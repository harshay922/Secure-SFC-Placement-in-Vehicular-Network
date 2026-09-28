import math
import networkx as nx
import config
from .model import RSU


def build_network(num_rsus, rng):
    """Random RSU positions + links within LINK_RADIUS + MST (guarantees connectivity)."""
    side = math.sqrt(num_rsus) * config.RSU_SPACING
    cap = {"cpu": config.RSU_CPU, "mem": config.RSU_MEM, "bw": config.RSU_BW}
    rsus = [RSU(i, rng.uniform(0, side), rng.uniform(0, side), dict(cap)) for i in range(num_rsus)]
    G, full = nx.Graph(), nx.Graph()
    G.add_nodes_from(range(num_rsus))
    for a in rsus:
        for b in rsus:
            if a.rid < b.rid:
                d = math.dist((a.x, a.y), (b.x, b.y))
                full.add_edge(a.rid, b.rid, weight=d)
                if d <= config.LINK_RADIUS:
                    G.add_edge(a.rid, b.rid)
    if num_rsus > 1:
        G.add_edges_from(nx.minimum_spanning_edges(full, data=False))
    hop = dict(nx.all_pairs_shortest_path_length(G))
    return rsus, G, hop, side
