"""Tes untuk evaluasi Fase 6: metrik, jalur CSI sempurna, dan B3/B4."""

from __future__ import annotations

import dataclasses
import sys
from pathlib import Path

import numpy as np
import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from risisac.channels.database import database_path                  # noqa: E402
from risisac.config import channel_config_hash, load_config          # noqa: E402
from risisac.env import TrajectoryStore                              # noqa: E402

from risisac.baselines.env_policy import (OracleEnvPolicy, _weights_to_raw,
                                          episode_length, episode_snapshot,
                                          precompute_oracle)
from risisac.env import EnvConfig, RisIsacEnv                         # noqa: E402
from risisac.eval import metrics                                     # noqa: E402


@pytest.fixture(scope="module")
def cfg_base():
    return load_config("base")


@pytest.fixture(scope="module")
def store_test(cfg_base):
    path = database_path(cfg_base, channel_config_hash(cfg_base),
                         root=REPO / cfg_base["paths"]["channel_db"])
    if not path.exists():
        pytest.skip(f"basis data kanal belum ada: {path}")
    return TrajectoryStore(path, "test")


# ------------------------------------------------------------------ metrik
def test_track_duration_berhenti_di_pelanggaran_pertama():
    err = [0.1, 0.2, 7.0, 0.1, 0.1]
    durasi, tersensor = metrics.track_duration(err, dt_s=0.1, sigma_max_m=5.0)
    assert durasi == pytest.approx(0.2)
    assert tersensor is False


def test_track_duration_penuh_bila_tidak_pernah_hilang():
    err = [0.1] * 7
    durasi, tersensor = metrics.track_duration(err, dt_s=0.1, sigma_max_m=5.0)
    assert durasi == pytest.approx(0.7)
    assert tersensor is True


def test_track_duration_nol_bila_hilang_di_langkah_pertama():
    durasi, tersensor = metrics.track_duration([9.0, 0.1], 0.1, 5.0)
    assert durasi == 0.0 and tersensor is False


def test_pemulihan_tidak_menyambung_track():
    """Track yang hilang lalu pulih tetap berakhir di pelanggaran pertama."""
    durasi, _ = metrics.track_duration([0.1, 9.0, 0.1, 0.1, 0.1], 0.1, 5.0)
    assert durasi == pytest.approx(0.1)


def test_ecdf_naik_dari_1_per_n_sampai_1():
    x, f = metrics.ecdf([3.0, 1.0, 2.0])
    assert list(x) == [1.0, 2.0, 3.0]
    assert f[0] == pytest.approx(1 / 3) and f[-1] == pytest.approx(1.0)


def test_cluster_bootstrap_memusat_di_rata_rata_antar_seed():
    """Titik estimasinya rata-rata ANTAR-seed, bukan rata-rata semua episode.

    Dengan jumlah episode tak seimbang per seed, keduanya berbeda; yang
    diminta §9 adalah yang pertama.
    """
    values = np.array([0.0, 0.0, 0.0, 10.0])
    seeds = np.array([0, 0, 0, 1])
    out = metrics.cluster_bootstrap(values, seeds, n_boot=200, seed=0)
    assert out["mean"] == pytest.approx(5.0)
    assert out["n_seeds"] == 2 and out["n_episodes"] == 4


def test_cluster_bootstrap_ci_melingkupi_titik_estimasi():
    rng = np.random.default_rng(0)
    values = rng.normal(5.0, 1.0, 90)
    seeds = np.repeat([0, 1, 2], 30)
    out = metrics.cluster_bootstrap(values, seeds, n_boot=500, seed=1)
    assert out["ci_low"] < out["mean"] < out["ci_high"]


def test_welch_ttest_tanda_dan_cohen_d():
    a = [5.0, 5.1, 4.9]
    b = [3.0, 3.1, 2.9]
    out = metrics.welch_ttest(a, b)
    assert out["diff"] == pytest.approx(2.0, abs=1e-9)
    assert out["t"] > 0 and out["cohen_d"] > 0 and out["p"] < 0.05


# -------------------------------------------------- panjang episode & snapshot
def test_episode_length_cocok_dengan_env(store_test, cfg_base):
    """Panjang yang dihitung di muka harus sama dengan yang dijalankan env.

    B3 mengoptimalkan seluruh langkah episode sekaligus, jadi kalau perhitungan
    ini meleset ia akan memutar keputusan yang bergeser satu langkah.
    """
    env_cfg = dataclasses.replace(EnvConfig.from_config(cfg_base, "partial"),
                                  phase_update="absolute")
    env = RisIsacEnv(store_test, env_cfg, train=False, seed=7)
    for index in range(min(6, len(store_test))):
        env.reset(seed=7 + index, options={"trajectory_index": index})
        n = 0
        while True:
            _, _, term, trunc, _ = env.step(np.zeros(env_cfg.action_dim))
            n += 1
            if term or trunc:
                break
        assert n == episode_length(store_test[index], env_cfg)


def test_episode_snapshot_mengambil_langkah_yang_benar(store_test, cfg_base):
    env_cfg = EnvConfig.from_config(cfg_base, "partial")
    traj = store_test[0]
    snap = episode_snapshot(traj, store_test, env_cfg, 4)
    assert snap.batch == 4
    # Snapshot membalik sumbu (entitas, waktu) menjadi (waktu, entitas).
    assert np.allclose(snap.g_user[2], traj.user_g[:, 2, :])
    assert np.allclose(snap.g_tgt[3], traj.target_g[:, 3, :])
    assert np.allclose(snap.p_max_watt, env_cfg.p_max_eval_watt)


# ------------------------------------------------------------- bobot <-> aksi
def test_weights_to_raw_bolak_balik_lewat_softmax():
    from risisac.system.precoding import softmax

    w = np.array([0.7, 0.3])
    assert np.allclose(softmax(_weights_to_raw(w)), w)


def test_weights_to_raw_memusat_bobot_seimbang_ke_nol():
    """Pemusatan penting: env memotong aksi ke [-1, 1]."""
    assert np.allclose(_weights_to_raw(np.array([0.5, 0.5])), [0.0, 0.0])


# ------------------------------------------------------------- CSI sempurna
def test_perfect_csi_mematikan_derau_estimasi(store_test, cfg_base):
    """Dua env dengan seed sama: yang oracle harus memakai kanal sebenarnya."""
    base = dataclasses.replace(EnvConfig.from_config(cfg_base, "partial"),
                               phase_update="absolute")
    oracle = dataclasses.replace(base, perfect_csi=True)
    a = RisIsacEnv(store_test, base, train=False, seed=3)
    b = RisIsacEnv(store_test, oracle, train=False, seed=3)
    a.reset(seed=3, options={"trajectory_index": 0})
    b.reset(seed=3, options={"trajectory_index": 0})
    h_true = b._h_hat.copy()          # perfect_csi: h_hat == h sebenarnya
    assert not np.allclose(a._h_hat, h_true)

    # g_hat target: model LoS lawan g_t sebenarnya.
    assert np.allclose(b._estimated_target_channel(),
                       store_test[0].target_g[0, 0, :])
    assert not np.allclose(a._estimated_target_channel(),
                           store_test[0].target_g[0, 0, :])


def test_perfect_csi_default_mati(cfg_base):
    assert EnvConfig.from_config(cfg_base, "partial").perfect_csi is False


# ---------------------------------------------------------------- B3 dan B4
def test_b3_lewat_env_cocok_dengan_mesin_snapshot(store_test, cfg_base):
    """B3 lewat env harus memberi angka yang sama dengan mesin snapshot.

    Selisih yang tersisa hanyalah pemotongan bobot daya ke kotak aksi env;
    kalau selisihnya besar, berarti salah satu jalur keliru.
    """
    from risisac.eval.rollout import rollout_baseline, summarise

    env_cfg = EnvConfig.from_config(cfg_base, "partial")
    oracle_cfg = dataclasses.replace(env_cfg, phase_update="absolute",
                                     perfect_csi=True)
    indices = list(range(min(8, len(store_test))))
    out = precompute_oracle(store_test, cfg_base, env_cfg, indices, seed=0)
    env = RisIsacEnv(store_test, oracle_cfg, train=False, seed=11)
    got = summarise(rollout_baseline(env, OracleEnvPolicy(out["decisions"], 1),
                                     indices, 11))
    assert got["reward_per_step"] == pytest.approx(
        out["oracle_reward_per_step"], rel=0.01)
    assert got["detection_rate"] > 0.95


def test_b4_menahan_keputusan_selama_d_langkah(store_test, cfg_base):
    env_cfg = EnvConfig.from_config(cfg_base, "partial")
    oracle_cfg = dataclasses.replace(env_cfg, phase_update="absolute",
                                     perfect_csi=True)
    indices = [0]
    out = precompute_oracle(store_test, cfg_base, env_cfg, indices, seed=0)
    env = RisIsacEnv(store_test, oracle_cfg, train=False, seed=5)
    policy = OracleEnvPolicy(out["decisions"], 5)
    env.reset(seed=5, options={"trajectory_index": 0})
    policy.reset(env)
    actions = []
    for _ in range(5):
        action = policy.act(env)
        actions.append(action.copy())
        env.step(action)
    # Lima langkah pertama memakai keputusan langkah 0 yang sama persis.
    for action in actions[1:]:
        assert np.allclose(action, actions[0])


def test_b4_nama_mengikuti_periode():
    assert OracleEnvPolicy({}, 1).name == "B3"
    assert OracleEnvPolicy({}, 10).name == "B4-D10"


# --------------------------------------------------------------------- gambar
@pytest.fixture
def steps_dummy():
    """Tabel per langkah minimal: dua metode, dua seed, dua lintasan."""
    import pandas as pd

    rng = np.random.default_rng(0)
    rows = []
    for method, offset in (("M1", 0.0), ("B2", -2.0)):
        for train_seed in (0, 1):
            for index in (0, 1):
                for t in range(12):
                    rows.append({
                        "method": method, "train_seed": train_seed,
                        "noise_seed": 2000, "trajectory_index": index,
                        "step": t,
                        "reward": float(rng.normal(3 + offset, 0.5)),
                        "min_rate": float(rng.normal(8 + offset, 0.4)),
                        "scnr_db": float(rng.normal(14 + offset, 3.0)),
                        "detected": 1.0, "tracker_error_m": float(abs(rng.normal(0.3, 0.2))),
                        "rho": 0.1, "total_power": 1.0, "p_max_watt": 1.0,
                    })
    return pd.DataFrame(rows)


def test_f5_f6_menghasilkan_berkas(steps_dummy, tmp_path):
    from risisac.eval.plots import plot_f5_rate_cdf, plot_f6_episode

    f5 = plot_f5_rate_cdf(steps_dummy, tmp_path / "F5.png")
    f6 = plot_f6_episode(steps_dummy, tmp_path / "F6.png", 0,
                         methods=("B2", "M1"))
    assert f5.exists() and f5.stat().st_size > 0
    assert f6.exists() and f6.stat().st_size > 0


def test_f8_menggabung_label_titik_berdekatan(tmp_path):
    """Dua Gamma yang nyaris berimpit harus dilaporkan sebagai satu rentang."""
    from risisac.eval.plots import plot_f8_tradeoff

    points = [
        {"method": "B2", "gamma_db": 10.0, "min_rate": 2.0,
         "scnr_compliance": 0.997},
        {"method": "B2", "gamma_db": 16.0, "min_rate": 2.001,
         "scnr_compliance": 0.998},
        {"method": "M1", "gamma_db": 10.0, "min_rate": 8.4,
         "scnr_compliance": 0.57},
        {"method": "M1", "gamma_db": 16.0, "min_rate": 8.2,
         "scnr_compliance": 0.32},
    ]
    out = plot_f8_tradeoff(points, tmp_path / "F8.png")
    assert out.exists() and out.stat().st_size > 0


def test_episode_table_meringkas_per_episode(steps_dummy):
    table = metrics.episode_table(steps_dummy, dt_s=0.1, sigma_max_m=5.0,
                                  scnr_threshold_db=13.0)
    # 2 metode x 2 seed x 1 seed derau x 2 lintasan = 8 episode.
    assert len(table) == 8
    assert set(table["steps"]) == {12}
    assert table["track_censored"].all()
