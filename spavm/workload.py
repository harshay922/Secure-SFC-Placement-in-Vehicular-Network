import math
import config
from .model import VNFType, Vehicle, SFCRequest


def _level(rng, n):
    # [P] "smaller demands acquire higher proportions" -> weight 1/(k+1)
    return rng.choices(range(n), weights=[1.0 / (k + 1) for k in range(n)])[0]


def build_vnf_catalog(rng):
    cat = []
    for f in range(config.NUM_VNF_TYPES):
        k = _level(rng, len(config.CPU_LEVELS))
        mem = config.MEM_LEVELS[min(k, len(config.MEM_LEVELS) - 1)]
        cat.append(VNFType(f, config.CPU_LEVELS[k], mem, config.BW_LEVELS[k]))
    return cat


def build_sfc_catalog(rng, vnfs):
    return [rng.sample(vnfs, rng.randint(config.SFC_LEN_MIN, config.SFC_LEN_MAX))
            for _ in range(config.NUM_SFC_TYPES)]


def build_vehicles(n, side, rng):
    out = []
    for i in range(n):
        sp, ang = rng.uniform(*config.VEHICLE_SPEED), rng.uniform(0, 2 * math.pi)
        out.append(Vehicle(i, rng.uniform(0, side), rng.uniform(0, side),
                           sp * math.cos(ang), sp * math.sin(ang)))
    return out


def move_vehicles(vehicles, side):
    for v in vehicles:
        v.x += v.vx * config.SLOT_SECONDS
        v.y += v.vy * config.SLOT_SECONDS
        if not 0 <= v.x <= side:
            v.vx, v.x = -v.vx, min(max(v.x, 0.0), side)
        if not 0 <= v.y <= side:
            v.vy, v.y = -v.vy, min(max(v.y, 0.0), side)


def poisson(rng, lam):
    L, k, p = math.exp(-lam), 0, 1.0
    while True:
        p *= rng.random()
        if p <= L:
            return k
        k += 1


def generate_requests(vehicles, sfcs, rng, start_id):
    reqs, rid = [], start_id
    for v in vehicles:
        for _ in range(poisson(rng, config.REQUEST_RATE)):
            reqs.append(SFCRequest(rid, v, rng.choice(sfcs), rng.uniform(*config.SFC_SIZE_BITS)))
            rid += 1
    return reqs
