"""Environment RL (docs/EXPERIMENT_DESIGN.md §5, docs/TASKS.md Fase 4).

Berkas ini membaca basis data kanal dan **dilewati** bila prakomputasi belum
dijalankan. Yang diuji adalah hal-hal yang menentukan apakah hasil pelatihan
bisa dipercaya: dimensi observasi sesuai §5.2, seed yang sama memberi
trajektori identik, reward benar-benar (E9) yang dihitung ulang dari ``info``,
dan kebijakan B2 lewat env sama dengan B2 langsung.
"""

import dataclasses
import sys
import warnings
from pathlib import Path

import numpy as np
import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from risisac.baselines import geometric                              # noqa: E402
from risisac.baselines.common import (Snapshot, SystemConstants,     # noqa: E402
                                      evaluate_decision)
from risisac.channels.database import database_path                  # noqa: E402
from risisac.config import channel_config_hash, load_config          # noqa: E402
from risisac.env import EnvConfig, RisIsacEnv, TrajectoryStore       # noqa: E402
from risisac.system import ris as ris_mod                            # noqa: E402
from risisac.system import signal_model as sm                        # noqa: E402


@pytest.fixture(scope="module")
def cfg():
    return load_config("base")


@pytest.fixture(scope="module")
def store(cfg):
    path = database_path(cfg, channel_config_hash(cfg),
                         root=REPO / cfg["paths"]["channel_db"])
    if not path.exists():
        pytest.skip(f"basis data kanal belum ada: {path}")
    return TrajectoryStore(path, "val")


def make_env(cfg, store, mode="partial", train=True, seed=0, **overrides):
    env_cfg = EnvConfig.from_config(cfg, mode)
    if overrides:
        env_cfg = dataclasses.replace(env_cfg, **overrides)
    return RisIsacEnv(store, env_cfg, train=train, seed=seed)


# ------------------------------------------------------------------ bentuk
def test_dimensi_sesuai_desain(cfg, store):
    """§5.2: 174 per frame (parsial); §5.3: aksi M + 1 + K = 67."""
    env = make_env(cfg, store)
    assert env.observation_space.shape == (174,)
    assert env.action_space.shape == (67,)
    full = make_env(cfg, store, mode="full")
    m = env.cfg.num_elements
    extra = 2 * m * (env.cfg.num_users + env.cfg.num_targets)
    assert full.observation_space.shape == (174 + extra,)
    assert extra == 384


def test_check_env_gymnasium(cfg, store):
    from gymnasium.utils.env_checker import check_env
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        for mode in ("partial", "full"):
            check_env(make_env(cfg, store, mode=mode), skip_render_check=True)


def test_api_lima_nilai_dan_observasi_hingga(cfg, store):
    env = make_env(cfg, store)
    obs, info = env.reset(seed=1)
    assert obs.shape == env.observation_space.shape and obs.dtype == np.float32
    assert np.all(np.isfinite(obs))
    out = env.step(env.action_space.sample())
    assert len(out) == 5
    obs, reward, terminated, truncated, info = out
    assert np.all(np.isfinite(obs)) and np.isfinite(reward)
    assert terminated is False and isinstance(truncated, bool)


# ------------------------------------------------------------ determinisme
def test_seed_sama_memberi_trajektori_identik(cfg, store):
    def rollout(seed):
        env = make_env(cfg, store, seed=seed)
        obs, _ = env.reset(seed=seed)
        rng = np.random.default_rng(0)
        frames, rewards = [obs], []
        for _ in range(12):
            a = rng.uniform(-1, 1, env.action_space.shape[0])
            obs, r, _, trunc, _ = env.step(a)
            frames.append(obs)
            rewards.append(r)
            if trunc:
                break
        return np.array(frames), np.array(rewards)

    a_obs, a_rew = rollout(7)
    b_obs, b_rew = rollout(7)
    assert np.array_equal(a_obs, b_obs)
    assert np.array_equal(a_rew, b_rew)
    c_obs, _ = rollout(8)
    assert not np.array_equal(a_obs, c_obs)


# ------------------------------------------------------------- reward (E9)
def test_reward_sama_dengan_e9_dari_info(cfg, store):
    """Reward harus bisa dihitung ulang dari ``info`` -- kalau tidak, metrik
    yang dilaporkan dan yang dioptimalkan bukan besaran yang sama."""
    env = make_env(cfg, store)
    env.reset(seed=3)
    rng = np.random.default_rng(1)
    for _ in range(25):
        obs, reward, _, trunc, info = env.step(rng.uniform(-1, 1, 67))
        expected = sm.reward(info["min_rate"], info["scnr_db"],
                             env.cfg.scnr_threshold_db, env.cfg.reward_lambda,
                             env.cfg.hinge_scale_db)
        assert reward == pytest.approx(float(expected), rel=1e-12)
        assert info["min_rate"] == pytest.approx(float(np.min(info["rates"])))
        assert reward == pytest.approx(info["reward_rate_term"]
                                       - info["reward_penalty_term"], rel=1e-12)
        if trunc:
            break


def test_anggaran_daya_dipenuhi_tiap_langkah(cfg, store):
    env = make_env(cfg, store)
    env.reset(seed=4)
    rng = np.random.default_rng(2)
    for _ in range(20):
        _, _, _, trunc, info = env.step(rng.uniform(-1, 1, 67))
        assert info["total_power"] == pytest.approx(info["p_max_watt"], rel=1e-9)
        if trunc:
            break


def test_hukuman_nol_saat_terdeteksi(cfg, store):
    env = make_env(cfg, store)
    env.reset(seed=5)
    rng = np.random.default_rng(3)
    for _ in range(30):
        _, reward, _, trunc, info = env.step(rng.uniform(-1, 1, 67))
        if info["detected"]:
            assert info["reward_penalty_term"] == pytest.approx(0.0)
            assert reward == pytest.approx(info["min_rate"])
        else:
            assert info["reward_penalty_term"] > 0.0
        if trunc:
            break


# --------------------------------------------------------- episode (§5.5)
def test_episode_terpotong_saat_target_keluar_roi(cfg, store):
    env = make_env(cfg, store, train=False)
    for index in range(len(store)):
        env.reset(seed=index, options={"trajectory_index": index})
        traj = store[index]
        expected = min(int(traj.target_in_roi[0].sum()), env.cfg.episode_steps)
        steps = 0
        while True:
            _, _, term, trunc, _ = env.step(np.zeros(67))
            steps += 1
            assert term is False          # hanya truncation, tidak pernah termination
            if trunc:
                break
        assert steps == expected


def test_p_max_diacak_saat_latih_dan_tetap_saat_eval(cfg, store):
    train = make_env(cfg, store, train=True)
    values = set()
    for s in range(8):
        train.reset(seed=s)
        values.add(float(train._p_max))
    assert len(values) > 1
    lo, hi = train.cfg.p_max_train_range_watt
    assert all(lo <= v <= hi for v in values)

    ev = make_env(cfg, store, train=False)
    for s in range(4):
        ev.reset(seed=s)
        assert ev._p_max == pytest.approx(ev.cfg.p_max_eval_watt)


# ------------------------------------------------------------- aksi (§5.3)
def test_fasa_inkremental_terbatas_per_langkah(cfg, store):
    """|phi_t - phi_{t-1}| <= kappa pi: aksi hanya MENGGESER fasa."""
    env = make_env(cfg, store)
    env.reset(seed=9)
    rng = np.random.default_rng(4)
    for _ in range(10):
        before = env._phi_prev.copy()
        _, _, _, trunc, _ = env.step(rng.uniform(-1, 1, 67))
        delta = np.angle(np.exp(1j * (env._phi_prev - before)))
        assert np.max(np.abs(delta)) <= env.cfg.phase_step_kappa * np.pi + 1e-9
        if trunc:
            break


def test_mode_absolut_tidak_terbatas(cfg, store):
    env = make_env(cfg, store, phase_update="absolute")
    env.reset(seed=9)
    before = env._phi_prev.copy()
    env.step(np.concatenate([np.ones(64), [0.0, 0.0, 0.0]]))
    assert np.max(np.abs(np.angle(np.exp(1j * (env._phi_prev - before))))) > \
        env.cfg.phase_step_kappa * np.pi


def test_rho_dan_bobot_daya_dari_aksi(cfg, store):
    env = make_env(cfg, store)
    env.reset(seed=11)
    _, _, _, _, info = env.step(np.concatenate([np.zeros(64), [1.0], [0.0, 0.0]]))
    assert info["rho"] == pytest.approx(1.0)
    assert np.allclose(info["power_weights"], 0.5)


# ------------------------------------------------- kebijakan B2 lewat env
def test_kebijakan_b2_lewat_env_sama_dengan_b2_langsung(cfg, store):
    """Tanpa galat estimasi, env dan mesin evaluasi baseline harus sama persis.

    Kalau tidak, perbandingan agen lawan baseline membandingkan dua jalur
    hitung yang berbeda, dan selisihnya bukan selisih kebijakan.
    """
    env = make_env(cfg, store, train=False, eff_channel_nmse=0.0)
    env.reset(seed=0, options={"trajectory_index": 0})
    traj = store[0]
    t = 0

    omega = np.concatenate([np.full(env.cfg.num_users, 0.125), [0.75]])
    g_hat_tgt = env._estimated_target_channel()[None, :]
    g_hat_user = traj.user_g[:, t, :][None, ...].astype(np.complex128)
    g_hat = np.concatenate([g_hat_user, g_hat_tgt[:, None, :]], axis=1)
    phi = geometric.phases(g_hat, env._G, omega)[0]
    rho, weights = 0.3, np.full(env.cfg.num_users, 0.5)

    # Aksi yang menghasilkan phi tepat ini pada mode absolut.
    env_abs = make_env(cfg, store, train=False, eff_channel_nmse=0.0,
                       phase_update="absolute")
    env_abs.reset(seed=0, options={"trajectory_index": 0})
    # g_hat diambil SEBELUM step: env membangun beam sensing dari state tracker
    # pada awal langkah, lalu memperbarui tracker di akhir langkah (§5.1).
    g_hat_step = env_abs._estimated_target_channel()[None, :]
    delta = phi / np.pi - 1.0
    rho_raw = 2.0 * rho - 1.0
    action = np.concatenate([delta, [rho_raw], np.zeros(env.cfg.num_users)])
    _, reward, _, _, info = env_abs.step(action)
    assert np.allclose(ris_mod.absolute_update(delta), phi)

    snap = Snapshot(
        G=env._G, H=env._H, Hc=env._Hc,
        hd_user=traj.user_hd[:, t, :][None, ...].astype(np.complex128),
        g_user=traj.user_g[:, t, :][None, ...].astype(np.complex128),
        hd_tgt_tx=traj.target_hd_tx[:, t, :][None, ...].astype(np.complex128),
        hd_tgt_rx=traj.target_hd_rx[:, t, :][None, ...].astype(np.complex128),
        g_tgt=traj.target_g[:, t, :][None, ...].astype(np.complex128),
        p_max_watt=np.array([env_abs._p_max]))
    const = SystemConstants.from_config(cfg)
    direct = evaluate_decision(snap, const, phi[None, :], np.array([rho]),
                               weights[None, :], g_hat_step)

    assert info["min_rate"] == pytest.approx(float(direct["min_rate"][0]), rel=1e-9)
    assert info["scnr_db"] == pytest.approx(float(direct["worst_scnr_db"][0]),
                                            rel=1e-9)
    assert reward == pytest.approx(float(direct["reward"][0]), rel=1e-9)


# ------------------------------------------------------------- kecepatan
def test_laju_langkah_memenuhi_gate_4(cfg, store):
    """Gate 4: >= 1.000 langkah/detik per proses."""
    import time

    env = make_env(cfg, store)
    env.reset(seed=0)
    rng = np.random.default_rng(0)
    actions = rng.uniform(-1, 1, (400, 67))
    t0 = time.perf_counter()
    n = 0
    for a in actions:
        _, _, _, trunc, _ = env.step(a)
        n += 1
        if trunc:
            env.reset()
    rate = n / (time.perf_counter() - t0)
    assert rate >= 1000.0, f"{rate:.0f} langkah/detik"
