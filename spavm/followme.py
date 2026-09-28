"""PHASE 2 - STEP 3b + STEP 4: Follow-me service migration, and its storm guard.

Why this exists
    SPAVM's VIMA only straightens chain paths; it never moves a service because a vehicle
    moved. So position lies cannot push VIMA into migration storms (we measured this).
    Real vehicular edge systems, however, also keep a per-vehicle service (session state,
    e.g. the vehicle's own processing instance) close to the vehicle and MIGRATE it as the
    vehicle drives: the classic distance-threshold ("follow-me") policy.
    That is exactly the kind of migration a lying vehicle can abuse.

Policy (each slot, for every vehicle the network can hear)
    target = serving RSU for this vehicle (chosen by the scheme: SPAVM / ignore / ours / oracle)
    if the service is more than P2_FOLLOW_HOPS hops from target -> migrate it to target
       cost = hops x C_MIG_PER_HOP (same unit cost as VIMA, eq. 6), reported separately
       (kept out of VIMA's Lyapunov queues: with a shared budget the queues grow even with no
        attackers, which would starve VIMA in every scheme and hide the comparison)

Storm guard (Step 4)
    Only migrate if the same target was requested for P2_STABLE_SLOTS slots in a row
    (hysteresis). A random-position liar jumps somewhere new every slot, so it never
    becomes stable; an honest vehicle waits at most one extra slot.

Measured
    sess_mig      migrations per slot
    sess_cost     migration cost (cost units)
    sess_corrupt  migrations to an RSU far (> P2_FOLLOW_HOPS) from the vehicle's TRUE nearest RSU
    access delay  honest vehicles: hops between their true nearest RSU and their service x 10 ms
"""
import config
from . import delay_cost as dc


class FollowMe:
    def __init__(self, sim):
        self.s = sim
        self.loc = {}                  # vehicle id -> RSU hosting its service
        self.pending = {}              # vehicle id -> (requested target, how many slots in a row)

    def step(self, t, row):
        s = self.s
        for v in s.vehicles:
            claim, receiver, conf, liar = s._reports[v.vid]
            true_pos = (v.x, v.y)
            target, _ = s.ingress_for(true_pos, claim, receiver, conf)
            if target is None:
                continue                                   # vehicle unreachable: service stays put
            cur = self.loc.get(v.vid)
            if cur is None:
                self.loc[v.vid] = cur = target             # first contact: start the service here
            elif s.hop[cur][target] > config.P2_FOLLOW_HOPS and s.gate(target):
                go = True
                if s.storm_guard:
                    last, n = self.pending.get(v.vid, (None, 0))
                    n = n + 1 if last == target else 1
                    self.pending[v.vid] = (target, n)
                    go = n >= config.P2_STABLE_SLOTS
                if go:
                    cost = dc.r_mig(s.hop[cur][target])
                    row["sess_mig"] += 1
                    row["sess_cost"] += cost
                    true_near = s.nearest_rsu(true_pos)[0]
                    row["sess_corrupt"] += s.hop[target][true_near] > config.P2_FOLLOW_HOPS
                    self.loc[v.vid] = cur = target
                    self.pending.pop(v.vid, None)
            else:
                self.pending.pop(v.vid, None)
            if not liar:
                true_near = s.nearest_rsu(true_pos)[0]
                row["sess_honest"] += 1
                row["sess_access_delay"] += dc.d_hop(s.hop[true_near][cur])
