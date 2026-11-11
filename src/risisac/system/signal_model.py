"""Model sinyal ISAC (docs/EXPERIMENT_DESIGN.md §3), versi NumPy terbatch.

Berisi (E1)-(E7) lengkap. Versi PyTorch yang setara ada di
``signal_model_torch.py`` untuk Oracle-GD; kesetaraan numeriknya diuji di
``tests/test_signal_model_torch.py``, bukan diandaikan.

Konvensi bentuk mengikuti tabel CLAUDE.md; ``...`` adalah dimensi batch
(waktu, episode) yang boleh kosong::

    G        (M, Nt)        H      (Nr, M)       Hc    (Nr, Nt)
    g_user   (..., K, M)    hd_user (..., K, Nt)
    g_tgt    (..., Q, M)    hd_tgt_tx (..., Q, Nt)   hd_tgt_rx (..., Q, Nr)
    phi      (..., M)       Wc     (..., Nt, K)      ws    (..., Nt)

Perhatikan **transpose tanpa konjugat** pada (E2), (E3), (E5), dan (E7):
desain memakai ``h^T w``, bukan ``h^H w``. Konvensi itu konsisten dengan
koefisien kanal resiprokal dari ray tracing dan TIDAK boleh diganti diam-diam;
mengganti satu saja membuat profil fasa RIS menyefasekan hal yang salah.

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


# ===================================================================== (E1)-(E7)

def ris_response(phi: np.ndarray) -> np.ndarray:
    """Diagonal Theta = diag(e^{j phi}), dikembalikan sebagai vektor (..., M)."""
    return np.exp(1j * np.asarray(phi))


def effective_channel(hd: np.ndarray, g: np.ndarray, phi: np.ndarray,
                      G: np.ndarray) -> np.ndarray:
    """Kanal efektif  h_e,k^T = h_d,k^T + g_k^T Theta G.  (E2)

    :param hd: (..., K, Nt) kanal langsung BS-tx -> pengguna
    :param g:  (..., K, M)  kanal RIS -> pengguna
    :param phi: (..., M)    fasa RIS
    :param G:  (M, Nt)      kanal BS-tx -> RIS
    :returns: (..., K, Nt)
    """
    v = np.asarray(g) * ris_response(phi)[..., None, :]        # (..., K, M)
    return np.asarray(hd) + np.einsum("mn,...km->...kn", np.asarray(G), v)


def transmit_covariance(Wc: np.ndarray, ws: np.ndarray) -> np.ndarray:
    """R_x = W_c W_c^H + w_s w_s^H.  (E1)  :returns: (..., Nt, Nt)

    Dipakai untuk pemeriksaan dan tes; jalur hitung utama (SINR, SCNR) memakai
    bentuk terfaktor agar tidak membentuk matriks Nt x Nt per langkah.
    """
    Wc, ws = np.asarray(Wc), np.asarray(ws)
    return (np.einsum("...nk,...mk->...nm", Wc, np.conj(Wc))
            + np.einsum("...n,...m->...nm", ws, np.conj(ws)))


def total_power(Wc: np.ndarray, ws: np.ndarray) -> np.ndarray:
    """tr(R_x) = ||W_c||_F^2 + ||w_s||^2.  (E1)  :returns: (...,) real"""
    return (np.sum(np.abs(np.asarray(Wc)) ** 2, axis=(-2, -1))
            + np.sum(np.abs(np.asarray(ws)) ** 2, axis=-1))


def sinr(h_eff: np.ndarray, Wc: np.ndarray, ws: np.ndarray,
         noise_power_watt: float, beta_s: float = 1.0) -> np.ndarray:
    """SINR tiap pengguna.  (E3)

        SINR_k = |h_e,k^T w_k|^2
                 / ( sum_{j != k} |h_e,k^T w_j|^2
                     + beta_s |h_e,k^T w_s|^2 + sigma_n^2 )

    ``beta_s = 1`` (default desain): aliran sensing menjadi interferensi.

    :param h_eff: (..., K, Nt)
    :returns: (..., K) real
    """
    h_eff, Wc, ws = np.asarray(h_eff), np.asarray(Wc), np.asarray(ws)
    cross = np.einsum("...kn,...nj->...kj", h_eff, Wc)          # (..., K, K)
    power = np.abs(cross) ** 2
    signal = np.diagonal(power, axis1=-2, axis2=-1)             # (..., K)
    interference = np.sum(power, axis=-1) - signal
    leak = np.abs(np.einsum("...kn,...n->...k", h_eff, ws)) ** 2
    return signal / (interference + float(beta_s) * leak + float(noise_power_watt))


def rate(sinr_linear: np.ndarray) -> np.ndarray:
    """R_k = log2(1 + SINR_k) [bit/s/Hz].  (E4)"""
    return np.log2(1.0 + np.asarray(sinr_linear))


def sensing_channels(hd_tgt_tx: np.ndarray, hd_tgt_rx: np.ndarray,
                     g_tgt: np.ndarray, phi: np.ndarray,
                     G: np.ndarray, H: np.ndarray):
    """Kanal maju dan balik target.  (E5)

        c^T = h_{d,t}^T + g_t^T Theta G,     b = h^{(r)}_{d,t} + H Theta g_t

    :returns: ``(c, b)`` berbentuk (..., Q, Nt) dan (..., Q, Nr)
    """
    v = np.asarray(g_tgt) * ris_response(phi)[..., None, :]      # (..., Q, M)
    c = np.asarray(hd_tgt_tx) + np.einsum("mn,...qm->...qn", np.asarray(G), v)
    b = np.asarray(hd_tgt_rx) + np.einsum("rm,...qm->...qr", np.asarray(H), v)
    return c, b


def clutter_noise_covariance(Hc: np.ndarray, Wc: np.ndarray, ws: np.ndarray,
                             clutter_residual: float, noise_power_watt: float,
                             integration_samples: int) -> np.ndarray:
    """R_cn = xi * H_c R_x H_c^H + (sigma_n^2 / L) I_{Nr}.  (E7)

    xi adalah fraksi clutter yang tersisa setelah filter nol-Doppler (§3.5).
    Dibentuk dari faktor ``H_c W_c`` dan ``H_c w_s``, bukan dari R_x utuh:
    hasilnya sama tetapi tetap positif semidefinit secara numerik.

    :returns: (..., Nr, Nr)
    """
    Hc, Wc, ws = np.asarray(Hc), np.asarray(Wc), np.asarray(ws)
    hw = np.einsum("rn,...nk->...rk", Hc, Wc)                    # (..., Nr, K)
    hs = np.einsum("rn,...n->...r", Hc, ws)                      # (..., Nr)
    clutter = (np.einsum("...rk,...sk->...rs", hw, np.conj(hw))
               + np.einsum("...r,...s->...rs", hs, np.conj(hs)))
    nr = Hc.shape[0]
    noise = (float(noise_power_watt) / float(integration_samples)) * np.eye(nr)
    return float(clutter_residual) * clutter + noise


def forward_sensing_power(c: np.ndarray, Wc: np.ndarray,
                          ws: np.ndarray) -> np.ndarray:
    """c^T R_x c^*  (suku maju pada (E7)).  :returns: (..., Q) real

    Dengan R_x = W_c W_c^H + w_s w_s^H berlaku
    ``c^T R_x c^* = ||c^T W_c||^2 + |c^T w_s|^2``, yang juga membuat jelas
    bahwa besaran ini riil dan tak negatif.
    """
    c, Wc, ws = np.asarray(c), np.asarray(Wc), np.asarray(ws)
    comm = np.sum(np.abs(np.einsum("...qn,...nk->...qk", c, Wc)) ** 2, axis=-1)
    sens = np.abs(np.einsum("...qn,...n->...q", c, ws)) ** 2
    return comm + sens


def scnr(c: np.ndarray, b: np.ndarray, Wc: np.ndarray, ws: np.ndarray,
         Hc: np.ndarray, eta: float, noise_power_watt: float,
         integration_samples: int, clutter_residual: float) -> np.ndarray:
    """SCNR dengan combiner MVDR dan integrasi koheren L sampel.  (E7)

        SCNR = eta * (c^T R_x c^*) * b^H R_cn^{-1} b

    Bentuk tertutup ini adalah maksimum rasio Rayleigh umum atas combiner;
    kesetaraannya diuji numerik di ``tests/test_signal_model.py``.

    :returns: (..., Q) real
    """
    Rcn = clutter_noise_covariance(Hc, Wc, ws, clutter_residual,
                                   noise_power_watt, integration_samples)
    b = np.asarray(b)
    # b^H R_cn^{-1} b lewat solve, bukan inverse eksplisit.
    sol = np.linalg.solve(Rcn[..., None, :, :], b[..., None])[..., 0]
    ret = np.real(np.sum(np.conj(b) * sol, axis=-1))             # (..., Q)
    return float(eta) * forward_sensing_power(c, Wc, ws) * ret


def reward(min_rate: np.ndarray, scnr_db: np.ndarray, threshold_db: float,
           reward_lambda: float, hinge_scale_db: float) -> np.ndarray:
    """r_t = min_k R_k - lambda * [Gamma_dB - SCNR_dB]_+ / hinge_scale.  (E9)

    Hinge menghukum SCNR **di bawah** ambang saja (CLAUDE.md, pelajaran dari
    proyek sebelumnya): SCNR di atas Gamma tidak memberi hadiah tambahan,
    sehingga agen tidak terdorong membuang daya komunikasi untuk sensing yang
    sudah cukup.
    """
    deficit = np.maximum(float(threshold_db) - np.asarray(scnr_db), 0.0)
    return np.asarray(min_rate) - float(reward_lambda) * deficit / float(hinge_scale_db)
