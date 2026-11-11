"""Kanal dari ray tracing (docs/TASKS.md Fase 2, docs/EXPERIMENT_DESIGN.md §4).

Tes di sini memanggil Sionna RT sungguhan, tetapi pada scene ruang bebas dan
array kecil, sehingga seluruh berkas selesai dalam beberapa detik. Yang diuji
adalah sifat yang gagal **diam-diam**: konvensi fasa, resiprositas, dan
pembuangan jalur LoS pada kanal clutter.
"""

import sys
from pathlib import Path

import numpy as np
import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from risisac.channels.geometry import (focusing_phase_profile,        # noqa: E402
                                       look_at_angles,
                                       ris_element_positions)
from risisac.channels.patterns import register_cosine_pattern         # noqa: E402
from risisac.channels.rt_extract import (RayTracingSettings,          # noqa: E402
                                         clutter_channel,
                                         narrowband_coefficients)
from risisac.channels.validate_analytic import (                      # noqa: E402
    free_space_los_coefficients, unit_cell_gain)
from risisac.config import load_config                                # noqa: E402
from risisac.scene.synthetic_l import load_free_space                 # noqa: E402
from risisac.system.signal_model import to_db, wavelength_of          # noqa: E402

FC = 3.5e9
WL = wavelength_of(FC)
TX = np.array([0.0, 0.0, 5.0])
RX = np.array([12.0, 4.0, 5.0])


@pytest.fixture(scope="module")
def rt():
    register_cosine_pattern()
    import sionna.rt as sionna_rt
    return sionna_rt


@pytest.fixture(scope="module")
def scene(rt):
    s = load_free_space()
    s.frequency = FC
    return s


@pytest.fixture(scope="module")
def settings():
    return RayTracingSettings(
        max_depth=3, samples_per_src=10_000, max_num_paths_per_src=100_000,
        max_paths_total=8_000_000, specular_reflection=True,
        diffuse_reflection=False, diffraction=False, synthetic_array=False,
        rx_batch_size=64)


def iso(rt, n=1):
    return rt.PlanarArray(num_rows=1, num_cols=n, vertical_spacing=0.5,
                          horizontal_spacing=0.5, pattern="iso", polarization="V")


def test_bentuk_dtype_dan_tanpa_nan(rt, scene, settings):
    points = np.array([[10.0, 0.0, 1.5], [15.0, 2.0, 1.5], [20.0, -3.0, 1.5]])
    a = narrowband_coefficients(scene, iso(rt, 4), iso(rt, 1), TX, points,
                                settings)
    assert a.shape == (3, 1, 4)
    assert a.dtype == np.complex128
    assert np.all(np.isfinite(a))
    assert np.all(np.abs(a) > 0)


def test_determinisme_seed_sama(rt, scene, settings):
    points = np.array([[10.0, 0.0, 1.5], [14.0, 1.0, 1.5]])
    a = narrowband_coefficients(scene, iso(rt, 2), iso(rt, 1), TX, points, settings)
    b = narrowband_coefficients(scene, iso(rt, 2), iso(rt, 1), TX, points, settings)
    assert np.array_equal(a, b)


def test_resiprositas(rt, scene, settings):
    """a(A->B) = a(B->A) untuk pola nyata berpolarisasi tunggal."""
    fwd = narrowband_coefficients(scene, iso(rt, 1), iso(rt, 1), TX,
                                  RX[None, :], settings)[0, 0, 0]
    rev = narrowband_coefficients(scene, iso(rt, 1), iso(rt, 1), RX,
                                  TX[None, :], settings)[0, 0, 0]
    assert abs(fwd - rev) <= 1e-9 * abs(fwd)


def test_friis_analitik_cocok_dengan_ray_tracing(rt, scene, settings):
    """Uji implementasi E0 versi cepat: 1 Tx iso -> beberapa titik iso.

    Menangkap kesalahan konvensi fasa dan penskalaan lambda/(4 pi r), yang
    tidak menimbulkan error apa pun tetapi menggeser seluruh hasil.
    """
    points = np.array([[8.0, 0.0, 5.0], [13.0, 5.0, 5.0], [25.0, -7.0, 5.0]])
    a = narrowband_coefficients(scene, iso(rt, 1), iso(rt, 1), TX, points,
                                settings)[:, 0, 0]
    an = free_space_los_coefficients(TX[None, :], points, WL)[:, 0]
    assert np.max(np.abs(to_db(np.abs(a) ** 2) - to_db(np.abs(an) ** 2))) < 0.01
    assert np.max(np.abs(np.angle(a * np.conj(an)))) < 1e-3


def test_pola_kosinus_ris_cocok_dengan_analitik(rt, scene, settings):
    """Indeks elemen dan orientasi panel RIS, bukan hanya penskalaan skalar."""
    rows, cols, sp = 2, 2, 0.5
    centre = np.array([0.0, 0.0, 6.0])
    look = centre + np.array([1.0, 0.2, 0.0])
    ris = rt.PlanarArray(num_rows=rows, num_cols=cols, vertical_spacing=sp,
                         horizontal_spacing=sp, pattern="cosine", polarization="V")
    points = np.array([[14.0, 3.0, 1.5], [20.0, -4.0, 1.5]])
    a = narrowband_coefficients(scene, ris, iso(rt, 1), centre, points,
                                settings, tx_look_at=look)[:, 0, :]

    xyz = ris_element_positions(centre, look - centre, rows, cols, WL, sp)
    an = free_space_los_coefficients(
        xyz, points, WL, tx_pattern="cosine", rx_pattern="iso",
        tx_orientation=look_at_angles(centre, look))
    assert np.max(np.abs(to_db(np.abs(a) ** 2) - to_db(np.abs(an) ** 2))) < 0.05
    assert np.max(np.abs(np.angle(a * np.conj(an)))) < 1e-2


def test_profil_fokus_menjumlah_koheren(rt, scene, settings):
    """focusing_phase_profile harus benar-benar menyefasekan kanal dari RT.

    Bila tanda fasa atau urutan elemen salah, jumlahnya jatuh jauh di bawah
    batas koheren sum|a_m| tanpa error apa pun.
    """
    rows, cols, sp = 4, 4, 0.5
    centre = np.array([0.0, 0.0, 6.0])
    look = centre + np.array([1.0, 0.0, 0.0])
    target = np.array([18.0, 2.0, 1.5])
    ris = rt.PlanarArray(num_rows=rows, num_cols=cols, vertical_spacing=sp,
                         horizontal_spacing=sp, pattern="cosine", polarization="V")
    # Sumber harus di DEPAN panel (+x lokal): pola kosinus nol di belakangnya,
    # sehingga sumber di belakang memberi G = 0 dan uji menjadi hampa.
    src = np.array([8.0, -9.0, 10.0])

    G = narrowband_coefficients(scene, iso(rt, 1), ris, src, centre[None, :],
                                settings, rx_look_at=look)[0][:, 0]      # (M,)
    g = narrowband_coefficients(scene, ris, iso(rt, 1), centre,
                                target[None, :], settings,
                                tx_look_at=look)[0, 0, :]                # (M,)
    xyz = ris_element_positions(centre, look - centre, rows, cols, WL, sp)
    phi = focusing_phase_profile(xyz, src, target, WL)

    per_element = G * g
    coherent = float(np.sum(np.abs(per_element)))
    achieved = float(np.abs(np.sum(per_element * np.exp(1j * phi))))
    assert achieved > 0.999 * coherent
    # Profil acak harus jauh lebih buruk: membuktikan uji di atas tidak sepele.
    rng = np.random.default_rng(0)
    random_phi = rng.uniform(0, 2 * np.pi, rows * cols)
    assert float(np.abs(np.sum(per_element * np.exp(1j * random_phi)))) < 0.6 * coherent


def test_fasa_absolut_dipertahankan(rt, scene, settings):
    """Koefisien harus membawa fasa propagasi exp(-j 2 pi r / lambda).

    Default Sionna ``normalize_delays=True`` menggeser tundaan tiap pasangan
    perangkat sehingga fasa link LoS menjadi tepat NOL. Fasa relatif
    antar-elemen tetap benar, jadi profil fokus dan peta cakupan tetap
    terlihat wajar -- kesalahannya hanya muncul saat menjumlahkan hasil dua
    pemanggilan yang berbeda, yaitu h_e = h_d + g^T Theta G (E2).
    """
    points = np.array([[10.0, 0.0, 5.0], [17.0, 0.0, 5.0], [31.0, 0.0, 5.0]])
    a = narrowband_coefficients(scene, iso(rt, 1), iso(rt, 1), TX, points,
                                settings)[:, 0, 0]
    r = np.linalg.norm(points - TX, axis=1)
    expected = np.angle(np.exp(-2j * np.pi * r / WL))
    assert np.max(np.abs(np.angle(np.exp(1j * (np.angle(a) - expected))))) < 1e-3
    assert np.max(np.abs(np.angle(a))) > 1e-3      # bukan nol karena normalisasi


def test_penjumlahan_antar_pemanggilan_koheren(rt, scene, settings):
    """Dua pemanggilan terpisah harus bisa dijumlahkan secara koheren.

    Kanal dari satu Tx ke satu titik, dihitung sekali utuh, harus sama dengan
    penjumlahan dua pemanggilan terpisah untuk dua sub-array Tx -- yang hanya
    benar bila fasa absolutnya dipertahankan.
    """
    point = np.array([[19.0, 6.0, 5.0]])
    centre = np.array([0.0, 0.0, 5.0])
    # PlanarArray memusatkan elemen pada posisi perangkat, jadi posisi elemen
    # diambil dari geometry, bukan diasumsikan.
    xyz = ris_element_positions(centre, point[0] - centre, 1, 2, WL, 0.5)
    both = narrowband_coefficients(scene, iso(rt, 2), iso(rt, 1), centre, point,
                                   settings, tx_look_at=point[0])[0, 0, :]
    separate = [narrowband_coefficients(scene, iso(rt, 1), iso(rt, 1), p, point,
                                        settings, tx_look_at=point[0])[0, 0, 0]
                for p in xyz]
    for got, want in zip(both, separate):
        assert abs(got - want) <= 1e-6 * abs(want)


def test_clutter_nol_di_ruang_bebas(rt, scene, settings):
    """**H**_c = 0 bila tidak ada apa pun yang memantulkan (§3.5).

    Sekaligus membuktikan jalur LoS tx-rx benar-benar dibuang: tanpa itu nilai
    ini akan besar, karena kedua panel BS hanya terpisah 0,5 m.
    """
    rx_pos = TX + np.array([0.0, 0.0, -0.5])
    hc = clutter_channel(scene, iso(rt, 2), iso(rt, 2), TX, rx_pos, settings)
    assert hc.shape == (2, 2)
    assert np.all(np.isfinite(hc))
    assert np.max(np.abs(hc)) == 0.0

    full = narrowband_coefficients(scene, iso(rt, 2), iso(rt, 2), TX,
                                   rx_pos[None, :], settings)[0]
    assert np.max(np.abs(full)) > 0.0      # jalur LoS-nya memang ada


def test_penguatan_sel_satuan_kosinus():
    """G = 2(alpha+1); pola kosinus proyek ini (alpha = 1) memberi 4."""
    assert unit_cell_gain(1.0) == pytest.approx(4.0)
    assert unit_cell_gain(3.0) == pytest.approx(8.0)
