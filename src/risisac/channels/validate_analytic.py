"""Validasi ringan (E0) (docs/EXPERIMENT_DESIGN.md §4.5).

Tiga pemeriksaan pada **scene ruang bebas** (tanpa gedung dan tanah):

1. **Uji implementasi.** Koefisien kanal hasil Sionna RT dibandingkan dengan
   model Friis analitik per hop memakai pola elemen yang sama. Yang diuji
   adalah hal-hal yang gagal diam-diam: konvensi fasa, orientasi array, dan
   indeks elemen. Ambang < 0,1 dB.
2. **Kalibrasi fisika.** Penguatan kaskade dibandingkan dengan model path loss
   RIS berbasis fisika dari Tang dkk. (2021), IEEE TWC 20(1):421-439,
   Pers. (6) kasus *far-field beamforming*. Selisih konstannya dicatat sebagai
   ``calibration_db``.
3. **Per elemen vs synthetic array.** Dikerjakan di skrip E0, bukan di sini.

Model analitik di sini mengikuti persis pipeline Sionna 2.2
(``path_solvers/field_calculator.py``, diperiksa di versi terpasang):

* medan berangkat sebagai pola antena pancar (vektor Jones);
* rugi propagasi ruang bebas 1/r dikali 1/sqrt(4 pi);
* di penerima dikali ``wavelength / sqrt(4 pi)`` (akar luas efektif
  lambda^2/(4 pi)) lalu diproyeksikan ke pola antena terima dengan
  ``jones_vec_dot(u, v) = u^H v`` -- pola TERIMA yang dikonjugasi.

Sehingga, untuk satu jalur LoS,

    a = (lambda / (4 pi r)) * <C_rx, C_tx>_dunia * exp(PHASE_SIGN j 2 pi r / lambda)

dengan ``PHASE_SIGN`` dari ``channels.geometry`` (diuji terhadap ray tracing,
bukan diandaikan).
"""

from __future__ import annotations

import numpy as np

from .geometry import PHASE_SIGN, rotation_matrix

FOUR_PI = 4.0 * np.pi


def _spherical_angles(direction: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """(theta, phi) Sionna: theta dari +z, phi dari +x. ``direction`` (..., 3) unit."""
    d = np.asarray(direction, dtype=float)
    theta = np.arccos(np.clip(d[..., 2], -1.0, 1.0))
    phi = np.arctan2(d[..., 1], d[..., 0])
    return theta, phi


def _spherical_basis(theta: np.ndarray, phi: np.ndarray):
    """Vektor basis (theta_hat, phi_hat) di frame yang sama dengan sudutnya."""
    st, ct = np.sin(theta), np.cos(theta)
    sp, cp = np.sin(phi), np.cos(phi)
    theta_hat = np.stack([ct * cp, ct * sp, -st], axis=-1)
    phi_hat = np.stack([-sp, cp, np.zeros_like(sp)], axis=-1)
    return theta_hat, phi_hat


def evaluate_pattern(pattern_name: str, theta, phi, polarization: str = "V",
                     polarization_model: str = "tr38901_2") -> np.ndarray:
    """Vektor Jones (c_theta, c_phi) pola antena Sionna, bentuk (..., 2) complex.

    Dievaluasi lewat registry Sionna sendiri, bukan diimplementasikan ulang,
    supaya uji implementasi benar-benar menguji kode kita terhadap pola yang
    sama persis -- termasuk pola ``cosine`` yang kita daftarkan sendiri.
    """
    import drjit as dr          # noqa: F401  (dibutuhkan mitsuba)
    import mitsuba as mi
    from sionna.rt.antenna_pattern import antenna_pattern_registry

    theta = np.atleast_1d(np.asarray(theta, dtype=float))
    phi = np.atleast_1d(np.asarray(phi, dtype=float))
    shape = np.broadcast_shapes(theta.shape, phi.shape)
    theta_f = np.broadcast_to(theta, shape).ravel()
    phi_f = np.broadcast_to(phi, shape).ravel()

    factory = antenna_pattern_registry.get(pattern_name)
    pattern = factory(polarization=polarization,
                      polarization_model=polarization_model)
    if len(pattern.patterns) != 1:
        raise ValueError(
            f"polarisasi '{polarization}' memberi {len(pattern.patterns)} pola; "
            "model analitik ini hanya untuk polarisasi tunggal.")
    c_theta, c_phi = pattern.patterns[0](mi.Float(theta_f), mi.Float(phi_f))

    def to_numpy(c):
        return np.asarray(c.real) + 1j * np.asarray(c.imag)

    out = np.stack([to_numpy(c_theta), to_numpy(c_phi)], axis=-1)
    return out.reshape(shape + (2,))


def free_space_los_coefficients(tx_positions, rx_positions, wavelength: float,
                                tx_pattern: str = "iso", rx_pattern: str = "iso",
                                tx_orientation=(0.0, 0.0, 0.0),
                                rx_orientation=(0.0, 0.0, 0.0),
                                polarization: str = "V") -> np.ndarray:
    """Koefisien LoS ruang bebas analitik, bentuk (num_rx, num_tx) complex.

    Friis per hop dengan pola antena Sionna dan basis sferis dunia yang benar;
    lihat docstring modul untuk penurunannya dari source Sionna 2.2.

    :param tx_positions: (Nt, 3) posisi tiap elemen pancar
    :param rx_positions: (Nr, 3) posisi tiap elemen terima
    :param tx_orientation: (yaw, pitch, roll) frame lokal array pancar
    """
    tx = np.asarray(tx_positions, dtype=float).reshape(-1, 3)
    rx = np.asarray(rx_positions, dtype=float).reshape(-1, 3)
    rot_t = rotation_matrix(tx_orientation)
    rot_r = rotation_matrix(rx_orientation)

    delta = rx[:, None, :] - tx[None, :, :]            # (Nr, Nt, 3)
    r = np.linalg.norm(delta, axis=-1)
    if np.any(r < 1e-9):
        raise ValueError("free_space_los_coefficients: ada elemen berimpit.")
    u = delta / r[..., None]                           # arah rambat tx -> rx

    # Pola PANCAR dievaluasi pada arah berangkat, di frame lokal pemancar.
    u_t_local = u @ rot_t                              # = (rot_t^T u^T)^T
    theta_t, phi_t = _spherical_angles(u_t_local)
    c_t = evaluate_pattern(tx_pattern, theta_t, phi_t, polarization)
    th_t, ph_t = _spherical_basis(theta_t, phi_t)
    e_tx = (c_t[..., 0:1] * th_t + c_t[..., 1:2] * ph_t) @ rot_t.T   # ke dunia

    # Pola TERIMA dievaluasi pada arah DATANG (-u), di frame lokal penerima.
    u_r_local = (-u) @ rot_r
    theta_r, phi_r = _spherical_angles(u_r_local)
    c_r = evaluate_pattern(rx_pattern, theta_r, phi_r, polarization)
    th_r, ph_r = _spherical_basis(theta_r, phi_r)
    e_rx = (c_r[..., 0:1] * th_r + c_r[..., 1:2] * ph_r) @ rot_r.T

    # jones_vec_dot(u, v) = u^H v, dengan u pola terima.
    coupling = np.sum(np.conj(e_rx) * e_tx, axis=-1)
    phase = np.exp(PHASE_SIGN * 2j * np.pi * r / wavelength)
    return (wavelength / (FOUR_PI * r)) * coupling * phase


def unit_cell_gain(alpha: float = 1.0) -> float:
    """Penguatan sel satuan untuk pola daya ternormalisasi cos^alpha(theta).

    Integral cos^alpha atas setengah bola = 2 pi / (alpha + 1), sehingga
    G = 4 pi / (2 pi / (alpha + 1)) = 2 (alpha + 1). Untuk pola kosinus yang
    dipakai proyek ini (alpha = 1) nilainya 4, cocok dengan faktor 4 di
    ``channels/patterns.py``.
    """
    return 2.0 * (float(alpha) + 1.0)


def tang2021_beamforming_gain(d1: float, d2: float, wavelength: float,
                              num_rows: int, num_cols: int,
                              cell_dx: float, cell_dy: float,
                              gain_tx: float, gain_rx: float,
                              cell_gain: float,
                              f_tx: float = 1.0, f_rx: float = 1.0,
                              reflection_amplitude: float = 1.0) -> float:
    """Penguatan daya RIS kasus *far-field beamforming* (Tang dkk., 2021).

    Tang, W., Chen, M. Z., Chen, X., Xu, J., Alexandropoulos, G. C., Dai, L.,
    Di Renzo, M., Cheng, Q., & Cui, T. J. (2021). Wireless communications with
    reconfigurable intelligent surface: Path loss modeling and experimental
    measurement. *IEEE Transactions on Wireless Communications*, 20(1),
    421-439. https://doi.org/10.1109/TWC.2020.3024887

    Pers. (6) dalam bentuk path loss::

        PL = 64 pi^3 (d1 d2)^2
             / (G_t G_r G M^2 N^2 d_x d_y lambda^2 F(th_t,ph_t) F(th_r,ph_r) A^2)

    Fungsi ini mengembalikan kebalikannya, yaitu P_r / P_t. Berlaku bila
    pemancar dan penerima berada di medan jauh RIS; untuk RIS 8x8 pada 3,5 GHz
    jarak Fraunhofer-nya 3-6 m (§4.2), jauh di bawah d1 = 20 m dan d2 >= 10 m.

    :param f_tx: pola daya ternormalisasi sel satuan pada sudut datang
    :param f_rx: idem pada sudut pantul
    :param reflection_amplitude: A pada Gamma = A e^{j phi}
    """
    numerator = (float(gain_tx) * float(gain_rx) * float(cell_gain)
                 * (int(num_rows) * int(num_cols)) ** 2
                 * float(cell_dx) * float(cell_dy) * float(wavelength) ** 2
                 * float(f_tx) * float(f_rx) * float(reflection_amplitude) ** 2)
    denominator = 64.0 * np.pi ** 3 * (float(d1) * float(d2)) ** 2
    return numerator / denominator
