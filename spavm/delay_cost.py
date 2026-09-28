import math
import config


def distance(v, r):                        # Euclidean distance vehicle-RSU
    return math.dist((v.x, v.y), (r.x, r.y))


def tx_rate(d):                            # eq. 10
    return config.W * math.log2(1 + config.P_TX * config.H2 / (config.NOISE * max(d, 1.0) ** config.THETA))


def d_tra(size_bits, d):                   # eq. 9 (one request)
    return size_bits / tx_rate(d)


def path_hops(n_init, rsus, hop):          # hops along n_init -> VNF1 -> VNF2 ...
    total, prev = 0, n_init
    for r in rsus:
        total += hop[prev][r]
        prev = r
    return total


def d_hop(hops):
    return hops * config.D_HOP             # eq. 11


def d_dep(num_cold):
    return num_cold * config.D_DEP         # eq. 12


def d_mig(num_mig):
    return num_mig * config.D_MIG          # eq. 13


def r_comp(cold_vnfs):                     # eq. 5
    return sum(f.cpu * config.C_INST for f in cold_vnfs)


def r_mig(hops):
    return hops * config.C_MIG_PER_HOP     # eq. 6 (one migration)


def r_keep(n):
    return n * config.C_KEEP               # eq. 7
