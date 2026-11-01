# =====================================================================
# network.py  -  the physical network: 25 RSUs + 1 cloud + links
# ---------------------------------------------------------------------
# This file is a "library": other steps do  `from network import load_network`
# It reads rsus.csv and links.csv and answers questions like:
#   - where is RSU5?           - how many CPU units does it have?
#   - how many fibre hops from RSU5 to RSU9?  - what is the delay of that path?
#   - which RSUs are within 2 hops of RSU5?   (used by partial scale-out)
# =====================================================================

import csv                     # to read .csv files
import heapq                   # a "priority queue", used by Dijkstra's shortest-path algorithm
import math                    # for sqrt (distance between two points)
from collections import deque  # a fast queue, used by BFS (breadth-first search) to count hops
import config as cfg           # our settings file


class Network:                                         # one object that holds the whole network
    def __init__(self):                                # runs when we create Network()
        self.rsus = {}                                 # RSU id -> dict(x, y, cpu, mem)   (cloud NOT included)
        self.cloud = {}                                # the cloud: dict(cpu, mem)
        self.fibre = {}                                # RSU id -> {neighbour id: delay in ms}   (only RSU-RSU fibre links)
        self.cloud_delay_ms = {}                       # RSU id -> one-way delay RSU->cloud in ms (wireless link)
        self.cloud_bw_mbps = {}                        # RSU id -> bandwidth of RSU->cloud link in Mbps
        self.hops = {}                                 # (a, b) -> number of fibre hops between RSU a and RSU b
        self.path_delay_ms = {}                        # (a, b) -> smallest total fibre delay between a and b in ms
        self._to_cloud = {}                            # RSU -> delay RSU->cloud (filled the first time it is asked)

    # ---------- small helper functions ----------
    def distance_m(self, rsu_id, x, y):                # straight-line distance (metres) from a point (x, y) to an RSU
        r = self.rsus[rsu_id]                          # look up the RSU
        return math.sqrt((r["x"] - x) ** 2 + (r["y"] - y) ** 2)   # Pythagoras: sqrt(dx^2 + dy^2)

    def rsus_in_range(self, x, y):                     # list of RSUs that a car at (x, y) can reach, nearest first
        near = []                                      # empty list to fill
        for rid in self.rsus:                          # check every RSU
            d = self.distance_m(rid, x, y)             # distance car -> RSU
            if d <= cfg.RSU_RANGE_M:                   # inside the 300 m radio range?
                near.append((d, rid))                  # keep (distance, id)
        near.sort()                                    # sort by distance (smallest first)
        return [(rid, d) for d, rid in near]           # return list of (id, distance)

    def neighbours_within(self, rsu_id, max_hops):     # RSUs reachable in 1..max_hops fibre hops, closest first
        out = [(self.hops[(rsu_id, b)], self.path_delay_ms[(rsu_id, b)], b)   # (hops, delay, id)
               for b in self.rsus                                             # for every other RSU b
               if b != rsu_id and (rsu_id, b) in self.hops                    # b is connected by fibre
               and self.hops[(rsu_id, b)] <= max_hops]                        # and is close enough
        out.sort()                                     # fewest hops first, then smallest delay
        return [(b, h, d) for h, d, b in out]          # return list of (id, hops, delay_ms)

    def delay_ms(self, a, b):                          # one-packet delay between ANY two nodes (RSU or CLOUD)
        if a == b:                                     # same node -> no network delay
            return 0.0
        if a != cfg.CLOUD_ID and b != cfg.CLOUD_ID:    # RSU -> RSU: fibre path
            return self.path_delay_ms[(a, b)]
        rsu = a if b == cfg.CLOUD_ID else b            # the RSU end of an RSU <-> cloud trip
        if rsu not in self._to_cloud:                  # not computed yet -> compute once and remember (cache)
            # best way: go over fibre to some RSU r, then take r's wireless link to the cloud
            self._to_cloud[rsu] = min(self.path_delay_ms[(rsu, r)] + self.cloud_delay_ms[r] for r in self.rsus)
        return self._to_cloud[rsu]


def load_network():                                    # read the two csv files and build a Network object
    net = Network()                                    # empty network

    # ---- 1) read RSUs (and the cloud) from rsus.csv ----
    with open(cfg.RSU_FILE, newline="") as f:          # open rsus.csv
        for row in csv.DictReader(f):                  # each row becomes a dict: {"id": "RSU0", "x_m": "1000.4", ...}
            if row["id"] == cfg.CLOUD_ID:              # the CLOUD row has no position
                net.cloud = {"cpu": float(row["cpu"]), "mem": float(row["mem"])}   # store cloud capacity
            else:                                      # a normal RSU row
                net.rsus[row["id"]] = {                # store its position and capacity
                    "x": float(row["x_m"]),            # x position in metres (SUMO coordinates)
                    "y": float(row["y_m"]),            # y position in metres
                    "cpu": float(row["cpu"]),          # CPU units (96, from Alibaba)
                    "mem": float(row["mem"]),          # memory units (100, from Alibaba)
                }
                net.fibre[row["id"]] = {}              # start with no fibre neighbours

    # ---- 2) read links from links.csv ----
    with open(cfg.LINK_FILE, newline="") as f:         # open links.csv
        for row in csv.DictReader(f):                  # each row: src, dst, type, length_m, bandwidth_mbps, delay_ms
            a, b = row["src"], row["dst"]              # the two ends of the link
            trans = cfg.PKT_SIZE_BITS / (float(row["bandwidth_mbps"]) * 1e6) * 1000   # transmission delay = packet size / bandwidth, in ms
            delay = float(row["delay_ms"]) + trans     # one-way delay of one packet = propagation (from csv) + transmission
            if b == cfg.CLOUD_ID:                      # an RSU -> cloud wireless link
                net.cloud_delay_ms[a] = cfg.CLOUD_ONE_WAY_MS + trans   # 25 ms (config) + transmission, instead of the csv value
                net.cloud_bw_mbps[a] = float(row["bandwidth_mbps"])   # and its bandwidth (100 Mbps)
            else:                                      # an RSU <-> RSU fibre link (works in both directions)
                net.fibre[a][b] = delay                # a -> b
                net.fibre[b][a] = delay                # b -> a

    # ---- 3) hop count between every pair of RSUs (BFS over fibre links) ----
    for start in net.rsus:                             # start a BFS from every RSU
        seen = {start: 0}                              # RSU -> hops from start (start itself = 0 hops)
        queue = deque([start])                         # RSUs waiting to be expanded
        while queue:                                   # until nothing is left
            cur = queue.popleft()                      # take the oldest RSU in the queue
            for nb in net.fibre[cur]:                  # look at its fibre neighbours
                if nb not in seen:                     # first time we reach this neighbour?
                    seen[nb] = seen[cur] + 1           # it is one hop further than cur
                    queue.append(nb)                   # expand it later
        for end, h in seen.items():                    # save the result for every reached RSU
            net.hops[(start, end)] = h

    # ---- 4) smallest total delay between every pair (Dijkstra over fibre links) ----
    for start in net.rsus:                             # run Dijkstra from every RSU
        best = {start: 0.0}                            # RSU -> smallest delay found so far
        heap = [(0.0, start)]                          # (delay, RSU) ordered by delay
        while heap:                                    # until all reachable RSUs are finalised
            d, cur = heapq.heappop(heap)               # RSU with the smallest delay
            if d > best[cur]:                          # an old, worse entry -> skip it
                continue
            for nb, w in net.fibre[cur].items():       # relax every neighbour
                nd = d + w                             # delay via cur
                if nd < best.get(nb, float("inf")):    # better than what we had?
                    best[nb] = nd                      # update
                    heapq.heappush(heap, (nd, nb))     # and explore from it
        for end, d in best.items():                    # save the result
            net.path_delay_ms[(start, end)] = d

    return net                                         # give the finished network to the caller
