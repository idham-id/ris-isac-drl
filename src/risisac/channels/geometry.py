"""Geometri RIS: posisi elemen di dunia, steering gelombang sferis, profil fokus.

docs/TASKS.md Fase 1, docs/EXPERIMENT_DESIGN.md §4.2.

Konvensi di sini WAJIB sama persis dengan ``sionna.rt.PlanarArray``, karena
koefisien kanal per elemen datang dari ray tracing Sionna sementara profil fasa
dihitung di sini. Yang sudah diverifikasi terhadap source Sionna 2.2
(``sionna/rt/antenna_array.py``) dan diuji ulang di ``tests/test_geometry.py``:

* Array terletak di bidang y-z lokal, boresight menghadap +x lokal.
* ``y = d_h * j - (num_cols - 1) * d_h / 2`` dengan j indeks kolom.
* ``z = -d_v * i + (num_rows - 1) * d_v / 2`` dengan i indeks baris.
* Elemen diurutkan ``m = j * num_rows + i`` (baris berubah paling cepat).
* Jarak dinyatakan dalam panjang gelombang, lalu dikali wavelength.

Konvensi fasa kanal (exp(-jkr) atau exp(+jkr)) TIDAK diasumsikan di sini:
``PHASE_SIGN`` ditetapkan dari pengukuran dan diuji di
``tests/test_geometry.py::test_phase_convention_matches_ray_tracing``.
"""

from __future__ import annotations

import numpy as np

SPEED_OF_LIGHT = 299792458.0

#: Tanda eksponen pada koefisien jalur: a ∝ exp(PHASE_SIGN * 1j * k * r).
#: Sionna RT memakai konvensi teknik exp(-jkr), jadi nilainya -1.
#: Diuji terhadap ray tracing sungguhan, bukan diasumsikan.
PHASE_SIGN = -1.0


def rotation_matrix(angles) -> np.ndarray:
    """Matriks rotasi 3x3 dari sudut (yaw, pitch, roll) = (alpha, beta, gamma).

    Sama dengan ``sionna.rt.rotation_matrix``; diuji di tests/test_geometry.py.
    """
    a, b, c = (float(v) for v in np.asarray(angles).ravel()[:3])
    ca, sa = np.cos(a), np.sin(a)
    cb, sb = np.cos(b), np.sin(b)
    cc, sc = np.cos(c), np.sin(c)
    return np.array([
        [ca * cb, ca * sb * sc - sa * cc, ca * sb * cc + sa * sc],
        [sa * cb, sa * sb * sc + ca * cc, sa * sb * cc - ca * sc],
        [-sb, cb * sc, cb * cc],
    ])


def look_at_angles(position, target) -> np.ndarray:
    """Sudut (yaw, pitch, roll) yang mengarahkan boresight +x lokal ke ``target``.

    Sama dengan ``sionna.rt.look_at_orientation``; roll selalu 0.
    """
    d = np.asarray(target, dtype=float).reshape(3) - np.asarray(position, dtype=float).reshape(3)
    r = np.linalg.norm(d)
    if r < 1e-12:
        raise ValueError("look_at_angles: target berimpit dengan position.")
    yaw = np.arctan2(d[1], d[0])
    pitch = -np.arcsin(np.clip(d[2] / r, -1.0, 1.0))
    return np.array([yaw, pitch, 0.0])


def ris_element_positions(center, normal, num_rows: int, num_cols: int,
                          wavelength: float, spacing: float = 0.5) -> np.ndarray:
    """Posisi elemen RIS di koordinat dunia, bentuk (M, 3) dengan M = rows*cols.

    :param center: (3,) pusat panel RIS
    :param normal: (3,) arah hadap panel (tidak harus unit)
    :param spacing: jarak antar elemen dalam panjang gelombang (0.5 = lambda/2)
    """
    center = np.asarray(center, dtype=float).reshape(3)
    normal = np.asarray(normal, dtype=float).reshape(3)
    n = np.linalg.norm(normal)
    if n < 1e-12:
        raise ValueError("ris_element_positions: normal adalah vektor nol.")

    angles = look_at_angles(center, center + normal / n)
    rot = rotation_matrix(angles)

    i = np.arange(num_rows)          # indeks baris -> z
    j = np.arange(num_cols)          # indeks kolom -> y
    jj, ii = np.meshgrid(j, i, indexing="ij")   # m = j * num_rows + i
    y = spacing * jj.ravel() - (num_cols - 1) * spacing / 2.0
    z = -spacing * ii.ravel() + (num_rows - 1) * spacing / 2.0

    local = np.stack([np.zeros_like(y), y, z], axis=1) * wavelength
    return center[None, :] + local @ rot.T


def spherical_steering(element_positions, point, wavelength: float,
                       include_amplitude: bool = False) -> np.ndarray:
    """Vektor steering gelombang sferis dari tiap elemen ke ``point``.

    Mengembalikan (M,) complex dengan ``exp(PHASE_SIGN * 1j * k * r)``, dikali
    ``1/r`` bila ``include_amplitude``. Model gelombang sferis (bukan bidang)
    dipakai karena pengguna dan target bisa berada di dalam jarak Fraunhofer
    RIS (docs/EXPERIMENT_DESIGN.md §4.2).
    """
    p = np.asarray(element_positions, dtype=float).reshape(-1, 3)
    q = np.asarray(point, dtype=float).reshape(3)
    r = np.linalg.norm(q[None, :] - p, axis=1)
    k = 2.0 * np.pi / wavelength
    out = np.exp(PHASE_SIGN * 1j * k * r)
    if include_amplitude:
        out = out / np.maximum(r, 1e-12)
    return out


def focusing_phase_profile(element_positions, source, target,
                           wavelength: float) -> np.ndarray:
    """Profil fasa RIS (M,) dalam [0, 2pi) yang memfokuskan ``source``->``target``.

    Kanal kaskade per elemen m sebanding dengan
    ``exp(PHASE_SIGN j k r_src,m) * exp(j phi_m) * exp(PHASE_SIGN j k r_tgt,m)``.
    Memilih ``phi_m = -PHASE_SIGN * k * (r_src,m + r_tgt,m)`` membuat seluruh
    suku sefase, sehingga amplitudonya menjumlah secara koheren.
    """
    p = np.asarray(element_positions, dtype=float).reshape(-1, 3)
    r_src = np.linalg.norm(np.asarray(source, dtype=float).reshape(3)[None, :] - p, axis=1)
    r_tgt = np.linalg.norm(np.asarray(target, dtype=float).reshape(3)[None, :] - p, axis=1)
    k = 2.0 * np.pi / wavelength
    return np.mod(-PHASE_SIGN * k * (r_src + r_tgt), 2.0 * np.pi)


def wavelength_of(frequency_hz: float) -> float:
    return SPEED_OF_LIGHT / float(frequency_hz)
