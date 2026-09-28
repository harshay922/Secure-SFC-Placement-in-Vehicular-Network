import config
from . import delay_cost as dc
from .model import Container, Placement


class SPVIR:
    """Algorithm 1: Service Placement based on VNF Instance Reuse."""

    def __init__(self, sim):
        self.s = sim

    def place(self, req):
        s = self.s
        d0, n_init = min((dc.distance(req.vehicle, r), r.rid) for r in s.rsus)   # line 1
        if d0 > config.COVERAGE_R:
            return None, "cloud_uncovered"                                    # lines 2-3
        steps, prev = [], n_init
        for f in req.chain:                                                   # line 5
            ref = prev if config.HOP_REFERENCE == "predecessor" else n_init
            cands = []
            if s.enable_reuse:                                                # lines 6-10: reuse
                cands = [c for c in s.containers if c.vnf.fid == f.fid
                         and s.hop[ref][c.rsu] <= config.MU_HOPS
                         and c.load < s.share_cap(c.rsu)                    # PHASE 1 Step 5: sharing limit
                         and s.gate(c.rsu)]                           # PHASE 1: trust gate
            if cands:
                c, cold = min(cands, key=lambda c: (s.hop[ref][c.rsu], c.cid)), False
            else:                                                             # lines 12-13: cold start
                rs = [r.rid for r in s.rsus
                      if s.hop[ref][r.rid] <= config.MU_HOPS and s.rm.fits(r.rid, f.demand())
                      and s.gate(r.rid)]                              # PHASE 1: trust gate
                if not rs:
                    self._rollback(steps)
                    return None, "cloud_infeasible"
                rid = min(rs, key=lambda i: (s.hop[ref][i], i))
                c = Container(s.new_cid(), f, rid)
                s.rm.reserve(rid, f.demand())
                s.containers.append(c)
                cold = True
            c.load += 1
            steps.append((c, cold))
            prev = c.rsu
        return Placement(req, n_init, steps), d0

    def _rollback(self, steps):            # all-or-nothing per SFC request
        for c, cold in reversed(steps):
            c.load -= 1
            if cold and c in self.s.containers:
                self.s.rm.release(c.rsu, c.vnf.demand())
                self.s.containers.remove(c)
