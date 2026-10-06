# WHAT THIS FILE DOES: Algorithm 2 of the paper (VIMA). Each slot it looks at the containers
#   used by this slot's chains and tries moving (migrating) some to neighbour RSUs, keeping only
#   moves that lower the Lyapunov drift-plus-penalty score (eq. 31).
# WHY WE NEED IT: after placement, chains can zig-zag or visit the same RSU twice. Moving a
#   container can shorten the path (less hop delay), but migration costs money (eq. 6), so the
#   Lyapunov queues decide whether it is worth it. Phase 1 blocks moves onto untrusted RSUs;
#   Phase 2 counts "corrupt" migrations that only looked good because of false positions.
# WHO CALLS IT: simulator.py creates VIMA(self) and calls .run(placements) once per slot.

import networkx as nx                      # graph library; used for shortest paths and node degree
import config                              # parameters: MU_HOPS, VIMA_MAX_CANDIDATES, HOP_REFERENCE, ...
from . import delay_cost as dc             # our delay/cost formulas (eq. 5-14), short name dc


class VIMA:
    # "class" defines a new object type; "self" inside methods is this VIMA object.
    """Algorithm 2: VNF Instance Migration (sequential branch-and-bound as written in the paper)."""

    def __init__(self, sim):
        # Runs when we write VIMA(sim). Keep the simulator so we can see RSUs, graph, queues, etc.
        self.s = sim

    def traversal_path(self, p):           # rho(S, t): every RSU the chain actually crosses
        # Builds the full list of RSUs the traffic passes through, INCLUDING relay RSUs
        # between two VNFs. Needed to spot "loop" nodes (visited more than once).
        # [p.n_init] + p.rsus joins two lists: ingress first, then the RSU of each VNF.
        # p.rsus is a property in model.py: it looks like a field but is computed on access.
        seq, nodes = [p.n_init] + p.rsus, [p.n_init]
        # zip(seq, seq[1:]) pairs each item with the next one: (s0,s1), (s1,s2), ...
        # seq[1:] is "slicing": the list without its first element.
        for a, b in zip(seq, seq[1:]):
            if a != b:                     # two VNFs on the same RSU add no hops, skip
                # shortest_path gives [a, ..., b]; [1:] drops a because it is already in nodes.
                nodes += nx.shortest_path(self.s.G, a, b)[1:]
        return nodes

    def candidates(self, placements):      # Alg. 2 line 1: loop nodes first, then low degree
        # Alg.2 line 1: choose which containers are worth trying to move.
        # Priority 1: containers on "loop" nodes (chain passes the same RSU twice = zig-zag).
        # Priority 2: containers on low-degree RSUs (few neighbours = badly connected).
        # Max VIMA_MAX_CANDIDATES (10) to keep run time small.
        # set() = unordered collection with no duplicates; {} = empty dict (key -> value map).
        s, loop_nodes, on_path, used = self.s, set(), set(), {}
        for p in placements:               # every chain placed this slot
            rho = self.traversal_path(p)   # all RSUs this chain crosses
            on_path.update(rho)            # .update adds many items to a set
            # rho.count(n) = how many times n appears. >1 means the chain loops through n.
            loop_nodes.update(n for n in rho if rho.count(n) > 1)
            for c, _ in p.steps:           # "_" = a value we do not need (the cold-start flag)
                used[c.cid] = c            # dict keyed by container id -> each container listed once
        # Keep containers that sit on some chain path and still exist (not deleted).
        # .values() gives all values of the dict.
        cands = [c for c in used.values() if c.rsu in on_path and c in s.containers]
        # .sort(key=...) sorts in place. Tuple key: False sorts before True, so
        # "c.rsu not in loop_nodes" puts loop-node containers first; then lower degree; then lower id.
        cands.sort(key=lambda c: (c.rsu not in loop_nodes, s.G.degree[c.rsu], c.cid))
        return cands[:config.VIMA_MAX_CANDIDATES]   # slice [:k] = first k items

    def evaluate(self, placements, moves, truth=False):
        # truth=False is a default argument: callers can leave it out and it will be False.
        """U(H) for a set of moves; None if infeasible.
        truth=True (PHASE 2, measuring only): score with every chain starting at the vehicle's TRUE
        nearest RSU, to check whether a decision still makes sense once lies are removed."""
        # Scores a set of moves H = [(container, new_rsu), ...] WITHOUT really applying them.
        # Returns (eq. 31 score, per-RSU migration cost list R, delay), or None if not allowed.
        s = self.s
        # pos = "where each container WOULD be". Dict comprehension {key: value for ...}.
        # Two "for" parts = nested loop: for each placement p, for each step (c, _) of p.
        pos = {c.cid: c.rsu for p in placements for c, _ in p.steps}
        # delta[rid] = change in used CPU/mem/bw on each RSU if these moves happen. Starts at 0.
        delta = {r.rid: {"cpu": 0.0, "mem": 0.0, "bw": 0.0} for r in s.rsus}
        R = [0.0] * len(s.rsus)            # migration cost per RSU this slot (input to eq. 20/31)
        for c, nj in moves:                # each move: container c goes to RSU nj
            if s.hop[c.rsu][nj] > config.MU_HOPS:                  # eq. 3
                return None                # too far to move (hop limit mu)
            if not s.gate(nj):                                    # PHASE 1: never migrate onto an untrusted RSU
                return None
            # .items() gives (key, value) pairs of the dict, e.g. ("cpu", 2.0).
            for k, v in c.vnf.demand().items():
                delta[c.rsu][k] -= v       # source RSU frees this resource
                delta[nj][k] += v          # target RSU must hold it
            R[c.rsu] += dc.r_mig(s.hop[c.rsu][nj])                # eq. 6, charged to source RSU
            pos[c.cid] = nj                # container now (virtually) lives on nj
        for r in s.rsus:                                          # eq. 16-18
            # eq. 16-18: after the moves, no RSU may exceed its CPU/mem/bw capacity.
            # any(...) is True if at least one item is True. 1e-9 = tiny tolerance for float rounding.
            if any(r.used[k] + delta[r.rid][k] > r.cap[k] + 1e-9 for k in r.cap):
                return None
        # after moving, every chain must still respect the hop limit mu
        # With truth=True we only measure, so this check is skipped (loop over an empty list).
        for p in ([] if truth else placements):
            prev = p.n_init                # start measuring from the ingress RSU
            for c, _ in p.steps:
                # Same mu-hop reference rule as SPVIR (previous VNF or n_init, see config.HOP_REFERENCE).
                ref = prev if config.HOP_REFERENCE == "predecessor" else p.n_init
                if s.hop[ref][pos[c.cid]] > config.MU_HOPS:
                    return None            # this move would break some chain's hop limit
                prev = pos[c.cid]
        hops = 0.0                         # total hops of all chains after the moves
        for p in placements:
            rs = [pos[c.cid] for c, _ in p.steps]   # new RSU of each VNF in chain order
            if truth:
                # PHASE 2: measure from the TRUE nearest RSU (if known) instead of the reported one.
                hops += dc.path_hops(p.true_init if p.true_init is not None else p.n_init, rs, s.hop)
                continue                   # "continue" jumps to the next loop round
            hops += dc.path_hops(p.n_init, rs, s.hop)
        # Only the delay parts that migration can change: hop delay (eq. 11) + migration delay (eq. 13).
        # Dtra and Ddep do not depend on the moves, so they are left out of the comparison.
        delay = dc.d_hop(hops) + dc.d_mig(len(moves))     # len(list) = number of items
        return s.queues.objective(R, delay), R, delay             # eq. 31

    def _count_corrupt(self, placements, moves):
        """PHASE 2 metric: a chosen migration is 'corrupted' if, judged with TRUE positions,
        dropping it would be at least as good (it only looked useful because of false reports)."""
        if not moves:
            return 0                       # no migrations -> nothing to judge
        full = self.evaluate(placements, moves, truth=True)   # score of all chosen moves, true positions
        bad = 0
        for m in moves:
            # Score again with move m removed. "x is not m" compares identity (the same object).
            without = self.evaluate(placements, [x for x in moves if x is not m], truth=True)
            # [0] = the eq. 31 score. If removing m is not worse, m was useless -> corrupt.
            if full is not None and without is not None and full[0] >= without[0] - 1e-12:
                bad += 1
        return bad

    def run(self, placements):
        # Main entry of Algorithm 2. Returns (list of moves applied, per-RSU migration cost R).
        s = self.s
        self.last_corrupt = 0              # Phase 2 metric, read later by simulator.py
        if not placements:
            return [], [0.0] * len(s.rsus) # nothing placed this slot -> no migration, zero cost
        # Alg.2 lines 3-5: baseline H0 = "migrate nothing". Any move must beat this score.
        # evaluate returns 3 values; "_" ignores the delay.
        U_best, R_best, _ = self.evaluate(placements, [])         # lines 3-5: H0 = no migration
        best_moves = []                    # moves accepted so far (grows one candidate at a time)
        for c in self.candidates(placements):                     # line 6
            # Alg.2 line 6: take candidate containers one by one (sequential, not all combinations).
            H = []                         # branches for this candidate: (score, moves, R)
            for nj in s.G.nodes:                                  # line 7
                # Alg.2 line 7: try every other RSU as a target.
                # Hop limit mu inside evaluate() rejects far RSUs, so effectively only neighbours survive.
                if nj == c.rsu:
                    continue               # moving to the same RSU is not a move
                # Alg.2 line 8: two branches. H1 = add "move c to nj" to the moves so far; H2 = keep c where it is.
                # (A, B) is a tuple of two lists; the loop tries each one.
                for trial in (best_moves + [(c, nj)], best_moves):   # line 8: H1 migrate / H2 stay
                    res = self.evaluate(placements, trial)
                    if res is not None:                           # lines 9-16: keep feasible
                        H.append((res[0], trial, res[1]))         # (eq. 31 score, moves, R)
            if not H:
                continue                   # no feasible branch for this candidate
            # Alg.2 lines 17-21 (bound/prune): keep only the branches with the lowest score.
            U_min = min(h[0] for h in H)
            H = [h for h in H if h[0] <= U_min]                    # lines 17-21: prune
            # Alg.2 lines 23-25: pick the best branch; on a tie prefer FEWER moves (cheaper, safer).
            U, moves, R = min(H, key=lambda h: (h[0], len(h[1])))  # lines 23-25
            if U < U_best - 1e-12:         # strictly better than what we have (1e-12 ignores rounding noise)
                U_best, best_moves, R_best = U, moves, R
            # Only the best branch survives into the next candidate. This greedy branch-and-bound
            # is fast but can get stuck in a local optimum, as the paper itself admits.
        # PHASE 2: count how many chosen moves were fooled by false positions.
        # getattr(obj, "name", default) reads obj.name, or returns default if it does not exist.
        self.last_corrupt = self._count_corrupt(placements, best_moves) if getattr(s, "phase2", False) else 0
        # Really apply the moves. First release ALL old resources, then reserve new ones.
        # Doing it in two passes avoids a false "RSU full" error when containers swap places.
        for c, _ in best_moves:                                   # apply: release all, then reserve
            s.rm.release(c.rsu, c.vnf.demand())
        for c, nj in best_moves:
            s.rm.reserve(nj, c.vnf.demand())
            c.rsu = nj                     # the container now lives on RSU nj
        return best_moves, R_best          # R_best feeds the queue update (eq. 20) in simulator.py
