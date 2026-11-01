# Removes the S3 rate filter completely (variables, conditions, outputs). Run: python remove_filter.py <code folder>
import sys, os, re
d = sys.argv[1]
def sub(f, a, b, must=True):
    p = os.path.join(d, f); s = open(p, encoding='utf-8').read()
    if a not in s:
        if must: raise SystemExit(f"NOT FOUND in {f}: {a[:70]!r}")
        return
    s = s.replace(a, b, 1); open(p, 'w', encoding='utf-8').write(s)

# ---- config.py ----
sub('config.py',
'''RATE_FILTER_PPS = 200                      # [CONFIRMED 25 Oct, value my choice] S3 rate filter at EVERY RSU access: a sender above
                                           # 200 packets/s is dropped (normal SFC <= 100 pkt/s, attacker 500) -> "DoS seen at this RSU"
''', '')
sub('config.py',
'''dict(detect=True,  reserve=False, scaleout=True,  migrate=True, ratefilter=True),   # + migration + rate filter''',
'''dict(detect=True,  reserve=False, scaleout=True,  migrate=True),   # + migration + re-association''')
p = os.path.join(d, 'config.py'); s = open(p, encoding='utf-8').read()
s = re.sub(r'\n    "S3_no_ratefilter":[^\n]*', '', s); open(p, 'w', encoding='utf-8').write(s)

# ---- simulator.py ----
sub('simulator.py',
'''        self.filter_on = bool(self.opts.get("ratefilter", False))   # S3: rate filter at every RSU access
        self.filtered_pkts = 0                                  # packets dropped by the rate filter
        self.filtered_cars = set()                              # normal cars cut by the filter this second (false drops)
        self.false_filter_s = 0                                 # car-seconds of normal cars wrongly cut by the filter
        self.dos_seen = {r: 0 for r in self.net.rsus}           # seconds in which the filter saw a DoS sender at each RSU
''', '')
sub('simulator.py',
'''        """Flood from 'senders' attackers at RSU r. With the S3 rate filter, a sender above RATE_FILTER_PPS is dropped
        at the RSU access (its packets never reach the queue) and the RSU records that it is under DoS."""
        if self.filter_on and pps_per_sender > cfg.RATE_FILTER_PPS:
            self.filtered_pkts += pps_per_sender * senders
            self.dos_seen[r] += 1
            return
        self.flood_pps[r]''',
'''        """Flood from 'senders' attackers at RSU r: their junk packets are added to the RSU's radio load."""
        self.flood_pps[r]''')
sub('simulator.py',
'''        per_car = {}                                            # packets/s sent by each normal car (all its SFCs)
''', '')
sub('simulator.py',
'''                per_car[s["req"]["car_id"]] = per_car.get(s["req"]["car_id"], 0) + s["req"]["pkt_rate_pps"]
        self.filtered_cars = set()
        if self.filter_on:                                      # a normal car with many SFCs could also cross the limit
            for car, pps in per_car.items():
                if pps > cfg.RATE_FILTER_PPS:
                    self.filtered_cars.add(car); self.false_filter_s += 1
''', '')
sub('simulator.py',
'''        if req.get("car_id") in self.filtered_cars:             # this car was cut by the rate filter (false drop)
            return math.inf
''', '')
sub('simulator.py',
'''            "filtered_pkts_millions": self.filtered_pkts / 1e6,
            "false_filter_car_s": self.false_filter_s,
            "rsus_dos_seen_by_filter": sum(v > 0 for v in self.dos_seen.values()),
''', '')

# ---- step11_graphs.py ----
sub('step11_graphs.py', '"S3 proposed (all layers + rate filter)"', '"S3 proposed (detection + scale-out + migration)"')
print("rate filter removed from", d)
