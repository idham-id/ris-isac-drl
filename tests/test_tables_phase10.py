"""Tes untuk tabel dan metrik yang ditambahkan Fase 10.

Yang diuji di sini adalah hal-hal yang mudah SALAH DIAM-DIAM: fraksi
pelanggaran yang seharusnya persis satu dikurangi pemenuhan SCNR, shortfall
yang hanya dirata-ratakan atas langkah yang melanggar, dan tabel LaTeX yang
tetap menghasilkan sel ``--`` ketika tidak ada pelanggaran sama sekali.
Kesalahan pada ketiganya menghasilkan angka yang kelihatan masuk akal.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from risisac.eval import metrics, tables  # noqa: E402

GAMMA = 13.0


@pytest.fixture
def steps_two_methods():
    """Dua metode: 'TAAT' tidak pernah melanggar, 'LANGGAR' selalu 3 dB di bawah."""
    rows = []
    for method, scnr in (("TAAT", 20.0), ("LANGGAR", GAMMA - 3.0)):
        for seed in (0, 1, 2):
            for t in range(10):
                rows.append({
                    "method": method, "train_seed": seed, "noise_seed": 7,
                    "trajectory_index": 0, "step": t, "reward": 1.0,
                    "min_rate": 5.0 + 0.1 * t, "scnr_db": scnr,
                    "detected": 1.0, "tracker_error_m": 0.2,
                    "rho": 0.05 if method == "TAAT" else 0.2,
                    "total_power": 1.0, "p_max_watt": 1.0})
    return pd.DataFrame(rows)


def test_fraksi_pelanggaran_adalah_satu_dikurangi_pemenuhan(steps_two_methods):
    behaviour = metrics.behaviour_table(steps_two_methods, GAMMA)
    episodes = metrics.episode_table(steps_two_methods, dt_s=0.1,
                                     sigma_max_m=5.0, scnr_threshold_db=GAMMA)
    for method, group in episodes.groupby("method"):
        assert behaviour.loc[method, "violation_fraction"] == pytest.approx(
            1.0 - float(group["scnr_compliance"].mean()))


def test_shortfall_hanya_atas_langkah_yang_melanggar(steps_two_methods):
    behaviour = metrics.behaviour_table(steps_two_methods, GAMMA)
    # LANGGAR berada 3 dB di bawah ambang pada SETIAP langkah.
    assert behaviour.loc["LANGGAR", "mean_shortfall_db"] == pytest.approx(3.0)
    # TAAT tidak pernah melanggar: NaN, bukan 0 -- nol akan terbaca sebagai
    # "melanggar tepat di ambang".
    assert np.isnan(behaviour.loc["TAAT", "mean_shortfall_db"])
    assert behaviour.loc["TAAT", "violation_fraction"] == 0.0


def test_persentil_rate_berurutan(steps_two_methods):
    behaviour = metrics.behaviour_table(steps_two_methods, GAMMA)
    for method in behaviour.index:
        row = behaviour.loc[method]
        assert row["min_rate_p5"] <= row["min_rate_p10"] <= row["min_rate_p50"]


def test_urutan_baris_mengikuti_order_yang_diminta(steps_two_methods):
    behaviour = metrics.behaviour_table(steps_two_methods, GAMMA,
                                        order=("LANGGAR", "TAAT"))
    assert list(behaviour.index) == ["LANGGAR", "TAAT"]


def test_t5_mencetak_strip_untuk_shortfall_kosong(steps_two_methods):
    behaviour = metrics.behaviour_table(steps_two_methods, GAMMA)
    text = tables.t5_behaviour(behaviour, GAMMA)
    assert "\\begin{table}" in text and "tab:t5-behaviour" in text
    taat = [line for line in text.splitlines() if line.startswith("TAAT")][0]
    assert taat.rstrip().endswith("-- \\\\")


def test_panjang_episode_melaporkan_min_dan_maks():
    rows = []
    for index, length in ((0, 7), (1, 10)):
        for t in range(length):
            rows.append({"method": "A", "train_seed": 0, "noise_seed": 1,
                         "trajectory_index": index, "step": t, "reward": 0.0,
                         "min_rate": 1.0, "scnr_db": 20.0, "detected": 1.0,
                         "tracker_error_m": 0.1, "rho": 0.0,
                         "total_power": 1.0, "p_max_watt": 1.0})
    episodes = metrics.episode_table(pd.DataFrame(rows), dt_s=0.1,
                                     sigma_max_m=5.0, scnr_threshold_db=GAMMA)
    stats = metrics.episode_length_stats(episodes)
    assert (stats["min"], stats["max"]) == (7, 10)
    assert stats["mean"] == pytest.approx(8.5)
    assert stats["n_trajectories"] == 2
    assert stats["varies_within_trajectory"] == 0


def test_uji_welch_memakai_konvensi_kunci_yang_sama(steps_two_methods):
    episodes = metrics.episode_table(steps_two_methods, dt_s=0.1,
                                     sigma_max_m=5.0, scnr_threshold_db=GAMMA)
    out = metrics.pairwise_tests(episodes, pairs=(("TAAT", "LANGGAR"),),
                                 columns=("scnr_compliance",))
    assert list(out) == ["scnr_compliance|TAAT_vs_LANGGAR"]
    assert out["scnr_compliance|TAAT_vs_LANGGAR"]["diff"] == pytest.approx(1.0)


def test_label_profil_fasa_diterjemahkan():
    # fokus_0 adalah fokus PERTAMA: penomoran paper mulai dari 1.
    assert tables.profile_label("fokus_0") == "Focus 1"
    assert tables.profile_label("gradien") == "Gradient"
    assert tables.profile_label("tak_dikenal") == "tak_dikenal"


def test_tabel_baseline_memuat_semua_metode():
    text = tables.baselines_table()
    for key in ("B0", "B1", "B2", "B3", "A1-FullCSI", "M1", "M2"):
        assert tables.METHOD_LABELS[key] in text
    assert "B4 Oracle-GD-stale($D$)" in text
    # Kolom CSI harus menunjukkan bahwa A1-FullCSI TIDAK memakai CSI sempurna
    # untuk precoding; itu inti tabelnya.
    full = [line for line in text.splitlines()
            if line.startswith(tables.METHOD_LABELS["A1-FullCSI"])][0]
    assert r"Estimated $\hat{\mathbf{h}}_e$" in full


def test_tabel_parameter_menambahkan_baris_terukur():
    from risisac.config import load_config

    cfg = load_config("base")
    plain = tables.parameter_table(cfg)
    assert "test set: mean / min / max" not in plain
    with_stats = tables.parameter_table(
        cfg, {"mean": 36.92, "min": 18, "max": 50, "n_episodes": 2700,
              "n_trajectories": 50})
    assert "36.9 / 18 / 50 steps" in with_stats
    assert r"$\mu$ (hinge weight)" in with_stats
