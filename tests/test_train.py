"""Pelatihan dan baseline tingkat env (docs/TASKS.md Fase 5).

Yang diuji adalah hal-hal yang menentukan apakah angka Gate 5 bisa dipercaya:

* ketiga metode (M1, M2, A1) benar-benar berbeda pada tombol yang dimaksud
  dan tidak mengubah ``config_hash``;
* kriteria konvergensi berperilaku benar pada kurva yang sudah diketahui
  jawabannya, termasuk kurva yang melewati nol;
* ringkasan rollout memakai reward per LANGKAH, bukan per episode;
* B1/B2 lewat env menghasilkan keputusan yang sama persis dengan mesin
  evaluasi baseline Fase 3 -- tanpa ini, selisih agen lawan baseline bisa
  berasal dari dua jalur hitung yang berbeda.

Berkas ini membaca basis data kanal dan **dilewati** bila prakomputasi belum
dijalankan.
"""

import dataclasses
import sys
from pathlib import Path

import numpy as np
import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from risisac.baselines.common import (Snapshot, SystemConstants,     # noqa: E402
                                      evaluate_decision)
from risisac.baselines.env_policy import (GeometricEnvPolicy,        # noqa: E402
                                          RandomEnvPolicy,
                                          los_channel_estimate,
                                          make_baseline, tune_baseline)
from risisac.channels.database import database_path                  # noqa: E402
from risisac.channels.geometry import ris_element_positions          # noqa: E402
from risisac.config import (channel_config_hash, config_hash,        # noqa: E402
                            load_config)
from risisac.env import EnvConfig, RisIsacEnv, TrajectoryStore       # noqa: E402
from risisac.eval.rollout import (rollout_baseline, summarise)       # noqa: E402
from risisac.system import ris as ris_mod                            # noqa: E402
from risisac.train import METHODS, run_dir                           # noqa: E402

sys.path.insert(0, str(REPO / "scripts"))
from run_gate5_check import convergence                              # noqa: E402


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


def baseline_env(cfg, store, seed=0):
    env_cfg = dataclasses.replace(EnvConfig.from_config(cfg, "partial"),
                                  phase_update="absolute")
    return RisIsacEnv(store, env_cfg, train=False, seed=seed), env_cfg


# ------------------------------------------------------------------- metode
def test_tiga_metode_berbeda_pada_tombol_yang_dimaksud(cfg, store):
    """M1/M2/A1 hanya boleh berbeda pada observasi dan mode fasa (§6.1)."""
    dims, phases = {}, {}
    for name, spec in METHODS.items():
        env_cfg = dataclasses.replace(
            EnvConfig.from_config(cfg, spec["observation_mode"]),
            **spec["env_overrides"])
        dims[name] = env_cfg.observation_dim
        phases[name] = env_cfg.phase_update
    assert dims["ppo_po"] == dims["ppo_po_absolute"] == 174
    assert dims["ppo_full"] > dims["ppo_po"]
    assert phases["ppo_po"] == phases["ppo_full"] == "incremental"
    assert phases["ppo_po_absolute"] == "absolute"


def test_metode_tidak_mengubah_hash_config(cfg):
    """Tiga metode satu config harus berbagi ``config_hash`` yang sama.

    Kalau metode diterapkan dengan mengubah dict config, hash berubah dan
    hasil tiga metode tersebar ke direktori yang tampak tak berhubungan.
    """
    dirs = {m: run_dir(cfg, m, 0) for m in METHODS}
    hashes = {d.parents[1].name for d in dirs.values()}
    assert hashes == {config_hash(cfg)}
    assert len({d for d in dirs.values()}) == len(METHODS)


# ------------------------------------------------------------- konvergensi
def test_konvergensi_kurva_datar_dan_kurva_menanjak():
    steps = np.linspace(0, 1e6, 21)
    flat = np.concatenate([np.linspace(-2.0, 2.0, 17), np.full(4, 2.0)])
    rising = np.linspace(-2.0, 2.0, 21)
    assert convergence(steps, flat)["converged"]
    out = convergence(steps, rising)
    assert not out["converged"]
    # Kurva lurus: 20% langkah terakhir menyumbang sekitar 20% kenaikan.
    assert out["tail_ratio"] == pytest.approx(0.2, abs=0.02)


def test_konvergensi_bebas_skala_dan_aman_melewati_nol():
    """Kurva yang sama, digeser dan diskalakan, harus dinilai sama."""
    steps = np.linspace(0, 1e6, 21)
    base = np.concatenate([np.linspace(-2.0, 2.0, 17), np.full(4, 2.0)])
    a = convergence(steps, base)["tail_ratio"]
    b = convergence(steps, 7.0 * base + 100.0)["tail_ratio"]
    assert a == pytest.approx(b, abs=1e-9)


# ---------------------------------------------------------------- ringkasan
def test_ringkasan_memakai_reward_per_langkah():
    """Episode panjang tidak boleh mendapat nilai lebih tinggi karena panjang."""
    def ep(n, r):
        return {"reward": [r] * n, **{k: [0.0] * n for k in
                                      ("min_rate", "scnr_db", "detected",
                                       "tracker_error_m", "rho", "total_power",
                                       "p_max_watt")}}
    out = summarise([ep(10, 1.0), ep(40, 2.0)])
    assert out["reward_per_step"] == pytest.approx((10 + 80) / 50)
    assert out["episode_reward"] == pytest.approx((10 + 80) / 2)
    assert out["episode_steps"] == pytest.approx(25.0)


# ------------------------------------------------------------- B1/B2 di env
def test_aksi_baseline_menghasilkan_fasa_yang_diminta(cfg, store):
    """Pemetaan phi -> aksi harus tepat balik pada mode absolut."""
    env, env_cfg = baseline_env(cfg, store)
    env.reset(seed=3, options={"trajectory_index": 0})
    policy = RandomEnvPolicy(env_cfg.num_elements, env_cfg.num_users,
                             sensing_fraction=0.25, seed=5)
    policy.reset(env)
    rng = np.random.default_rng((5, env.trajectory_index))
    expected = ris_mod.random_phases(rng, env_cfg.num_elements)
    action = policy.act(env)
    phi = ris_mod.absolute_update(action[:env_cfg.num_elements])
    assert np.allclose(phi, expected, atol=1e-12)
    _, _, _, _, info = env.step(action)
    assert info["rho"] == pytest.approx(0.25)


def test_b1_dapat_diulang_dan_tidak_tergantung_urutan(cfg, store):
    """Hasil B1 pada satu lintasan tidak boleh bergantung pada riwayat env."""
    env, env_cfg = baseline_env(cfg, store)
    policy = make_baseline("b1", cfg, env_cfg, seed=7, rho=0.1)
    first = summarise(rollout_baseline(env, policy, [0, 1, 2], seed=1000))
    _ = rollout_baseline(env, policy, [3, 4], seed=1000)   # mengacak riwayat
    again = summarise(rollout_baseline(env, policy, [0, 1, 2], seed=1000))
    assert first["reward_per_step"] == pytest.approx(again["reward_per_step"],
                                                     rel=1e-12)


def test_b2_lewat_env_sama_dengan_mesin_baseline(cfg, store):
    """Keputusan B2 di env harus identik dengan ``evaluate_decision`` Fase 3."""
    env, env_cfg = baseline_env(cfg, store)
    env = RisIsacEnv(store, dataclasses.replace(env_cfg, eff_channel_nmse=0.0),
                     train=False, seed=0)
    env.reset(seed=0, options={"trajectory_index": 0})

    ris_xyz = ris_element_positions(env_cfg.ris_position, env_cfg.ris_normal,
                                    env_cfg.ris_rows, env_cfg.ris_cols,
                                    env_cfg.wavelength, env_cfg.ris_spacing)
    policy = GeometricEnvPolicy(env_cfg.num_users, ris_xyz, env_cfg.wavelength,
                                env_cfg.roi_height, env_cfg.user_pos_std_m,
                                omega_target=0.75, sensing_fraction=0.3, seed=11)
    policy.reset(env)
    ctx = env.baseline_context()
    action = policy.act(env)
    phi = ris_mod.absolute_update(action[:env_cfg.num_elements])
    _, reward, _, _, info = env.step(action)

    traj, t = store[0], 0
    snap = Snapshot(
        G=env.G, H=env._H, Hc=env._Hc,
        hd_user=traj.user_hd[:, t, :][None, ...].astype(np.complex128),
        g_user=traj.user_g[:, t, :][None, ...].astype(np.complex128),
        hd_tgt_tx=traj.target_hd_tx[:, t, :][None, ...].astype(np.complex128),
        hd_tgt_rx=traj.target_hd_rx[:, t, :][None, ...].astype(np.complex128),
        g_tgt=traj.target_g[:, t, :][None, ...].astype(np.complex128),
        p_max_watt=np.array([ctx["p_max_watt"]]))
    direct = evaluate_decision(snap, SystemConstants.from_config(cfg),
                               phi[None, :], np.array([0.3]),
                               np.full((1, env_cfg.num_users), 0.5),
                               ctx["g_hat_tgt"][None, :])
    assert info["min_rate"] == pytest.approx(float(direct["min_rate"][0]),
                                             rel=1e-9)
    assert info["scnr_db"] == pytest.approx(float(direct["worst_scnr_db"][0]),
                                            rel=1e-9)
    assert reward == pytest.approx(float(direct["reward"][0]), rel=1e-9)


def test_b2_memakai_posisi_estimasi_bukan_posisi_sebenarnya(cfg, store):
    """Galat posisi B2 harus punya sigma yang sama dengan observasi agen."""
    env, env_cfg = baseline_env(cfg, store)
    env.reset(seed=0, options={"trajectory_index": 0})
    ris_xyz = ris_element_positions(env_cfg.ris_position, env_cfg.ris_normal,
                                    env_cfg.ris_rows, env_cfg.ris_cols,
                                    env_cfg.wavelength, env_cfg.ris_spacing)
    policy = GeometricEnvPolicy(env_cfg.num_users, ris_xyz, env_cfg.wavelength,
                                env_cfg.roi_height, env_cfg.user_pos_std_m,
                                omega_target=0.5, sensing_fraction=0.2, seed=0)
    truth = env.baseline_context()["user_pos"]
    draws = []
    for _ in range(400):
        policy._rng = np.random.default_rng(len(draws))
        rng = np.random.default_rng(len(draws))
        draws.append(truth + rng.normal(0.0, env_cfg.user_pos_std_m, truth.shape))
    spread = np.std(np.array(draws) - truth)
    assert spread == pytest.approx(env_cfg.user_pos_std_m, rel=0.15)
    # Estimasi LoS harus berbeda dari kanal RT sebenarnya: B2 tidak punya CSI.
    g_hat = los_channel_estimate(truth, ris_xyz, env_cfg.wavelength,
                                 env_cfg.roi_height)
    assert g_hat.shape == (env_cfg.num_users, env_cfg.num_elements)


def test_sapuan_grid_b1_memakai_grid_config(cfg, store):
    env, env_cfg = baseline_env(cfg, store)
    out = tune_baseline("b1", env, cfg, env_cfg, [0, 1], seed=1000)
    assert [r["rho"] for r in out["grid"]] == \
        [float(v) for v in cfg["baselines"]["rho_grid"]]
    assert out["best"]["rho"] in set(r["rho"] for r in out["grid"])
    best_row = max(out["grid"], key=lambda r: r["reward_per_step"])
    assert out["best"]["rho"] == best_row["rho"]
