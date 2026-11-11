"""Precoder komunikasi dan beam sensing (docs/EXPERIMENT_DESIGN.md §5.3).

Struktur precoder di sini dipakai **sama persis** oleh agen DRL, B1, B2, dan
Oracle-GD. Yang membedakan metode hanyalah bagaimana ``phi``, ``rho``, dan
``p`` dipilih; dengan begitu perbandingan antar-metode mengukur kualitas
keputusan, bukan perbedaan implementasi precoder.

Konvensi bentuk mengikuti CLAUDE.md; ``...`` dimensi batch::

    h_eff (..., K, Nt)   ->   Wc (..., Nt, K)
    c_hat (..., Nt)      ->   ws (..., Nt)

Anggaran daya (E1) dipenuhi **secara konstruksi**, bukan lewat proyeksi
setelahnya: kolom W_c dinormalkan lalu diskalakan sqrt((1-rho) P p_k) dengan
sum_k p_k = 1, dan ||w_s||^2 = rho P. Jadi tr(R_x) = P_max persis.
"""

from __future__ import annotations

import numpy as np


def softmax(x: np.ndarray, axis: int = -1) -> np.ndarray:
    """Softmax stabil; dipakai mengubah ``p_raw`` menjadi bobot daya pengguna."""
    x = np.asarray(x, dtype=float)
    z = x - np.max(x, axis=axis, keepdims=True)
    e = np.exp(z)
    return e / np.sum(e, axis=axis, keepdims=True)


def rzf_regularization(num_users: int, noise_power_watt: float,
                       p_max_watt: float) -> float:
    """alpha = K sigma_n^2 / P_max  (§5.3, ``action.rzf_regularization: auto``)."""
    return float(num_users) * float(noise_power_watt) / float(p_max_watt)


def rzf_directions(h_eff: np.ndarray, regularization: float) -> np.ndarray:
    """Arah RZF (kolom ternormalisasi), bentuk (..., Nt, K).

    SINR (E3) memakai ``h_e,k^T w_j``, jadi matriks kanal yang relevan adalah
    ``A`` dengan h_e,k sebagai KOLOM dan target ``A^T W ~ I``. Solusinya

        W = conj(A) (A^T conj(A) + alpha I)^{-1},

    dengan ``A^T conj(A)`` Hermitian positif semidefinit. Memakai ``A^H A``
    di sini adalah kesalahan yang mudah terjadi dan tidak terdeteksi oleh uji
    daya mana pun -- ia hanya memperburuk SINR diam-diam.
    """
    h_eff = np.asarray(h_eff)
    a = np.swapaxes(h_eff, -1, -2)                        # (..., Nt, K)
    gram = np.einsum("...nk,...nj->...kj", a, np.conj(a))  # (..., K, K)
    k = gram.shape[-1]
    reg = float(regularization) * np.eye(k)
    w = np.linalg.solve(np.swapaxes(gram + reg, -1, -2), np.swapaxes(np.conj(a), -1, -2))
    w = np.swapaxes(w, -1, -2)                            # (..., Nt, K)
    norms = np.linalg.norm(w, axis=-2, keepdims=True)
    return w / np.maximum(norms, 1e-30)


def communication_precoder(h_eff: np.ndarray, power_weights: np.ndarray,
                           p_max_watt: float, sensing_fraction,
                           regularization: float) -> np.ndarray:
    """W_c = arah RZF diskalakan sqrt((1 - rho) P_max p_k).  (§5.3)

    :param power_weights: (..., K), harus berjumlah 1 (keluaran ``softmax``)
    :param sensing_fraction: rho, skalar atau (...,)
    :returns: (..., Nt, K)
    """
    directions = rzf_directions(h_eff, regularization)
    rho = np.asarray(sensing_fraction, dtype=float)
    scale = np.sqrt((1.0 - rho)[..., None] * float(p_max_watt)
                    * np.asarray(power_weights, dtype=float))     # (..., K)
    return directions * scale[..., None, :]


def sensing_beam(c_hat: np.ndarray, p_max_watt: float,
                 sensing_fraction) -> np.ndarray:
    """w_s = sqrt(rho P_max) * c_hat^* / ||c_hat||.  (§5.3)

    ``c_hat^T = g_hat_t^T Theta G`` dibangun dari model LoS gelombang sferis ke
    **estimasi** posisi target, sehingga beam ini sengaja tidak sempurna: itu
    bagian dari masalah observasi parsial, bukan cacat implementasi.

    Konjugat (bukan transpose biasa) karena (E7) memakai ``c^T w_s``:
    ``c^T c_hat^*`` maksimum saat c_hat = c.
    """
    c_hat = np.asarray(c_hat)
    norm = np.linalg.norm(c_hat, axis=-1, keepdims=True)
    rho = np.asarray(sensing_fraction, dtype=float)
    return (np.sqrt(rho * float(p_max_watt))[..., None]
            * np.conj(c_hat) / np.maximum(norm, 1e-30))


def estimated_sensing_channel(g_hat_t: np.ndarray, phi: np.ndarray,
                              G: np.ndarray) -> np.ndarray:
    """c_hat^T = g_hat_t^T Theta G, bentuk (..., Nt).

    Sama dengan (E5) tanpa suku langsung: §5.3 membangun beam sensing hanya
    dari jalur lewat RIS, karena jalur langsung BS->target memang NLoS.
    """
    v = np.asarray(g_hat_t) * np.exp(1j * np.asarray(phi))
    return np.einsum("mn,...m->...n", np.asarray(G), v)
