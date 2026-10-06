# WHAT THIS FILE DOES: Algorithm 1 of the paper (SPVIR). For one SFC request it decides,
#   VNF by VNF, which RSU container serves it: reuse an existing container if possible,
#   otherwise cold-start a new one, otherwise send the whole request to the cloud.
# WHY WE NEED IT: reusing containers avoids cold-start delay (eq. 12) and cost (eq. 5).
#   Phase 1 adds a trust gate (s.gate) and a sharing cap (s.share_cap) so we never reuse
#   or start containers on low-trust RSUs. Phase 2 records extra position fields.
# WHO CALLS IT: simulator.py creates SPVIR(self) once and calls .place(req) for each request.

import config                               # parameters: COVERAGE_R, MU_HOPS, HOP_REFERENCE, ...
from . import delay_cost as dc              # "from . import X" = import X from this same package; "as dc" = short name
from .model import Container, Placement     # data classes: a running container, and the final placement result


class SPVIR:
    # "class" defines a new object type. Methods below take "self" = this SPVIR object.
    """Algorithm 1: Service Placement based on VNF Instance Reuse."""

    def __init__(self, sim):
        # __init__ runs when we write SPVIR(sim). We keep a link to the simulator so we can
        # read its RSUs, containers, hop table, resource manager, trust gate, etc.
        self.s = sim

    def place(self, req):
        # Place one SFC request. Returns (Placement, d0) on success, or (None, reason) on failure.
        s = self.s                                                            # short local name for the simulator
        # Alg.1 line 1: pick ingress RSU n_init = RSU nearest the vehicle; d0 = its distance.
        # choose_ingress returns two values as a tuple; "a, b = ..." unpacks them.
        n_init, d0 = s.choose_ingress(req)                                    # line 1 (PHASE 2: may use confidence)
        # Alg.1 lines 2-3: nobody in range, or nearest RSU beyond coverage radius R -> go to cloud.
        # "is None" checks for Python's "no value" marker; "or" is true if either side is true.
        if n_init is None or d0 > config.COVERAGE_R:
            return None, "cloud_uncovered"                                    # lines 2-3
        # steps = list of (container, was_cold_start) in chain order; prev = RSU of the previous VNF.
        steps, prev = [], n_init                                              # [] is an empty list
        for f in req.chain:                                                   # line 5
            # Alg.1 line 5: handle each VNF f of the chain in order.
            # "A if cond else B" is Python's one-line if/else.
            # ref = the RSU from which the mu-hop limit is measured. Paper text: previous VNF
            # ("predecessor"); Alg.1 pseudo-code: n_init. config.HOP_REFERENCE switches between them.
            ref = prev if config.HOP_REFERENCE == "predecessor" else n_init
            cands = []                                                        # candidate containers to reuse
            if s.enable_reuse:                                                # lines 6-10: reuse
                # Alg.1 lines 6-10: look for an existing container we can SHARE. List comprehension:
                # [c for c in list if conditions] keeps only containers c that pass ALL conditions:
                cands = [c for c in s.containers if c.vnf.fid == f.fid        # same VNF type as f
                         and s.hop[ref][c.rsu] <= config.MU_HOPS              # within mu hops (eq. 3)
                         and c.load < s.share_cap(c.rsu)                    # PHASE 1 Step 5: sharing limit
                         and s.gate(c.rsu)]                           # PHASE 1: trust gate
            if cands:                                                         # a non-empty list counts as True
                # Reuse: pick the closest container; ties broken by smaller container id (deterministic).
                # min(list, key=func) returns the item with the smallest func(item).
                # "lambda c: ..." is a tiny unnamed function. It returns a tuple, and tuples are
                # compared element by element: first by hops, then by cid.
                # The whole line is tuple unpacking: c = the chosen container, cold = False (not a cold start).
                c, cold = min(cands, key=lambda c: (s.hop[ref][c.rsu], c.cid)), False
            else:                                                             # lines 12-13: cold start
                # Alg.1 lines 12-13: no reusable container, so start a new one.
                # Allowed RSUs: within mu hops, enough free CPU/mem/bw (eq. 16-18), and trusted (Phase 1).
                rs = [r.rid for r in s.rsus
                      if s.hop[ref][r.rid] <= config.MU_HOPS and s.rm.fits(r.rid, f.demand())
                      and s.gate(r.rid)]                              # PHASE 1: trust gate
                if not rs:                                                    # empty list -> no RSU can host f
                    # Cannot serve this VNF, so the whole SFC is rejected (all-or-nothing).
                    # Undo containers/loads we already set up for earlier VNFs of this chain.
                    self._rollback(steps)
                    return None, "cloud_infeasible"
                rid = min(rs, key=lambda i: (s.hop[ref][i], i))               # nearest allowed RSU (tie: lower id)
                c = Container(s.new_cid(), f, rid)                            # create a new container object
                s.rm.reserve(rid, f.demand())                                 # book its CPU/mem/bw on that RSU
                s.containers.append(c)                                        # .append adds to the end of the list
                cold = True                                                   # remember: this was a cold start (eq. 5, 12)
            c.load += 1                                                       # one more SFC now shares this container
            steps.append((c, cold))                                           # record (container, cold?) as a tuple
            prev = c.rsu                                                      # next VNF's hop limit is measured from here
        p = Placement(req, n_init, steps)                                     # bundle the final result
        if s.phase2:                                                          # PHASE 2 bookkeeping
            # alt_init = RSU that physically heard the vehicle's message (a fallback ingress).
            p.alt_init = req.receiver
            # true_init = RSU nearest the vehicle's TRUE position. Used only for measuring
            # (e.g. truth=True re-scoring in vima.py), never for decisions. [0] takes the id part.
            p.true_init = s.nearest_rsu((req.vehicle.x, req.vehicle.y))[0]
        return p, d0                                                          # success: placement and ingress distance

    def _rollback(self, steps):            # all-or-nothing per SFC request
        # Leading "_" in the name means "internal helper, not for outside use".
        # Undo every step of a partially placed chain.
        # reversed(list) walks the list backwards (undo in the opposite order we did things).
        for c, cold in reversed(steps):    # each step is a tuple (container, cold); unpack it
            c.load -= 1                    # this SFC no longer uses the container
            if cold and c in self.s.containers:   # "x in list" tests membership
                # We created this container for this request, so delete it and free its resources.
                self.s.rm.release(c.rsu, c.vnf.demand())
                self.s.containers.remove(c)       # .remove(x) deletes x from the list
