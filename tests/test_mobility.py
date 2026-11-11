"""Lintasan target dan pengguna (docs/EXPERIMENT_DESIGN.md §2.3)."""

import sys
from pathlib import Path

import numpy as np
import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from risisac.config import load_config                                # noqa: E402
from risisac.mobility import (MobilitySpec, generate_split,           # noqa: E402
                              generate_trajectory, split_seed)
from risisac.mobility.trajectories import num_trajectories            # noqa: E402


@pytest.fixture(scope="module")
def cfg():
    return load_config("base")


@pytest.fixture(scope="module")
def spec(cfg):
    return MobilitySpec.from_config(cfg)


def test_bentuk_dan_jumlah(cfg, spec):
    tr = generate_trajectory(spec, "val", 0, split_seed(cfg, "val"))
    t, k, q = spec.episode_steps, spec.num_users, spec.num_targets
    assert tr.target_pos.shape == (q, t, 3)
    assert tr.target_vel.shape == (q, t, 3)
    assert tr.target_in_roi.shape == (q, t)
    assert tr.user_pos.shape == (k, t, 3)
    assert tr.all_positions().shape == ((q + k) * t, 3)


def test_split_sesuai_desain(cfg):
    """200 / 30 / 50, dan §4.3 memperkirakan ~42.000 titik penerima."""
    assert [num_trajectories(cfg, s) for s in ("train", "val", "test")] == [200, 30, 50]
    spec = MobilitySpec.from_config(cfg)
    total = sum(num_trajectories(cfg, s) for s in ("train", "val", "test"))
    assert total * spec.episode_steps * (spec.num_users + spec.num_targets) == 42_000


def test_determinisme_per_lintasan(cfg, spec):
    """Lintasan ke-i tidak boleh bergantung pada berapa banyak yang diminta.

    Ini yang membuat prakomputasi bisa dilanjutkan di tengah tanpa menggeser
    isi lintasan berikutnya.
    """
    seed = split_seed(cfg, "val")
    a = generate_trajectory(spec, "val", 7, seed)
    b = generate_trajectory(spec, "val", 7, seed)
    assert np.array_equal(a.target_pos, b.target_pos)
    assert np.array_equal(a.user_pos, b.user_pos)
    assert np.array_equal(a.target_in_roi, b.target_in_roi)
    assert a.target_speed_mps == pytest.approx(b.target_speed_mps)
    assert np.array_equal(generate_split(cfg, "val")[7].target_pos, a.target_pos)


def test_split_punya_seed_berbeda(cfg, spec):
    a = generate_trajectory(spec, "train", 0, split_seed(cfg, "train"))
    b = generate_trajectory(spec, "val", 0, split_seed(cfg, "val"))
    assert not np.array_equal(a.target_pos, b.target_pos)


def test_kecepatan_target_dalam_rentang(cfg, spec):
    lo, hi = spec.target_speed_mps
    speeds = np.array([t.target_speed_mps[0] for t in generate_split(cfg, "test")])
    assert speeds.min() >= lo and speeds.max() <= hi


def test_pengguna_di_trotoar_dan_di_dalam_roi(cfg, spec):
    """§2.1: pengguna ada di trotoar; ROI harus memuatnya (kanal tersedia)."""
    xmin, xmax, ymin, ymax = spec.roi_bounds
    sidewalk_x = np.concatenate([np.abs(p[:, 0]) for p in spec.sidewalks])
    lo, hi = sidewalk_x.min(), sidewalk_x.max()
    for tr in generate_split(cfg, "val"):
        p = tr.user_pos.reshape(-1, 3)
        assert np.all((p[:, 0] >= xmin) & (p[:, 0] <= xmax))
        assert np.all((p[:, 1] >= ymin) & (p[:, 1] <= ymax))
        assert np.all(np.abs(p[:, 0]) >= lo - 1e-9)      # tidak turun ke lajur
        assert np.all(np.abs(p[:, 0]) <= hi + 1e-9)


def test_pengguna_tidak_melebihi_kecepatan_pejalan_kaki(cfg, spec):
    lo, hi = spec.user_speed_mps
    for tr in generate_split(cfg, "val"):
        step = np.linalg.norm(np.diff(tr.user_pos, axis=1), axis=-1)
        assert step.max() <= hi * spec.dt_s + 1e-6


def test_target_selalu_di_dalam_kotak_roi(cfg, spec):
    """Posisi dijepit, sehingga tidak ada titik penerima di luar scene."""
    xmin, xmax, ymin, ymax = spec.roi_bounds
    for tr in generate_split(cfg, "val"):
        p = tr.target_pos.reshape(-1, 3)
        assert np.all((p[:, 0] >= xmin - 1e-6) & (p[:, 0] <= xmax + 1e-6))
        assert np.all((p[:, 1] >= ymin - 1e-6) & (p[:, 1] <= ymax + 1e-6))


def test_in_roi_monoton_turun(cfg, spec):
    """Sekali keluar ROI, episode terpotong: tidak boleh 'masuk lagi'."""
    for tr in generate_split(cfg, "val"):
        for mask in tr.target_in_roi:
            assert np.all(np.diff(mask.astype(int)) <= 0)
            assert mask[0]


def test_target_cepat_keluar_lebih_awal(cfg, spec):
    """Kendala fisik, bukan kebetulan: waktu di ROI ~ panjang ROI / kecepatan."""
    tr = generate_split(cfg, "test")
    speed = np.array([t.target_speed_mps[0] for t in tr])
    steps = np.array([t.target_in_roi[0].sum() for t in tr])
    assert np.corrcoef(speed, steps)[0, 1] < -0.5


def test_kecepatan_lateral_terbatas(cfg, spec):
    """Derau lateral harus berkorelasi waktu.

    Derau putih per langkah menghasilkan kecepatan lateral yang melonjak dan
    merusak asumsi kecepatan-konstan tracker Kalman (§5.2). Batas wajarnya
    adalah kecepatan perubahan lajur: jarak antar-lajur / durasi, dikali
    puncak turunan smoothstep (1,5).
    """
    lane_gap = max(spec.lane_x) - min(spec.lane_x)
    bound = 1.5 * lane_gap / spec.lane_change_duration_s
    for tr in generate_split(cfg, "val"):
        lateral = np.abs(tr.target_vel[..., 0])
        assert lateral.max() <= bound * 1.3


def test_kecepatan_konsisten_dengan_posisi(cfg, spec):
    tr = generate_trajectory(spec, "val", 2, split_seed(cfg, "val"))
    expected = (tr.target_pos[:, 1:] - tr.target_pos[:, :-1]) / spec.dt_s
    assert np.allclose(tr.target_vel[:, :-1], expected, atol=1e-9)
