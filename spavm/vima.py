import networkx as nx
import config
from . import delay_cost as dc


class VIMA:
    """Algorithm 2: VNF Instance Migration (sequential branch-and-bound as written in the paper)."""

    def __init__(self, sim):
        self.s = sim

    def traversal_path(self, p):           # rho(S, t): every RSU the chain actually crosses
        seq, nodes = [p.n_init] + p.rsus, [p.n_init]
        for a, b in zip(seq, seq[1:]):
            if a != b:
                nodes += nx.shortest_path(self.s.G, a, b)[1:]
        return nodes

    def candidates(self, placements):      # Alg. 2 line 1: loop nodes first, then low degree
        s, loop_nodes, on_path, used = self.s, set(), set(), {}
        for p in placements:
            rho = self.traversal_path(p)
            on_path.update(rho)
            loop_nodes.update(n for n in rho if rho.count(n) > 1)
            for c, _ in p.steps:
                used[c.cid] = c
        cands = [c for c in used.values() if c.rsu in on_path and c in s.containers]
        cands.sort(key=lambda c: (c.rsu not in loop_nodes, s.G.degree[c.rsu], c.cid))
        return cands[:config.VIMA_MAX_CANDIDATES]

    def evaluate(self, placements, moves, truth=False):
        """U(H) for a set of moves; None if infeasible.
        truth=True (PHASE 2, measuring only): score with every chain starting at the vehicle's TRUE
        nearest RSU, to check whether a decision still makes sense once lies are removed."""
        s = self.s
        pos = {c.cid: c.rsu for p in placements for c, _ in p.steps}
        delta = {r.rid: {"cpu": 0.0, "mem": 0.0, "bw": 0.0} for r in s.rsus}
        R = [0.0] * len(s.rsus)
        for c, nj in moves:
            if s.hop[c.rsu][nj] > config.MU_HOPS:                  # eq. 3
                return None
            if not s.gate(nj):                                    # PHASE 1: never migrate onto an untrusted RSU
                return None
            for k, v in c.vnf.demand().items():
                delta[c.rsu][k] -= v
                delta[nj][k] += v
            R[c.rsu] += dc.r_mig(s.hop[c.rsu][nj])                # eq. 6, charged to source RSU
            pos[c.cid] = nj
        for r in s.rsus:                                          # eq. 16-18
            if any(r.used[k] + delta[r.rid][k] > r.cap[k] + 1e-9 for k in r.cap):
                return None
        # after moving, every chain must still respect the hop limit mu
        for p in ([] if truth else placements):
            prev = p.n_init
            for c, _ in p.steps:
                ref = prev if config.HOP_REFERENCE == "predecessor" else p.n_init
                if s.hop[ref][pos[c.cid]] > config.MU_HOPS:
                    return None
                prev = pos[c.cid]
        hops = 0.0
        for p in placements:
            rs = [pos[c.cid] for c, _ in p.steps]
            if truth:
                hops += dc.path_hops(p.true_init if p.true_init is not None else p.n_init, rs, s.hop)
                continue
            hops += dc.path_hops(p.n_init, rs, s.hop)
        delay = dc.d_hop(hops) + dc.d_mig(len(moves))
        return s.queues.objective(R, delay), R, delay             # eq. 31

    def _count_corrupt(self, placements, moves):
        """PHASE 2 metric: a chosen migration is 'corrupted' if, judged with TRUE positions,
        dropping it would be at least as good (it only looked useful because of false reports)."""
        if not moves:
            return 0
        full = self.evaluate(placements, moves, truth=True)
        bad = 0
        for m in moves:
            without = self.evaluate(placements, [x for x in moves if x is not m], truth=True)
            if full is not None and without is not None and full[0] >= without[0] - 1e-12:
                bad += 1
        return bad

    def run(self, placements):
        s = self.s
        self.last_corrupt = 0
        if not placements:
            return [], [0.0] * len(s.rsus)
        U_best, R_best, _ = self.evaluate(placements, [])         # lines 3-5: H0 = no migration
        best_moves = []
        for c in self.candidates(placements):                     # line 6
            H = []
            for nj in s.G.nodes:                                  # line 7
                if nj == c.rsu:
                    continue
                for trial in (best_moves + [(c, nj)], best_moves):   # line 8: H1 migrate / H2 stay
                    res = self.evaluate(placements, trial)
                    if res is not None:                           # lines 9-16: keep feasible
                        H.append((res[0], trial, res[1]))
            if not H:
                continue
            U_min = min(h[0] for h in H)
            H = [h for h in H if h[0] <= U_min]                    # lines 17-21: prune
            U, moves, R = min(H, key=lambda h: (h[0], len(h[1])))  # lines 23-25
            if U < U_best - 1e-12:
                U_best, best_moves, R_best = U, moves, R
        self.last_corrupt = self._count_corrupt(placements, best_moves) if getattr(s, "phase2", False) else 0
        for c, _ in best_moves:                                   # apply: release all, then reserve
            s.rm.release(c.rsu, c.vnf.demand())
        for c, nj in best_moves:
            s.rm.reserve(nj, c.vnf.demand())
            c.rsu = nj
        return best_moves, R_best
