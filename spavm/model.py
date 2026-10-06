# WHAT THIS FILE DOES: defines the basic "things" of the simulation as small classes:
#   a VNF type, a running container, an RSU, a vehicle, an SFC request, and a placement.
# WHY WE NEED IT: every other part of the code talks about these objects, so they are defined
#   once here. They mostly just hold data (no algorithms here).
# WHO USES IT: spavm/network.py (RSU), spavm/workload.py (VNFType, Vehicle, SFCRequest),
#   spavm/spvir.py (Container, Placement), and tests/test_phase2.py (Vehicle).
# Python note: a class is a template for objects. @dataclass = Python writes __init__ (the
#   constructor), printing and comparison for us, from the list of fields "name: type".

from dataclasses import dataclass, field  # dataclass decorator; field() for special default values


@dataclass(frozen=True)  # frozen=True = fields cannot be changed after creation (a VNF type never changes)
class VNFType:  # one KIND of VNF (e.g. "firewall"), with its resource demand
    fid: int  # function id: 0 .. NUM_VNF_TYPES-1
    cpu: float  # CPU units one container of this type needs
    mem: float  # memory units needed
    bw: float  # bandwidth units needed

    def demand(self):  # method = function that belongs to the class; self = this particular object
        return {"cpu": self.cpu, "mem": self.mem, "bw": self.bw}  # demand as a dict, used for eq. 16-18 checks


@dataclass(eq=False)          # identity semantics: each container is a unique object
#                               (eq=False: two containers are "equal" only if they are the same object,
#                               even if all their fields are the same)
class Container:  # one RUNNING instance of a VNF on an RSU; can be reused by several SFCs
    cid: int  # container id (unique number)
    vnf: VNFType  # which VNF type this container runs
    rsu: int  # id of the RSU it currently runs on (changes when VIMA migrates it)
    load: int = 0             # SFCs served this slot (q in eq. 2/3)
    #                           "= 0" is a default value: if not given, it starts at 0
    idle: int = 0             # consecutive unused slots (i(.) in eq. 4)
    #                           when idle reaches IDLE_LIMIT the container is deleted


@dataclass
class RSU:  # Road Side Unit = edge server next to the road
    rid: int  # RSU id: 0 .. num_rsus-1 (also its node number in the network graph)
    x: float  # position in metres
    y: float
    cap: dict  # capacity {"cpu": 96, "mem": 100, "bw": 96} (right-hand side of eq. 16-18)
    # used = resources currently taken by containers. default_factory makes a NEW dict for every RSU
    # (a plain "= {...}" would make all RSUs share one dict, a classic Python bug).
    # lambda = a tiny unnamed function; here it returns a fresh dict each time it is called.
    used: dict = field(default_factory=lambda: {"cpu": 0.0, "mem": 0.0, "bw": 0.0})


@dataclass
class Vehicle:  # a car that sends SFC requests and moves each slot
    vid: int  # vehicle id
    x: float  # current TRUE position in metres
    y: float
    vx: float  # velocity in x direction (m/s)
    vy: float  # velocity in y direction (m/s)


@dataclass
class SFCRequest:  # one request from a vehicle for one service chain
    rid: int  # request id (unique)
    vehicle: Vehicle  # which vehicle asked
    chain: list               # ordered list of VNFType
    size_bits: float          # L_k
    #                           data size in bits; used for transmission delay (eq. 9)
    # ---- PHASE 2 (filled only when mobility reports are simulated) ----
    reported: tuple = None    # position the vehicle CLAIMS (x, y)
    receiver: int = None      # RSU that physically received the message (None = nobody heard it)
    conf: float = 1.0         # confidence in the reported position (Step 2)
    is_liar: bool = False     # ground truth, used ONLY for measuring results
    #                           bool = True/False. The algorithm must never read this (it would be cheating).


@dataclass
class Placement:  # the result of placing one SFC request (output of SPVIR, Alg. 1)
    request: SFCRequest  # the request that was placed
    n_init: int  # ingress RSU = the RSU the vehicle sends its data to first
    steps: list               # [(Container, is_cold_start), ...] in chain order
    #                           one pair per VNF: which container serves it, and whether it was newly
    #                           started (cold start, costs D_DEP) or reused (warm)
    alt_init: int = None      # PHASE 2: fallback ingress (the receiving RSU)
    true_init: int = None     # PHASE 2: nearest RSU to the TRUE position (for measuring only)

    @property  # @property = lets us write p.rsus (no brackets) instead of p.rsus()
    def rsus(self):
        # List comprehension over (container, flag) pairs; "_" = a name for a value we ignore.
        # Result: the RSU id of every VNF in chain order, e.g. [3, 3, 5]. Used to count hops (eq. 11).
        return [c.rsu for c, _ in self.steps]
