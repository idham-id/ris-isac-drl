"""B0 "No-RIS" (docs/EXPERIMENT_DESIGN.md §6.2, ditambahkan Fase 8).

B0 adalah **lantai** yang dipakai mengukur sumbangan RIS, jadi yang diuji di
sini bukan "apakah angkanya bagus" melainkan dua hal yang kalau salah akan
membuat seluruh klaim "RIS menambah sekian" keliru dan tetap terlihat masuk
akal:

1. kaskade RIS benar-benar hilang -- h_e sama **persis** dengan h_d, dan fasa
   RIS tidak berpengaruh sama sekali;
2. jalur env dan jalur snapshot memberi SINR dan SCNR yang sama, seperti yang
   sudah dijamin untuk B2 (``tests/test_env.py``) dan B3
   (``tests/test_eval.py``). Tanpa itu, B0 dibandingkan dengan metode lain
   lewat dua mesin hitung yang berbeda dan selisihnya bukan selisih sistem.
"""

from __future__ import annotations

import dataclasses
import sys
from pathlib import Path

import numpy as np
import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from risisac.baselines.common import (Snapshot, SystemConstants,     # noqa: E402
                                      evaluate_decision)
from risisac.baselines.env_policy import (NoRisEnvPolicy,            # noqa: E402
                                          make_baseline,
                                          power_weights_from_share)
from risisac.channels.database import database_path                  # noqa: E402
from risisac.config import channel_config_hash, load_config          # noqa: E402
from risisac.env import EnvConfig, RisIsacEnv, TrajectoryStore       # noqa: E402
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


def b0_env_config(cfg):
    base = EnvConfig.from_config(cfg, "partial")
    return dataclasses.replace(base, phase_update="absolute",
                               no_ris=True, perfect_csi=True)


# ------------------------------------------------------------------ bobot
def test_bobot_daya_dari_share_berjumlah_satu():
    for share in (0.25, 0.5, 0.75):
        for k in (2, 3, 4):
            w = power_weights_from_share(share, k)
            assert len(w) == k
            assert w.sum() == pytest.approx(1.0)
            assert w[0] == pytest.approx(share)


def test_b0_default_mati(cfg):
    """``no_ris`` harus mati secara default: agen tidak boleh kebagian."""
    assert EnvConfig.from_config(cfg, "partial").no_ris is False


# -------------------------------------------------- (1) kaskade benar hilang
def test_tanpa_ris_kanal_efektif_sama_persis_dengan_langsung(cfg, store):
    env = RisIsacEnv(store, b0_env_config(cfg), train=False, seed=0)
    env.reset(seed=0, options={"trajectory_index": 0})
    traj = store[0]
    hd = traj.user_hd[:, 0, :].astype(np.complex128)
    g = traj.user_g[:, 0, :].astype(np.complex128)
    rng = np.random.default_rng(0)
    for _ in range(5):
        phi = rng.uniform(0.0, 2.0 * np.pi, env.cfg.num_elements)
        got = env._effective_channel(hd, g, phi)
        assert np.array_equal(got, hd)

    # Kanal target juga: c = h_{d,t}, b = h^{(r)}_{d,t}.
    hd_tx = traj.target_hd_tx[:, 0, :].astype(np.complex128)
    hd_rx = traj.target_hd_rx[:, 0, :].astype(np.complex128)
    g_t = traj.target_g[:, 0, :].astype(np.complex128)
    c, b = env._target_channels(hd_tx, hd_rx, g_t, phi)
    assert np.array_equal(c, hd_tx)
    assert np.array_equal(b, hd_rx)

    # Dan dengan RIS menyala, ketiganya TIDAK sama -- kalau sama, berarti
    # basis data kanalnya yang kosong dan tes di atas tidak membuktikan apa pun.
    with_ris = dataclasses.replace(b0_env_config(cfg), no_ris=False)
    env_ris = RisIsacEnv(store, with_ris, train=False, seed=0)
    env_ris.reset(seed=0, options={"trajectory_index": 0})
    assert not np.allclose(env_ris._effective_channel(hd, g, phi), hd)


def test_fasa_ris_tidak_berpengaruh_pada_b0(cfg, store):
    """Dua fasa yang sangat berbeda harus memberi reward yang identik."""
    rewards, scnrs = [], []
    for value in (-1.0, +1.0):
        env = RisIsacEnv(store, b0_env_config(cfg), train=False, seed=3)
        env.reset(seed=3, options={"trajectory_index": 0})
        action = np.concatenate([np.full(env.cfg.num_elements, value),
                                 [0.0], np.zeros(env.cfg.num_users)])
        _, reward, _, _, info = env.step(action)
        rewards.append(reward)
        scnrs.append(info["scnr_db"])
    assert rewards[0] == pytest.approx(rewards[1], rel=1e-12)
    assert scnrs[0] == pytest.approx(scnrs[1], rel=1e-12)


# ------------------------------------------- (2) env sama dengan jalur snapshot
def test_b0_lewat_env_sama_dengan_jalur_snapshot(cfg, store):
    """Toleransi mengikuti tes B2 yang sudah ada: rel = 1e-9."""
    env = RisIsacEnv(store, b0_env_config(cfg), train=False, seed=0)
    env.reset(seed=0, options={"trajectory_index": 0})
    traj, t = store[0], 0

    rho, share = 0.3, 0.25
    weights = power_weights_from_share(share, env.cfg.num_users)
    policy = NoRisEnvPolicy(env.cfg.num_elements, env.cfg.num_users, rho, share)
    _, reward, _, _, info = env.step(policy.act(env))

    snap = Snapshot(
        G=env._G, H=env._H, Hc=env._Hc,
        hd_user=traj.user_hd[:, t, :][None, ...].astype(np.complex128),
        g_user=traj.user_g[:, t, :][None, ...].astype(np.complex128),
        hd_tgt_tx=traj.target_hd_tx[:, t, :][None, ...].astype(np.complex128),
        hd_tgt_rx=traj.target_hd_rx[:, t, :][None, ...].astype(np.complex128),
        g_tgt=traj.target_g[:, t, :][None, ...].astype(np.complex128),
        p_max_watt=np.array([env.p_max_watt]))
    direct = evaluate_decision(snap, SystemConstants.from_config(cfg),
                               np.zeros((1, env.cfg.num_elements)),
                               np.array([rho]), weights[None, :], no_ris=True)

    assert info["min_rate"] == pytest.approx(float(direct["min_rate"][0]),
                                             rel=1e-9)
    assert info["scnr_db"] == pytest.approx(float(direct["worst_scnr_db"][0]),
                                            rel=1e-9)
    assert np.allclose(info["sinr_db"], sm.to_db(direct["sinr"][0]), rtol=1e-9)
    assert reward == pytest.approx(float(direct["reward"][0]), rel=1e-9)


def test_b0_anggaran_daya_dipenuhi(cfg, store):
    env = RisIsacEnv(store, b0_env_config(cfg), train=False, seed=1)
    env.reset(seed=1, options={"trajectory_index": 1})
    policy = make_baseline("b0", cfg, env.cfg, seed=1,
                           rho=0.4, weight_share=0.5)
    for _ in range(5):
        _, _, _, trunc, info = env.step(policy.act(env))
        assert info["total_power"] <= info["p_max_watt"] * (1.0 + 1e-9)
        if trunc:
            break


def test_b0_lebih_buruk_daripada_ris_pada_lintasan_yang_sama(cfg, store):
    """Uji kewarasan: kalau B0 menang, premis seluruh paper yang salah.

    Pembandingnya fasa fokus geometris lewat RIS, bukan agen terlatih, supaya
    tes ini tidak bergantung pada hasil pelatihan mana pun.
    """
    from risisac.baselines import geometric

    def run(env_cfg, use_focus):
        env = RisIsacEnv(store, env_cfg, train=False, seed=7)
        env.reset(seed=7, options={"trajectory_index": 0})
        total, steps = 0.0, 0
        while True:
            if use_focus:
                ctx = env.baseline_context()
                g_hat = np.concatenate(
                    [env.trajectory.user_g[:, min(ctx["step"], 49), :]
                     [None, ...].astype(np.complex128),
                     ctx["g_hat_tgt"][None, None, :]], axis=1)
                omega = np.concatenate([np.full(env.cfg.num_users, 0.25),
                                        [0.5]])
                phi = geometric.phases(g_hat, env.G, omega)[0]
                delta = phi / np.pi - 1.0
            else:
                delta = np.zeros(env.cfg.num_elements)
            action = np.concatenate([delta, [0.0],
                                     np.zeros(env.cfg.num_users)])
            _, reward, _, trunc, _ = env.step(action)
            total += reward
            steps += 1
            if trunc:
                return total / steps

    b0 = run(b0_env_config(cfg), use_focus=False)
    ris = run(dataclasses.replace(b0_env_config(cfg), no_ris=False),
              use_focus=True)
    assert ris > b0, f"RIS {ris:+.3f} tidak mengalahkan B0 {b0:+.3f}"
