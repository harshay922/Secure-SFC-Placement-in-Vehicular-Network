"""Your 20-point validation checklist as automatic tests.  Run: pytest -v"""
import math
import networkx as nx
import pytest
import config
from spavm import delay_cost as dc
from spavm.lyapunov import MigrationQueues
from spavm.model import VNFType, Vehicle, SFCRequest, Container
from spavm.simulator import Simulator
from spavm.workload import generate_requests

FA = VNFType(100, 2, 1.56, 2)
FB = VNFType(101, 2, 1.56, 2)


def stage_a(seed=config.SEED, **kw):
    return Simulator(**config.STAGES["A"], seed=seed, **kw)


def tiny_sim():
    """3 RSUs on a line 0-1-2, 200 m apart, no vehicles, no containers."""
    sim = Simulator(num_rsus=3, num_slots=1, num_vehicles=0, seed=1)
    for i, r in enumerate(sim.rsus):
        r.x, r.y = i * 200.0, 0.0
    sim.G = nx.path_graph(3)
    sim.hop = dict(nx.all_pairs_shortest_path_length(sim.G))
    return sim


def add(sim, f, rid):
    c = Container(sim.new_cid(), f, rid)
    sim.rm.reserve(rid, f.demand())
    sim.containers.append(c)
    return c


def req(chain, x=0.0, y=0.0):
    return SFCRequest(0, Vehicle(0, x, y, 0, 0), chain, 1e6)


# [1] network created correctly
def test_01_network_connected():
    for st in config.STAGES.values():
        sim = Simulator(**st, seed=3)
        assert nx.is_connected(sim.G) and len(sim.rsus) == st["num_rsus"]


# [2] RSU resources initialised
def test_02_rsu_resources_initialised():
    for r in stage_a().rsus:
        assert r.cap == {"cpu": 96, "mem": 100, "bw": 96}
        assert all(v == 0 for v in r.used.values())


# [3] SFC requests generated
def test_03_requests_generated():
    sim = stage_a()
    assert sum(len(generate_requests(sim.vehicles, sim.sfcs, sim.rng, 0)) for _ in range(50)) > 0


# [4] VNF requirements generated from paper's sets
def test_04_vnf_and_sfc_catalog():
    sim = stage_a()
    assert len(sim.vnfs) == config.NUM_VNF_TYPES
    for f in sim.vnfs:
        assert f.cpu in config.CPU_LEVELS and f.mem in config.MEM_LEVELS and f.bw in config.BW_LEVELS
    assert all(config.SFC_LEN_MIN <= len(c) <= config.SFC_LEN_MAX for c in sim.sfcs)


# [5] resource constraints working
def test_05_resource_constraint_blocks_overbooking():
    sim, big = tiny_sim(), VNFType(999, 97, 1.0, 1)
    assert not sim.rm.fits(0, big.demand())
    with pytest.raises(AssertionError):
        sim.rm.reserve(0, big.demand())


# [6] hop constraint working
def test_06_hop_constraint_blocks_far_container():
    sim, old = tiny_sim(), config.MU_HOPS
    config.MU_HOPS = 1
    try:
        far = add(sim, FA, 2)                     # 2 hops from RSU0
        p, _ = sim.spvir.place(req([FA]))
        assert p.steps[0][0] is not far and p.steps[0][1] is True
    finally:
        config.MU_HOPS = old


# [7][8] existing VNF detected + reuse working
def test_07_08_existing_vnf_is_reused():
    sim = tiny_sim()
    c = add(sim, FA, 0)
    p, _ = sim.spvir.place(req([FA]))
    assert p.steps[0][0] is c and p.steps[0][1] is False and len(sim.containers) == 1


# [9] new deployment working
def test_09_cold_start_when_no_container():
    sim = tiny_sim()
    p, _ = sim.spvir.place(req([FA]))
    assert p.steps[0][1] is True and len(sim.containers) == 1


# [10] failed requests handled (with rollback, no resource leak)
def test_10_rejection_and_rollback():
    sim = tiny_sim()
    for r in sim.rsus[1:]:
        r.used = dict(r.cap)
    sim.rsus[0].used = {"cpu": 94, "mem": 0.0, "bw": 0.0}     # room for FA only
    p, info = sim.spvir.place(req([FA, FB]))
    assert p is None and info == "cloud_infeasible"
    assert sim.containers == [] and sim.rsus[0].used["cpu"] == 94


def test_10b_out_of_coverage_goes_to_cloud():
    p, info = tiny_sim().spvir.place(req([FA], x=0.0, y=10_000.0))
    assert p is None and info == "cloud_uncovered"


# [11] delay calculated (hand-checked)
def test_11_delay_equations():
    d = 100.0
    rate = config.W * math.log2(1 + config.P_TX * config.H2 / (config.NOISE * d ** config.THETA))
    assert math.isclose(dc.tx_rate(d), rate) and math.isclose(dc.d_tra(1e6, d), 1e6 / rate)
    hop = {0: {0: 0, 1: 1, 2: 2}, 1: {0: 1, 1: 0, 2: 1}, 2: {0: 2, 1: 1, 2: 0}}
    assert dc.path_hops(0, [1, 0], hop) == 2 and dc.path_hops(0, [2, 2], hop) == 2
    assert math.isclose(dc.d_hop(3), 3 * config.D_HOP) and math.isclose(dc.d_dep(2), 2 * config.D_DEP)


# [12] cost calculated (hand-checked)
def test_12_cost_equations():
    assert math.isclose(dc.r_comp([FA, FB]), (FA.cpu + FB.cpu) * config.C_INST)
    assert math.isclose(dc.r_mig(2), 2 * config.C_MIG_PER_HOP)
    assert math.isclose(dc.r_keep(5), 5 * config.C_KEEP)


# [13] Lyapunov queue updated
def test_13_lyapunov_queue_update():
    q, C = MigrationQueues(2), config.MIG_BUDGET_C
    q.update([C + 3.0, 0.0])
    assert q.Q == pytest.approx([3.0, 0.0])
    q.update([0.0, 0.0])
    assert q.Q == pytest.approx([max(3.0 - C, 0.0), 0.0])


# [14][15][16][17] SPVIR + VIMA completed, migration performed, constraints checked
def loop_scenario():
    sim = tiny_sim()
    ca, _ = add(sim, FA, 1), add(sim, FB, 0)
    p, _ = sim.spvir.place(req([FA, FB]))           # path 0 -> 1 -> 0 : loop at RSU0
    assert [c.rsu for c, _ in p.steps] == [1, 0]
    return sim, p, ca


def test_14_16_vima_removes_loop():
    sim, p, ca = loop_scenario()
    moves, R = sim.vima.run([p])
    assert moves and ca.rsu == 0 and R[1] > 0
    sim.rm.check_invariants(sim.containers)


def test_17_vima_respects_capacity():
    sim, p, _ = loop_scenario()
    sim.rsus[0].used = dict(sim.rsus[0].cap)        # RSU0 full -> cannot receive
    moves, _ = sim.vima.run([p])
    assert all(nj != 0 for _, nj in moves)


def test_17b_vima_respects_queue_budget():
    """If RSU1's migration queue is already very large, VIMA should refuse to migrate from it."""
    sim, p, ca = loop_scenario()
    sim.queues.Q[1] = 1e6
    moves, _ = sim.vima.run([p])
    assert not moves and ca.rsu == 1


# [18] metrics recorded
def test_18_full_stage_a_run_and_metrics():
    m = stage_a().run()
    assert len(m.rows) == config.STAGES["A"]["num_slots"]
    s = m.summary()
    assert s["arrived"] == s["accepted"] + s["cloud_uncovered"] + s["cloud_infeasible"]


def test_18b_no_reuse_mode_never_reuses():
    s = stage_a(enable_reuse=False).run().summary()
    assert s["reuse"] == 0 and s["migrations"] == 0


# [19][20] reproducible + seed controlled
def test_19_reproducible_same_seed():
    assert stage_a(seed=7).run().rows == stage_a(seed=7).run().rows


def test_20_different_seed_differs():
    assert stage_a(seed=7).run().rows != stage_a(seed=8).run().rows
