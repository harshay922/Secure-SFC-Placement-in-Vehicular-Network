# =====================================================================
# mobility.py  -  where every car is, every second
# ---------------------------------------------------------------------
# Library used by all steps:
#     mob = Mobility(net); mob.start(); cars = mob.step(); mob.close()
#     cars = {car_id: (x, y, rsu_id or None)}   (rsu = nearest RSU within 300 m, None = only cloud)
# Two modes (config.USE_MOBILITY_TRACE):
#   LIVE  : runs SUMO and asks it for every car position (TraCI)  -> ~2.5 min per hour
#   TRACE : replays the positions recorded ONCE from the same SUMO run (seed 42)
#           by step2b_record_trace.py                              -> a few seconds per hour
# Both give exactly the same cars, because SUMO always uses seed 42.
# =====================================================================

import csv                                  # read/write the trace file
import gzip                                 # the trace file is compressed (.gz)
import os                                   # paths and environment variables
import sys                                  # to add SUMO's tools folder to Python's search path
import config as cfg                        # our settings

_TRACE = None                               # the trace is loaded once per Python process and then reused


def load_trace():
    """Read the recorded trace into memory: {second: {car: (x, y, rsu)}}."""
    global _TRACE
    if _TRACE is None:                                           # first time -> read the file
        _TRACE = {}
        with gzip.open(cfg.TRACE_FILE, "rt", newline="") as f:   # open the compressed csv as text
            for row in csv.DictReader(f):                        # columns: t, car, x, y, rsu
                t = int(row["t"])
                _TRACE.setdefault(t, {})[row["car"]] = (float(row["x"]), float(row["y"]), row["rsu"] or None)
    return _TRACE


class Mobility:
    def __init__(self, net, live=None):
        self.net = net                                           # Network object (RSU positions)
        self.live = (not cfg.USE_MOBILITY_TRACE) if live is None else live   # which mode
        self.t = 0                                               # current simulation second
        self.cars = {}

    def start(self):
        self.t = 0
        if not self.live:                                        # TRACE mode: just load the file
            if not os.path.isfile(cfg.TRACE_FILE):
                raise FileNotFoundError("Trace missing - run  python step2b_record_trace.py  once first")
            self.trace = load_trace()
            return
        if "SUMO_HOME" in os.environ:                            # LIVE mode: start SUMO
            sys.path.append(os.path.join(os.environ["SUMO_HOME"], "tools"))
        import traci, sumolib                                    # imported only when needed
        self.traci = traci
        program = sumolib.checkBinary("sumo-gui" if cfg.USE_SUMO_GUI else "sumo")
        cmd = [program, "-c", cfg.SUMO_CFG_FILE, "--seed", str(cfg.SUMO_SEED),
               "--no-step-log", "true", "--no-warnings", "true"]
        if cfg.USE_SUMO_GUI:
            cmd += ["--start", "--delay", "50"]
        traci.start(cmd)

    def step(self):                                              # advance one second
        self.t += cfg.SUMO_STEP_S
        if not self.live:                                        # TRACE: read this second from memory
            self.cars = self.trace.get(self.t, {})
            return self.cars
        self.traci.simulationStep()                              # LIVE: SUMO moves every car 1 s
        self.cars = {}
        for car in self.traci.vehicle.getIDList():
            x, y = self.traci.vehicle.getPosition(car)
            near = self.net.rsus_in_range(x, y)                  # RSUs within 300 m, nearest first
            self.cars[car] = (x, y, near[0][0] if near else None)
        return self.cars

    def close(self):
        if self.live:
            self.traci.close()
