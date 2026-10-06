# WHAT THIS FILE DOES: small math helpers that turn the paper's delay and cost formulas
#   (eq. 5-7 costs, eq. 9-14 delays) into Python functions.
# WHY WE NEED IT: every algorithm (placement, migration, metrics) must score decisions
#   with the SAME formulas, so they live in one place instead of being copied around.
# WHO CALLS IT: spvir.py (placement), vima.py (migration scoring), simulator.py (per-slot
#   totals), followme.py. They import it as `dc` and call e.g. dc.d_hop(...).
# Paper totals: R = Rc + Rm + Rs (eq. 8, cost) and D = Dtra + Dhop + Ddep + Dmig (eq. 14, delay).

import math    # "import" loads a module; math gives dist(), log2(), etc.
import config  # our own config.py: all numeric parameters (W, D_HOP, C_MIG_PER_HOP, ...) live there


def distance(v, r):                        # Euclidean distance vehicle-RSU
    # "def name(args):" defines a function. v is a vehicle, r is an RSU; both have .x and .y.
    # math.dist(p, q) = sqrt((px-qx)^2 + (py-qy)^2). (a, b) is a tuple = a fixed pair of values.
    return math.dist((v.x, v.y), (r.x, r.y))  # "return" hands the result back to the caller


def tx_rate(d):                            # eq. 10
    # eq. 10: r = W * log2(1 + p|h|^2 / (noise * d^theta)) -> Shannon capacity with path loss.
    # W = bandwidth (Hz), P_TX = transmit power p, H2 = channel gain |h|^2, THETA = path-loss exponent.
    # Farther vehicle -> bigger d^theta -> weaker signal -> lower bit rate.
    # max(d, 1.0): distance is clamped to at least 1 m so d = 0 never divides by zero. ** means "power".
    return config.W * math.log2(1 + config.P_TX * config.H2 / (config.NOISE * max(d, 1.0) ** config.THETA))


def d_tra(size_bits, d):                   # eq. 9 (one request)
    # eq. 9: transmission delay = data size / rate. Time to upload the request over the air
    # from the vehicle to its ingress RSU that is d metres away.
    return size_bits / tx_rate(d)


def path_hops(n_init, rsus, hop):          # hops along n_init -> VNF1 -> VNF2 ...
    # Counts how many network hops the traffic makes walking through the chain in order.
    # n_init = ingress RSU id, rsus = list of RSU ids hosting VNF1, VNF2, ...,
    # hop = 2-D table, hop[a][b] = shortest hop count between RSU a and RSU b.
    total, prev = 0, n_init                # tuple unpacking: total = 0 and prev = n_init in one line
    for r in rsus:                         # "for x in list:" repeats the indented block once per item
        total += hop[prev][r]              # += means total = total + ...; add hops from previous stop to r
        prev = r                           # the next VNF is measured from where we are now
    return total                           # total hops of the whole chain path


def d_hop(hops):
    # eq. 11: hop delay = number of hops * delay of one hop. More hops -> slower service.
    return hops * config.D_HOP             # eq. 11


def d_dep(num_cold):
    # eq. 12: deployment delay. Each cold start must download/boot a container image,
    # which costs D_DEP seconds. Reusing a container avoids this; that is the point of SPVIR.
    return num_cold * config.D_DEP         # eq. 12


def d_mig(num_mig):
    # eq. 13: migration delay. Moving a running container interrupts it for D_MIG seconds.
    return num_mig * config.D_MIG          # eq. 13


def r_comp(cold_vnfs):                     # eq. 5
    # eq. 5: instantiation (cold start) cost Rc. Bigger VNFs (more CPU) cost more to start.
    # "sum(expr for f in list)" is a generator expression: compute expr for each f, then add all up.
    return sum(f.cpu * config.C_INST for f in cold_vnfs)


def r_mig(hops):
    # eq. 6: migration cost Rm of ONE container, proportional to how many hops it travels.
    return hops * config.C_MIG_PER_HOP     # eq. 6 (one migration)


def r_keep(n):
    # eq. 7: keep-alive cost Rs. Every container kept running (even idle) costs C_KEEP per slot.
    # This is why idle containers are deleted after a while (eq. 4, done in simulator.py).
    return n * config.C_KEEP               # eq. 7
