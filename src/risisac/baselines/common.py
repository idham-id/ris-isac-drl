"""Mesin evaluasi bersama untuk semua metode (docs/EXPERIMENT_DESIGN.md §6).

Setiap metode -- agen DRL, B1, B2, B3 -- hanya memutuskan tiga hal:

    phi      (..., M)   fasa RIS
    rho      (...,)     fraksi daya sensing
    weights  (..., K)   bobot daya pengguna (berjumlah 1)

Sisanya (RZF, beam sensing, SINR, SCNR, reward) dikerjakan di sini, sehingga
perbandingan antar-metode mengukur kualitas KEPUTUSAN dan bukan perbedaan
implementasi precoder. Memisahkannya juga membuat satu kesalahan precoder
tidak bisa menguntungkan satu metode saja.

Semua fungsi terbatch pada sumbu depan ``B`` (snapshot).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..system import precoding as pc
from ..system import signal_model as sm


@dataclass(frozen=True)
class SystemConstants:
    """Tetapan sistem dari config; tidak berubah dalam satu eksperimen."""

    noise_power_watt: float
    eta: float
    integration_samples: int
    clutter_residual: float
    beta_s: float
    scnr_threshold_db: float
    reward_lambda: float
    hinge_scale_db: float

    @classmethod
    def from_config(cls, cfg: dict) -> "SystemConstants":
        from ..config import noise_power_watt
        sens, radio = cfg["sensing"], cfg["radio"]
        wavelength = sm.wavelength_of(float(radio["carrier_frequency_hz"]))
        return cls(
            noise_power_watt=noise_power_watt(cfg),
            eta=sm.eta_factor(float(radio["target"]["rcs_m2"]), wavelength),
            integration_samples=int(sens["integration_samples"]),
            clutter_residual=float(sens["clutter_residual"]),
            beta_s=1.0 if bool(sens["sensing_interferes_users"]) else 0.0,
            scnr_threshold_db=float(sens["scnr_threshold_db"]),
            reward_lambda=float(cfg["reward"]["lambda"]),
            hinge_scale_db=float(cfg["reward"]["hinge_scale_db"]),
        )


@dataclass(frozen=True)
class Snapshot:
    """Kanal satu himpunan langkah waktu, terbatch pada sumbu depan ``B``."""

    G: np.ndarray            # (M, Nt)   statis
    H: np.ndarray            # (Nr, M)   statis
    Hc: np.ndarray           # (Nr, Nt)  statis
    hd_user: np.ndarray      # (B, K, Nt)
    g_user: np.ndarray       # (B, K, M)
    hd_tgt_tx: np.ndarray    # (B, Q, Nt)
    hd_tgt_rx: np.ndarray    # (B, Q, Nr)
    g_tgt: np.ndarray        # (B, Q, M)
    p_max_watt: np.ndarray   # (B,)

    @property
    def batch(self) -> int:
        return int(self.hd_user.shape[0])

    @property
    def num_users(self) -> int:
        return int(self.hd_user.shape[1])

    @property
    def num_elements(self) -> int:
        return int(self.G.shape[0])

    @property
    def num_tx(self) -> int:
        return int(self.G.shape[1])

    def select(self, index) -> "Snapshot":
        return Snapshot(self.G, self.H, self.Hc,
                        self.hd_user[index], self.g_user[index],
                        self.hd_tgt_tx[index], self.hd_tgt_rx[index],
                        self.g_tgt[index], self.p_max_watt[index])


def evaluate_decision(snap: Snapshot, const: SystemConstants,
                      phi: np.ndarray, rho, weights: np.ndarray,
                      g_hat_tgt: np.ndarray | None = None,
                      no_ris: bool = False) -> dict:
    """Hitung SINR, rate, SCNR, dan reward untuk satu keputusan.

    :param g_hat_tgt: (B, M) estimasi kanal RIS->target untuk beam sensing.
        ``None`` berarti CSI sempurna (dipakai Oracle-GD): memakai ``g_tgt``
        sebenarnya. Pada B1/B2 dan agen DRL nilainya berasal dari model LoS
        gelombang sferis ke estimasi posisi target, sehingga beam sensing
        sengaja tidak sempurna -- itu bagian dari masalah, bukan cacat.
    :param no_ris: B0 (§6.2, Fase 8). Kaskade RIS dihapus dari (E2) dan (E5),
        dan beam sensing dibangun dari h_{d,t} sebenarnya karena
        ``estimated_sensing_channel`` -- yang hanya memakai jalur kaskade --
        bernilai nol tanpa RIS. ``phi`` dan ``g_hat_tgt`` diabaikan.
        Disediakan di sini, bukan hanya di env, supaya kedua jalur hitung
        benar-benar bisa dibandingkan untuk B0 seperti untuk B2 dan B3.
    """
    rho = np.asarray(rho, dtype=float)
    weights = np.asarray(weights, dtype=float)
    alpha = pc.rzf_regularization(snap.num_users, const.noise_power_watt,
                                  float(np.max(snap.p_max_watt)))

    h_eff = (np.array(snap.hd_user, copy=True) if no_ris
             else sm.effective_channel(snap.hd_user, snap.g_user, phi, snap.G))
    Wc = pc.communication_precoder(h_eff, weights, 1.0, rho, alpha)
    Wc = Wc * np.sqrt(snap.p_max_watt)[..., None, None]

    if no_ris:
        c_hat = snap.hd_tgt_tx[:, 0, :]
    else:
        g_hat = (snap.g_tgt[:, 0, :] if g_hat_tgt is None
                 else np.asarray(g_hat_tgt))
        c_hat = pc.estimated_sensing_channel(g_hat, phi, snap.G)
    ws = pc.sensing_beam(c_hat, 1.0, rho) * np.sqrt(snap.p_max_watt)[..., None]

    if no_ris:
        c, b = (np.array(snap.hd_tgt_tx, copy=True),
                np.array(snap.hd_tgt_rx, copy=True))
    else:
        c, b = sm.sensing_channels(snap.hd_tgt_tx, snap.hd_tgt_rx, snap.g_tgt,
                                   phi, snap.G, snap.H)
    sinr = sm.sinr(h_eff, Wc, ws, const.noise_power_watt, const.beta_s)
    rates = sm.rate(sinr)
    scnr = sm.scnr(c, b, Wc, ws, snap.Hc, const.eta, const.noise_power_watt,
                   const.integration_samples, const.clutter_residual)
    scnr_db = sm.to_db(scnr)
    min_rate = np.min(rates, axis=-1)
    # Satu target (Q = 1) di versi ramping; bila Q > 1 yang mengikat adalah
    # target terlemah, sejalan dengan min_k pada sisi komunikasi.
    worst_scnr_db = np.min(scnr_db, axis=-1)
    return {
        "sinr": sinr,
        "rates": rates,
        "min_rate": min_rate,
        "scnr_db": scnr_db,
        "worst_scnr_db": worst_scnr_db,
        "detected": worst_scnr_db >= const.scnr_threshold_db,
        "reward": sm.reward(min_rate, worst_scnr_db, const.scnr_threshold_db,
                            const.reward_lambda, const.hinge_scale_db),
        "total_power": sm.total_power(Wc, ws),
    }


def uniform_weights(batch: int, num_users: int) -> np.ndarray:
    """Bobot daya seragam; titik awal yang netral bagi B1 dan B2."""
    return np.full((batch, num_users), 1.0 / float(num_users))
