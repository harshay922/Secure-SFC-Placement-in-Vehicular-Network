# WHAT THIS FILE DOES: creates the "workload": the VNF types, the SFC chains, the vehicles,
#   moves the vehicles each slot, and generates new SFC requests each slot.
# WHY WE NEED IT: the algorithms (SPVIR, VIMA) need requests to place. These functions build
#   them following the paper's setup (Sec. V-A): 20 VNF types, chains of 2-6, Poisson arrivals.
# WHO USES IT: spavm/simulator.py imports all these functions.
import math  # exp, cos, sin, pi
import config  # settings: NUM_VNF_TYPES, CPU_LEVELS, REQUEST_RATE, ...
from .model import VNFType, Vehicle, SFCRequest  # the data classes we create here


def _level(rng, n):  # a leading "_" in a name means "private helper, only used in this file"
    # [P] "smaller demands acquire higher proportions" -> weight 1/(k+1)
    # Pick an index k in 0..n-1; k=0 has weight 1, k=1 has 1/2, k=2 has 1/3, ... so small demands
    # are more common. rng.choices returns a list of one item, so [0] takes that item.
    return rng.choices(range(n), weights=[1.0 / (k + 1) for k in range(n)])[0]


def build_vnf_catalog(rng):  # returns the list of all NUM_VNF_TYPES VNF types
    cat = []  # empty list to fill
    for f in range(config.NUM_VNF_TYPES):  # f = 0, 1, ..., 19
        k = _level(rng, len(config.CPU_LEVELS))  # len(list) = number of items; pick a demand level
        # MEM_LEVELS has only 5 values but CPU has 6, so min(...) stops k from going past the end.
        mem = config.MEM_LEVELS[min(k, len(config.MEM_LEVELS) - 1)]
        cat.append(VNFType(f, config.CPU_LEVELS[k], mem, config.BW_LEVELS[k]))  # same level for CPU and BW
    return cat


def build_sfc_catalog(rng, vnfs):  # returns NUM_SFC_TYPES chains; each chain is a list of VNFTypes
    # rng.randint(a, b) = random whole number from a to b (both included) -> chain length 2..6.
    # rng.sample(list, n) = n DIFFERENT items picked at random, so no VNF repeats inside one chain.
    # "_" is used as the loop variable because we do not need its value.
    return [rng.sample(vnfs, rng.randint(config.SFC_LEN_MIN, config.SFC_LEN_MAX))
            for _ in range(config.NUM_SFC_TYPES)]


def build_vehicles(n, side, rng):  # create n vehicles at random places inside the side x side area
    out = []
    for i in range(n):
        # rng.uniform(*config.VEHICLE_SPEED): the * unpacks the tuple (10, 30) into two arguments.
        # sp = speed (m/s), ang = direction in radians (0 to 2*pi = a full circle).
        sp, ang = rng.uniform(*config.VEHICLE_SPEED), rng.uniform(0, 2 * math.pi)
        # velocity split into x and y parts with cos and sin (basic trigonometry).
        out.append(Vehicle(i, rng.uniform(0, side), rng.uniform(0, side),
                           sp * math.cos(ang), sp * math.sin(ang)))
    return out


def move_vehicles(vehicles, side):  # advance every vehicle by one time slot
    for v in vehicles:
        v.x += v.vx * config.SLOT_SECONDS  # "+=" = add to the current value; distance = speed * time
        v.y += v.vy * config.SLOT_SECONDS
        if not 0 <= v.x <= side:  # left the area in x? (Python allows chained comparisons a <= x <= b)
            # bounce: reverse x speed and clamp the position back to the edge (min/max keep it in [0, side]).
            v.vx, v.x = -v.vx, min(max(v.x, 0.0), side)
        if not 0 <= v.y <= side:  # same for y
            v.vy, v.y = -v.vy, min(max(v.y, 0.0), side)


def poisson(rng, lam):
    # Draw a random count from a Poisson distribution with mean lam (Knuth's method):
    # multiply uniform random numbers until the product drops below e^-lam; the number of
    # steps needed is the Poisson sample. Used for "how many requests does a vehicle send now".
    L, k, p = math.exp(-lam), 0, 1.0
    while True:  # loop forever until "return" exits the function
        p *= rng.random()  # rng.random() = random number in [0, 1); "*=" multiplies in place
        if p <= L:
            return k
        k += 1


def generate_requests(vehicles, sfcs, rng, start_id):  # new SFC requests for one time slot
    reqs, rid = [], start_id  # empty result list, and the next request id to use
    for v in vehicles:
        # each vehicle sends a Poisson(REQUEST_RATE) number of requests (usually 0, sometimes 1+)
        for _ in range(poisson(rng, config.REQUEST_RATE)):
            # rng.choice picks one chain from the catalog; size L_k is random in SFC_SIZE_BITS (eq. 9).
            reqs.append(SFCRequest(rid, v, rng.choice(sfcs), rng.uniform(*config.SFC_SIZE_BITS)))
            rid += 1  # next request gets a new id
    return reqs
