"""PHASE 1 tests: attacker model, trust score, trust gate.  Run: pytest -v"""
import pytest
import config
from spavm.trust import TrustManager
from spavm.simulator import Simulator


def sim(mode, frac=0.2, amode="always", seed=3, slots=30):
    return Simulator(10, slots, 40, seed=seed, attack_fraction=frac, attack_mode=amode, trust_mode=mode)


# ---------- Step 1: attacker ----------
def test_p1_attacker_count_and_same_set_across_schemes():
    a, b = sim("none"), sim("gate")
    assert len(a.attacker.malicious) == 2
    assert a.attacker.malicious == b.attacker.malicious          # fair comparison


def test_p1_onoff_attacker_alternates():
    s = sim("none", amode="onoff")
    r = next(iter(s.attacker.malicious))
    P = config.ONOFF_PERIOD
    assert not s.attacker.attacking(r, 0) and s.attacker.attacking(r, P)


def test_p1_malicious_always_lies_honest_never():
    s = sim("none")
    bad = next(iter(s.attacker.malicious))
    good = next(r for r in range(10) if r not in s.attacker.malicious)
    assert s.attacker.self_report_healthy(bad, probe_failed=True) is True     # lie
    assert s.attacker.self_report_healthy(good, probe_failed=True) is False   # honest


# ---------- Step 2: trust score ----------
def test_p2_new_rsu_starts_neutral():
    assert TrustManager(1).T(0) == pytest.approx(0.5)


def test_p2_bad_evidence_lowers_trust_good_raises():
    t = TrustManager(2)
    for _ in range(5):
        t.add_good(0); t.add_bad(1); t.end_slot(False)
    assert t.T(0) > 0.8 and t.T(1) < 0.2


def test_p2_fast_to_lose_slow_to_gain():
    """After equal good and bad evidence, trust is below 0.5 because bad counts RHO x."""
    t = TrustManager(1)
    t.add_good(0); t.add_bad(0); t.end_slot(False)
    assert t.T(0) < 0.5


def test_p2_lie_costs_extra():
    liar, honest = TrustManager(1), TrustManager(1)
    liar.record_probe(0, failed=True, claimed_healthy=True)
    honest.record_probe(0, failed=True, claimed_healthy=False)
    liar.end_slot(False); honest.end_slot(False)
    assert liar.T(0) < honest.T(0) and liar.lies_caught == 1


def test_p2_blame_goes_mostly_to_less_trusted():
    t = TrustManager(2)
    t.a = [10.0, 0.0]; t.b = [0.0, 10.0]            # RSU0 trusted, RSU1 not
    t.record_outcome([0, 1], success=False)
    assert t._bad[1] > t._bad[0]


def test_p2_forgetting_lets_honest_rsu_recover():
    t = TrustManager(1)
    t.add_bad(0); t.end_slot(False)                  # one false alarm
    low = t.T(0)
    for _ in range(20):
        t.add_good(0); t.end_slot(False)
    assert t.T(0) > config.TRUST_THETA > low


# ---------- Step 3: trust gate ----------
def test_p3_unknown_rsu_gets_benefit_of_doubt():
    assert TrustManager(1).allowed(0)


def test_p3_low_trust_rsu_is_blocked():
    t = TrustManager(1)
    for _ in range(3):
        t.add_bad(0); t.end_slot(False)
    assert not t.allowed(0)


def test_p3_no_trust_mode_equals_plain_spavm():
    """With trust off, the attacker changes nothing about placement: same as baseline."""
    base = Simulator(10, 20, 40, seed=5).run().summary()
    att = Simulator(10, 20, 40, seed=5, attack_fraction=0.2, trust_mode="none").run().summary()
    for k in ("accepted", "reuse", "cold", "migrations", "D_total"):
        assert base[k] == att[k]


def test_p3_oracle_never_poisoned():
    assert sim("oracle").run().summary()["poisoned"] == 0


def test_p3_trust_reduces_poisoning():
    none = sim("none", slots=40).run().summary()["poisoned_rate"]
    gate = sim("gate", slots=40).run().summary()["poisoned_rate"]
    assert gate < none / 3


def test_p3_detects_all_always_bad_rsus():
    s = sim("gate", slots=40)
    s.run()
    assert all(v is not None for v in s.detect_slot.values())


def test_p3_resources_still_consistent_with_quarantine():
    s = sim("quarantine", slots=40)
    s.run()                                          # check_invariants runs every slot
    s.rm.check_invariants(s.containers)


def test_p0_phase1_does_not_overwrite_paper_parameters():
    """Guard: Phase 1 settings must not reuse names of SPAVM parameters (bug found: THETA clash)."""
    assert config.THETA == 2.0            # eq. 10 path-loss exponent
    assert config.MU_HOPS == 2


# ---------- Step 5: trust-based sharing limit (optional, off by default) ----------
def test_p5_sharing_limit_off_means_fixed_cap():
    s = sim("gate")
    assert s.share_cap(0) == config.MAX_SHARE


def test_p5_untested_rsu_gets_minimal_sharing():
    s = Simulator(10, 5, 40, seed=3, attack_fraction=0.2, trust_mode="gate", share_limit=True)
    assert s.share_cap(0) == config.SHARE_UNKNOWN


def test_p5_cap_grows_with_trust():
    s = Simulator(10, 5, 40, seed=3, attack_fraction=0.2, trust_mode="gate", share_limit=True)
    s.trust.a[0], s.trust.b[0] = 1000.0, 0.0        # almost fully trusted
    s.trust.a[1], s.trust.b[1] = 13.0, 7.0          # T just above threshold
    assert s.share_cap(0) == config.MAX_SHARE and s.share_cap(1) == 1
