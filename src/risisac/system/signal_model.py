"""Model sinyal ISAC (docs/EXPERIMENT_DESIGN.md §3).

Fase 1 hanya memerlukan faktor radar (E6) dan bentuk ideal SCNR (E7) untuk
peta kelayakan E1. Precoder, SINR (E3), dan SCNR lengkap dengan clutter
ditambahkan di Fase 3.

Semua daya dalam Watt; dB hanya untuk pelaporan.
"""

from __future__ import annotations

import numpy as np

SPEED_OF_LIGHT = 299_792_458.0


def wavelength_of(carrier_frequency_hz: float) -> float:
    """Panjang gelombang pembawa (meter). Disebut ``wavelength``, bukan ``lam``,
    agar tidak tertukar dengan bobot reward ``reward_lambda`` (CLAUDE.md)."""
    return SPEED_OF_LIGHT / float(carrier_frequency_hz)


def eta_factor(rcs_m2: float, wavelength: float) -> float:
    """Faktor radar eta = 4 pi sigma_rcs / lambda^2.  (E6)

    Membuat model kanal ternormalisasi Friis setara dengan persamaan radar
    bistatik. Tanpa faktor ini SNR radar meleset sekitar 32 dB pada 3,5 GHz
    dengan sigma_rcs = 1 m^2 (CLAUDE.md, "pelajaran dari proyek sebelumnya").
    """
    return 4.0 * np.pi * float(rcs_m2) / float(wavelength) ** 2


def focus_phases(u: np.ndarray, v: np.ndarray) -> np.ndarray:
    """Profil fasa RIS yang memaksimalkan |sum_m v_m e^{j phi_m} u_m|.

    ``u`` adalah kanal BS-tx -> elemen RIS setelah precoding (``G a_bar``),
    ``v`` adalah kanal elemen RIS -> titik. Hasilnya membuat setiap suku
    sefase, sehingga jumlahnya menjadi sum_m |u_m||v_m| (penjumlahan koheren).
    """
    return -np.angle(np.asarray(u) * np.asarray(v))


def cascaded_coefficient(u: np.ndarray, v: np.ndarray,
                         phi: np.ndarray) -> np.ndarray:
    """Koefisien kaskade sum_m v_m e^{j phi_m} u_m, dijumlahkan atas elemen RIS.

    Bentuk ``u``/``v``: (..., M); ``phi``: (..., M). Keluaran: (...,).
    """
    return np.sum(np.asarray(v) * np.exp(1j * np.asarray(phi)) * np.asarray(u),
                  axis=-1)


def ideal_scnr(c_eff: np.ndarray, b: np.ndarray, p_max_watt: float,
               eta: float, noise_power_watt: float,
               integration_samples: int) -> np.ndarray:
    """SCNR ideal: (E7) dengan rho = 1 dan tanpa clutter.

    Dengan seluruh daya untuk sensing dan beam ``w_s = sqrt(P_max) a_bar``,
    ``R_x = P_max a_bar a_bar^H`` sehingga ``c^T R_x c* = P_max |c^T a_bar|^2``.
    Tanpa clutter ``R_cn = (sigma_n^2 / L) I``, sehingga
    ``b^H R_cn^-1 b = (L / sigma_n^2) ||b||^2``. Maka

        SCNR = eta * P_max * |c^T a_bar|^2 * (L / sigma_n^2) * ||b||^2.

    :param c_eff: (...,) kanal efektif maju BS-tx -> target setelah precoding
    :param b: (..., Nr) kanal efektif balik target -> BS-rx
    """
    fwd = np.abs(np.asarray(c_eff)) ** 2
    ret = np.sum(np.abs(np.asarray(b)) ** 2, axis=-1)
    return (float(eta) * float(p_max_watt) * fwd * ret
            * float(integration_samples) / float(noise_power_watt))


def snr_from_gain(gain: np.ndarray, p_max_watt: float,
                  noise_power_watt: float) -> np.ndarray:
    """SNR komunikasi satu aliran: P_max * |h|^2 / sigma_n^2."""
    return float(p_max_watt) * np.asarray(gain) / float(noise_power_watt)


def to_db(x: np.ndarray) -> np.ndarray:
    """10 log10 dengan lantai agar nol tidak menghasilkan -inf."""
    return 10.0 * np.log10(np.asarray(x) + 1e-300)


def dbm_to_watt(dbm: float) -> float:
    return 10.0 ** ((float(dbm) - 30.0) / 10.0)
