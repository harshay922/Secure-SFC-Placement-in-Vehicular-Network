"""PHASE 2 tests: mobility attacker, confidence score, confidence-aware ingress, follow-me + storm guard.
Run: pytest -v"""
import ast
import math
import pathlib
import random
import config
from spavm.simulator import Simulator
from spavm.confidence import ConfidenceEngine, rssi_db
from spavm.model import Vehicle


def p2sim(mode="conf", frac=0.2, lmode="mixed", guard=False, seed=3, slots=20, n=20):
    return Simulator(n, slots, 4 * n, seed=seed, phase2=True, mobility_mode=mode,
                     liar_fraction=frac, liar_mode=lmode, storm_guard=guard)


# ---------- guard against the THETA-type bug ----------
def test_p2_config_has_no_duplicate_names():
    tree = ast.parse(pathlib.Path(config.__file__).read_text())
    names = []
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for t in node.targets:
                names += [e.id for e in (t.elts if isinstance(t, ast.Tuple) else [t]) if isinstance(e, ast.Name)]
    dup = {n for n in names if names.count(n) > 1}
    assert not dup, f"config names assigned twice: {dup}"


def test_p2_off_by_default_keeps_baseline():
    a = Simulator(10, 15, 40, seed=5).run().summary()
    assert a["misdirected"] == 0 and a["honest_flag_rate"] == 0.0 and a["sess_mig_per_slot"] == 0.0


# ---------- Step 1: attacker ----------
def test_p2_mixed_liars_cover_all_veremi_types():
    s = p2sim(frac=0.25)
    assert len(s.liars.kind) == 20 and set(s.liars.kind.values()) == {
        "const_pos", "const_offset", "random_pos", "random_offset", "eventual_stop"}


def test_p2_const_offset_uses_veremi_offset():
    s = p2sim(lmode="const_offset")
    vid = next(iter(s.liars.kind))
    v = next(x for x in s.vehicles if x.vid == vid)
    v.x, v.y = 300.0, 300.0
    assert s.liars.report(v) == (550.0, 150.0)


def test_p2_honest_reports_are_close_to_truth():
    s = p2sim(frac=0.0)
    v = s.vehicles[0]
    errs = [math.dist(s.liars.report(v), (v.x, v.y)) for _ in range(300)]
    assert sorted(errs)[len(errs) // 2] < 15            # typical error is GPS noise, not a lie


# ---------- Step 2: confidence ----------
def engine():
    s = p2sim(frac=0.0)
    return s, ConfidenceEngine(s.rsus, len(s.vehicles), random.Random(1))


def test_p2_rssi_falls_with_distance():
    assert rssi_db(10) > rssi_db(100) > rssi_db(300)


def test_p2_truthful_claim_scores_higher_than_far_claim():
    s, e = engine()
    r = s.rsus[0]
    true = (r.x + 60.0, r.y)
    heard = e.hearers(true)
    rec = min(heard, key=lambda h: h[1])[0]
    good = [e.score(1, true, true, heard, rec)[1]["signal"] for _ in range(50)]
    e2 = ConfidenceEngine(s.rsus, len(s.vehicles), random.Random(1))
    far_claim = (s.rsus[rec].x + 280.0, s.rsus[rec].y)
    bad = [e2.score(2, true, far_claim, heard, rec)[1]["signal"] for _ in range(50)]
    assert sum(good) / 50 > 0.7 > sum(bad) / 50


def test_p2_out_of_range_claim_is_impossible():
    s, e = engine()
    true = (s.rsus[0].x + 20.0, s.rsus[0].y)
    heard = e.hearers(true)
    rec = heard[0][0]
    claim = (s.rsus[rec].x + 5000.0, s.rsus[rec].y)
    assert e.score(3, true, claim, heard, rec)[1]["signal"] == 0.0


def test_p2_teleport_fails_speed_check():
    s, e = engine()
    true = (s.rsus[0].x, s.rsus[0].y)
    heard = e.hearers(true)
    e.score(4, true, (0.0, 0.0), heard, heard[0][0])
    parts = e.score(4, true, (2000.0, 0.0), heard, heard[0][0])[1]
    assert parts["physics"] < 0.1                        # 2 km in 5 s is impossible


def test_p2_confidence_separates_liars_from_honest():
    r = p2sim(slots=30).run().summary()
    assert r["liar_flag_rate"] > 0.7 and r["honest_flag_rate"] < 0.05


# ---------- Step 3: confidence-aware ingress ----------
def test_p2_spavm_sends_liars_to_unreachable_rsus():
    assert p2sim("none", slots=30).run().summary()["misdirected"] > 0


def test_p2_confidence_never_misdirects():
    assert p2sim("conf", slots=30).run().summary()["misdirected"] == 0


def test_p2_conf_ingress_only_uses_rsus_that_heard_the_vehicle():
    s = p2sim("conf")
    v = s.vehicles[0]
    heard = s.conf_engine.hearers((v.x, v.y))
    if heard:
        far = (0.0, 0.0) if math.dist((v.x, v.y), (0, 0)) > 600 else (s.side, s.side)
        rid, _ = s.ingress_for((v.x, v.y), far, heard[0][0], 0.99)
        assert rid in {h for h, _ in heard}


# ---------- Step 3b / 4: follow-me + storm guard ----------
def test_p2_oracle_followme_never_corrupted():
    assert p2sim("oracle", slots=30).run().summary()["sess_corrupt_rate"] == 0.0


def test_p2_random_position_liars_cause_storm_in_spavm():
    spavm = p2sim("none", frac=0.4, lmode="random_pos", slots=30).run().summary()
    oracle = p2sim("oracle", frac=0.4, lmode="random_pos", slots=30).run().summary()
    assert spavm["sess_mig_per_slot"] > 1.5 * oracle["sess_mig_per_slot"]


def test_p2_storm_guard_cuts_migrations():
    off = p2sim("conf", frac=0.4, lmode="random_pos", slots=30).run().summary()
    on = p2sim("conf", frac=0.4, lmode="random_pos", guard=True, slots=30).run().summary()
    assert on["sess_mig_per_slot"] < off["sess_mig_per_slot"]


def test_p2_resources_stay_consistent():
    s = p2sim("none", frac=0.4, lmode="const_pos", slots=30)
    s.run()                                              # check_invariants runs every slot
    s.rm.check_invariants(s.containers)
