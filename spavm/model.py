from dataclasses import dataclass, field


@dataclass(frozen=True)
class VNFType:
    fid: int
    cpu: float
    mem: float
    bw: float

    def demand(self):
        return {"cpu": self.cpu, "mem": self.mem, "bw": self.bw}


@dataclass(eq=False)          # identity semantics: each container is a unique object
class Container:
    cid: int
    vnf: VNFType
    rsu: int
    load: int = 0             # SFCs served this slot (q in eq. 2/3)
    idle: int = 0             # consecutive unused slots (i(.) in eq. 4)


@dataclass
class RSU:
    rid: int
    x: float
    y: float
    cap: dict
    used: dict = field(default_factory=lambda: {"cpu": 0.0, "mem": 0.0, "bw": 0.0})


@dataclass
class Vehicle:
    vid: int
    x: float
    y: float
    vx: float
    vy: float


@dataclass
class SFCRequest:
    rid: int
    vehicle: Vehicle
    chain: list               # ordered list of VNFType
    size_bits: float          # L_k


@dataclass
class Placement:
    request: SFCRequest
    n_init: int
    steps: list               # [(Container, is_cold_start), ...] in chain order

    @property
    def rsus(self):
        return [c.rsu for c, _ in self.steps]
