"""PHASE 2 - STEP 1: Mobility attacker (vehicles that lie about their position).

Attack types and parameters follow the VeReMi dataset paper
(van der Heijden, Lukaseder, Kargl, SecureComm 2018):
    const_pos      : always reports the same fixed position
    const_offset   : true position + fixed offset (250 m, -150 m)
    random_pos     : a random position anywhere in the area, every report
    random_offset  : true position + random offset in [-300, 300] m (x and y)
    eventual_stop  : honest at first, then "freezes" (keeps sending one old position);
                     chance of freezing grows by 0.025 per report
    mixed          : liars are split evenly across the five types

Honest vehicles are not perfect either: their GPS has ~5 m noise, and 2% of the
time it is badly wrong (150 m). That noise is what makes lie detection non-trivial.

Key idea: every vehicle has a TRUE position (physics) and a REPORTED position
(what the controller is told). SPAVM only ever sees the reported one.
"""
import math
import config

TYPES = ("const_pos", "const_offset", "random_pos", "random_offset", "eventual_stop")


class MobilityAttacker:
    def __init__(self, vehicles, side, select_rng, event_rng, fraction=None, mode=None):
        fraction = config.P2_LIAR_FRACTION if fraction is None else fraction
        mode = config.P2_LIAR_MODE if mode is None else mode
        self.side, self.rng = side, event_rng
        k = round(fraction * len(vehicles))
        chosen = select_rng.sample([v.vid for v in vehicles], k) if k else []
        self.kind = {}
        for i, vid in enumerate(sorted(chosen)):
            self.kind[vid] = TYPES[i % len(TYPES)] if mode == "mixed" else mode
        self.fixed_point = (0.85 * side, 0.15 * side)          # const_pos target
        self._stop_p = {vid: 0.0 for vid in self.kind}
        self._frozen = {}

    def is_liar(self, vid):
        return vid in self.kind

    def report(self, v):
        """The position this vehicle SENDS to the controller this slot."""
        kind = self.kind.get(v.vid)
        if kind is None:
            return self._honest(v)
        if kind == "const_pos":
            return self.fixed_point
        if kind == "const_offset":
            dx, dy = config.P2_CONST_OFFSET
            return self._clip(v.x + dx, v.y + dy)
        if kind == "random_pos":
            return (self.rng.uniform(0, self.side), self.rng.uniform(0, self.side))
        if kind == "random_offset":
            r = config.P2_RANDOM_OFFSET
            return self._clip(v.x + self.rng.uniform(-r, r), v.y + self.rng.uniform(-r, r))
        # eventual_stop
        if v.vid in self._frozen:
            return self._frozen[v.vid]
        self._stop_p[v.vid] += config.P2_STOP_STEP
        if self.rng.random() < self._stop_p[v.vid]:
            self._frozen[v.vid] = (v.x, v.y)
        return (v.x, v.y)

    def _honest(self, v):
        x = v.x + self.rng.gauss(0, config.P2_GPS_NOISE_M)
        y = v.y + self.rng.gauss(0, config.P2_GPS_NOISE_M)
        if self.rng.random() < config.P2_GPS_FAULT_P:              # honest but broken GPS
            a = self.rng.uniform(0, 2 * math.pi)
            x += config.P2_GPS_FAULT_M * math.cos(a)
            y += config.P2_GPS_FAULT_M * math.sin(a)
        return self._clip(x, y)

    def _clip(self, x, y):
        return (min(max(x, 0.0), self.side), min(max(y, 0.0), self.side))
