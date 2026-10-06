# WHAT THIS FILE DOES: creates the RSU network: places RSUs at random spots and decides
#   which RSUs are linked to each other, then pre-computes hop counts between all pairs.
# WHY WE NEED IT: placement (SPVIR) and migration (VIMA) need to know how many hops apart
#   two RSUs are (mu-hop limit, multi-hop delay eq. 11, migration cost eq. 6).
# WHO USES IT: spavm/simulator.py calls build_network() once at the start of a run.
import math  # math functions: sqrt, dist
import networkx as nx  # networkx = library for graphs (nodes + edges); "nx" is its usual short name
import config  # our settings (RSU_SPACING, LINK_RADIUS, capacities)
from .model import RSU  # the dot means "from this same package (spavm)"


def build_network(num_rsus, rng):
    """Random RSU positions + links within LINK_RADIUS + MST (guarantees connectivity)."""
    # rng = a random number generator (random.Random) so results repeat with the same seed.
    side = math.sqrt(num_rsus) * config.RSU_SPACING  # side of the square area in metres
    cap = {"cpu": config.RSU_CPU, "mem": config.RSU_MEM, "bw": config.RSU_BW}  # capacity of one RSU
    # List comprehension: one RSU per i in range(num_rsus) (range(n) = 0,1,...,n-1), each at a
    # random (x, y). dict(cap) makes a separate copy so RSUs never share the same dict.
    rsus = [RSU(i, rng.uniform(0, side), rng.uniform(0, side), dict(cap)) for i in range(num_rsus)]
    # Two empty graphs: G = the real network, full = every pair connected, weighted by distance.
    G, full = nx.Graph(), nx.Graph()
    G.add_nodes_from(range(num_rsus))  # add all RSUs as nodes (even ones with no links yet)
    for a in rsus:  # double loop over all pairs of RSUs
        for b in rsus:
            if a.rid < b.rid:  # consider each pair once (skip a==b and the reversed pair)
                d = math.dist((a.x, a.y), (b.x, b.y))  # straight-line distance in metres
                full.add_edge(a.rid, b.rid, weight=d)  # candidate link, used for the MST below
                if d <= config.LINK_RADIUS:  # close enough -> real link (one hop)
                    G.add_edge(a.rid, b.rid)
    if num_rsus > 1:
        # MST = minimum spanning tree: the shortest set of links that connects all RSUs.
        # Adding it guarantees every RSU can reach every other one (no isolated RSUs).
        G.add_edges_from(nx.minimum_spanning_edges(full, data=False))
    # hop[a][b] = smallest number of links between RSU a and RSU b (a dict of dicts).
    # Computed once here so later code can look it up quickly.
    hop = dict(nx.all_pairs_shortest_path_length(G))
    return rsus, G, hop, side  # a function can return several values at once (as a tuple)
