"""Filter Kalman kecepatan-konstan dan model galat pengukuran (§5.2)."""

import sys
from pathlib import Path

import numpy as np
import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from risisac.tracking import ConstantVelocityKalman, measurement_std  # noqa: E402

DT = 0.1


def make(sigma_a=1.0):
    return ConstantVelocityKalman(dt_s=DT, process_noise_std_mps2=sigma_a)


# ------------------------------------------------------ model galat (§5.2)
def test_sigma_pos_sama_dengan_sigma_ref_pada_ambang():
    assert measurement_std(13.0, 13.0, 0.5, 5.0) == pytest.approx(0.5)


def test_sigma_pos_mengecil_saat_scnr_naik():
    """sigma ~ sqrt(Gamma_lin / SCNR_lin): +20 dB SCNR -> sigma sepersepuluh."""
    assert measurement_std(33.0, 13.0, 0.5, 5.0) == pytest.approx(0.05)
    # Faktor 4 tepat butuh 20 log10(4) = 12,04 dB, bukan 12 dB bulat.
    assert measurement_std(13.0 + 20 * np.log10(4.0), 13.0, 0.5, 5.0) == \
        pytest.approx(0.5 / 4.0)


def test_sigma_pos_dibatasi_atas():
    """SCNR sangat rendah tidak boleh menghasilkan pengukuran tak terbatas."""
    assert measurement_std(-50.0, 13.0, 0.5, 5.0) == 5.0


def test_sigma_pos_monoton():
    values = [measurement_std(s, 13.0, 0.5, 5.0) for s in range(-10, 40, 2)]
    assert all(a >= b for a, b in zip(values, values[1:]))


# ----------------------------------------------------------------- prediksi
def test_prediksi_mengikuti_kecepatan_konstan():
    kf = make().initialize([1.0, 2.0], [3.0, -1.0])
    for _ in range(10):
        kf.predict()
    assert kf.position == pytest.approx([1.0 + 3.0 * 1.0, 2.0 - 1.0 * 1.0])
    assert kf.velocity == pytest.approx([3.0, -1.0])


def test_ketidakpastian_tumbuh_tanpa_pengukuran():
    """Target tak terdeteksi: filter hanya memprediksi, jadi makin tak yakin."""
    kf = make().initialize([0.0, 0.0], [1.0, 0.0])
    before = kf.position_std.copy()
    for _ in range(20):
        kf.step(detected=False)
    assert np.all(kf.position_std > before)


# ------------------------------------------------------------------ koreksi
def test_kovarians_tetap_simetris_dan_psd():
    rng = np.random.default_rng(0)
    kf = make().initialize([0.0, 0.0], [2.0, 0.0])
    for t in range(60):
        kf.predict()
        kf.update([2.0 * DT * t + rng.normal(0, 0.3), rng.normal(0, 0.3)], 0.3)
        assert np.allclose(kf.covariance, kf.covariance.T, atol=1e-12)
        assert np.min(np.linalg.eigvalsh(kf.covariance)) > -1e-12


def test_melacak_target_lurus_lebih_baik_daripada_pengukuran_mentah():
    """Nilai filter: galat posisi hasil filter < galat pengukuran mentah."""
    rng = np.random.default_rng(1)
    speed, sigma = 6.0, 0.5
    kf = make(0.5).initialize([0.0, 0.0], [0.0, 0.0], position_std_m=sigma)
    raw_err, filt_err = [], []
    for t in range(1, 80):
        truth = np.array([speed * DT * t, 0.0])
        z = truth + rng.normal(0, sigma, 2)
        kf.step(True, z, sigma)
        raw_err.append(np.linalg.norm(z - truth))
        filt_err.append(np.linalg.norm(kf.position - truth))
    assert np.mean(filt_err[20:]) < 0.6 * np.mean(raw_err[20:])


def test_pengukuran_lebih_tepat_lebih_dipercaya():
    """Galat kecil harus menarik state lebih dekat ke pengukuran."""
    far = make().initialize([0.0, 0.0], [0.0, 0.0], position_std_m=1.0)
    near = make().initialize([0.0, 0.0], [0.0, 0.0], position_std_m=1.0)
    far.step(True, [1.0, 0.0], 5.0)
    near.step(True, [1.0, 0.0], 0.05)
    assert near.position[0] > far.position[0]
    assert near.position[0] == pytest.approx(1.0, abs=0.05)


def test_step_butuh_pengukuran_saat_terdeteksi():
    with pytest.raises(ValueError, match="measurement_xy"):
        make().initialize([0.0, 0.0]).step(detected=True)


def test_derau_proses_nol_membuat_prediksi_eksak():
    kf = make(0.0).initialize([0.0, 0.0], [1.0, 2.0], position_std_m=0.0,
                              velocity_std_mps=0.0)
    kf.predict()
    assert kf.position == pytest.approx([DT, 2 * DT])
    assert np.allclose(kf.covariance, 0.0)
