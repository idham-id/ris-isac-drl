"""Tes geometri RIS. Konvensi di risisac.channels.geometry harus sama persis
dengan sionna.rt, jadi acuan tesnya adalah Sionna sendiri, bukan nilai hardcode.
"""

from __future__ import annotations

import numpy as np
import pytest

from risisac.channels.geometry import (PHASE_SIGN, focusing_phase_profile,
                                       look_at_angles, ris_element_positions,
                                       rotation_matrix, spherical_steering,
                                       wavelength_of)

sionna_rt = pytest.importorskip("sionna.rt")

FC = 3.5e9
WL = wavelength_of(FC)


@pytest.mark.parametrize("angles", [
    (0.0, 0.0, 0.0),
    (0.7, -0.3, 0.0),
    (2.625, 0.051, 0.0),
    (-1.1, 0.9, 0.4),
])
def test_rotation_matrix_matches_sionna(angles):
    import mitsuba as mi
    ours = rotation_matrix(angles)
    theirs = np.array(sionna_rt.rotation_matrix(
        mi.Point3f(*[float(v) for v in angles]))).reshape(3, 3)
    # Dr.Jit mengembalikan matriks dengan tata letak kolom; bandingkan keduanya.
    assert np.allclose(ours, theirs, atol=1e-6) or np.allclose(ours, theirs.T, atol=1e-6)


@pytest.mark.parametrize("target", [
    (1.0, 0.0, 0.0),
    (-0.868, 0.493, -0.051),
    (0.3, -0.9, 0.2),
])
def test_look_at_angles_matches_sionna(target):
    import mitsuba as mi
    ours = look_at_angles((0.0, 0.0, 0.0), target)
    theirs = np.array(sionna_rt.look_at_orientation(
        mi.Point3f(0.0, 0.0, 0.0),
        mi.Point3f(*[float(v) for v in target]))).ravel()[:3]
    assert np.allclose(ours, theirs, atol=1e-6)


def test_look_at_boresight_points_at_target():
    normal = np.array([-0.868, 0.493, -0.051])
    normal = normal / np.linalg.norm(normal)
    rot = rotation_matrix(look_at_angles((0, 0, 0), normal))
    assert np.allclose(rot @ np.array([1.0, 0.0, 0.0]), normal, atol=1e-6)


@pytest.mark.parametrize("rows,cols", [(1, 1), (2, 3), (8, 8), (12, 12)])
def test_element_positions_match_sionna(rows, cols):
    """Posisi dan URUTAN elemen harus identik: koefisien per elemen dari ray
    tracing dipasangkan ke profil fasa yang dihitung di sini lewat indeks m."""
    import mitsuba as mi
    center = np.array([9.9, 12.0, 6.0])
    normal = np.array([-0.868, 0.493, -0.051])

    ours = ris_element_positions(center, normal, rows, cols, WL, spacing=0.5)

    arr = sionna_rt.PlanarArray(num_rows=rows, num_cols=cols,
                                vertical_spacing=0.5, horizontal_spacing=0.5,
                                pattern="iso", polarization="V")
    target = center + normal / np.linalg.norm(normal)
    orient = sionna_rt.look_at_orientation(
        mi.Point3f(*[float(v) for v in center]),
        mi.Point3f(*[float(v) for v in target]))
    rot = arr.rotate(WL, orient)
    theirs = center[None, :] + np.stack(
        [np.array(rot.x), np.array(rot.y), np.array(rot.z)], axis=1)

    assert ours.shape == (rows * cols, 3)
    assert np.allclose(ours, theirs, atol=1e-6)


def test_element_spacing_is_half_wavelength():
    pos = ris_element_positions([0, 0, 10], [1, 0, 0], 4, 4, WL, spacing=0.5)
    d = np.linalg.norm(pos[1] - pos[0])      # m = j*rows + i, jadi 0 dan 1 sebaris kolom
    assert np.isclose(d, WL / 2, atol=1e-9)


def test_focusing_profile_aligns_phases():
    """Profil fokus harus membuat seluruh suku kaskade sefase."""
    center, normal = np.array([0.0, 0.0, 6.0]), np.array([1.0, 0.0, 0.0])
    src, tgt = np.array([-30.0, 5.0, 10.0]), np.array([25.0, -8.0, 1.5])
    pos = ris_element_positions(center, normal, 6, 6, WL)

    phi = focusing_phase_profile(pos, src, tgt, WL)
    a_in = spherical_steering(pos, src, WL)
    a_out = spherical_steering(pos, tgt, WL)
    terms = a_in * np.exp(1j * phi) * a_out

    # Semua suku harus punya fasa yang sama -> jumlahnya = jumlah magnitudo.
    assert np.isclose(np.abs(terms.sum()), np.sum(np.abs(terms)), rtol=1e-9)

    # Dan profil acak harus jelas lebih buruk.
    rng = np.random.default_rng(0)
    rand = a_in * np.exp(1j * rng.uniform(0, 2 * np.pi, len(pos))) * a_out
    assert np.abs(rand.sum()) < 0.5 * np.abs(terms.sum())


def test_phase_convention_matches_ray_tracing():
    """PHASE_SIGN diuji terhadap ray tracing, bukan diasumsikan.

    Dalam scene kosong (hanya LoS), fasa koefisien kanal per elemen harus
    mengikuti exp(PHASE_SIGN * j * k * r) sampai satu konstanta global.
    """
    import sionna.rt as rt

    xml = """<scene version="2.1.0">
      <bsdf type="itu-radio-material" id="m"><string name="type" value="concrete"/>
      <float name="thickness" value="0.1"/></bsdf>
    </scene>"""
    scene = rt.load_scene_from_string(xml)
    scene.frequency = FC

    rows = cols = 4
    center = np.array([0.0, 0.0, 10.0])
    normal = np.array([1.0, 0.0, 0.0])
    rx_point = np.array([37.0, 11.0, 1.5])

    scene.tx_array = rt.PlanarArray(num_rows=rows, num_cols=cols,
                                    vertical_spacing=0.5, horizontal_spacing=0.5,
                                    pattern="iso", polarization="V")
    scene.rx_array = rt.PlanarArray(num_rows=1, num_cols=1, pattern="iso",
                                    polarization="V")
    scene.add(rt.Transmitter("tx", position=[float(v) for v in center],
                             look_at=[float(v) for v in (center + normal)]))
    scene.add(rt.Receiver("rx", position=[float(v) for v in rx_point]))

    a, _ = rt.PathSolver()(scene, max_depth=0, synthetic_array=False).cir(out_type="numpy")
    measured = a[0, 0, 0, :, :, 0].sum(axis=-1)          # (M,)
    assert np.all(np.abs(measured) > 0), "tidak ada jalur LoS pada scene kosong"

    pos = ris_element_positions(center, normal, rows, cols, WL)
    predicted = spherical_steering(pos, rx_point, WL)

    # Buang konstanta global, lalu bandingkan pola fasa relatifnya.
    ratio = measured / predicted
    ratio = ratio / ratio[0]
    assert np.allclose(np.angle(ratio), 0.0, atol=1e-2), (
        f"PHASE_SIGN={PHASE_SIGN} tidak cocok dengan ray tracing; "
        f"sisa fasa (rad) = {np.angle(ratio)}"
    )
