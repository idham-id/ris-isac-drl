"""B3 / B4 - Oracle-GD (docs/EXPERIMENT_DESIGN.md §6.2).

Adam per langkah atas ``phi``, ``rho``, dan ``p`` dengan **struktur precoder
yang sama** seperti metode lain; objektifnya versi halus dari reward (E9)::

    maksimumkan  softmin_k R_k  -  lambda * softplus(Gamma_dB - SCNR_dB) / skala

Softmin dan softplus dipakai karena ``min`` dan ``[.]_+`` mematikan gradien di
seluruh pengguna kecuali yang terlemah dan di seluruh titik yang sudah
memenuhi ambang. Pemilihan restart terbaik tetap memakai reward **keras**
(E9), bukan versi halusnya, supaya yang dilaporkan adalah besaran yang sama
dengan yang dipakai metode lain.

B3 mendapat **CSI dan posisi sempurna**: ia adalah acuan atas, bukan metode
yang bisa diterapkan. B4 menjalankan B3 tiap D langkah lalu menahan
keputusannya, sehingga selisih B3-B4 mengukur seberapa cepat keputusan menjadi
usang -- itulah yang membuat masalah ini layak ditangani agen sekuensial.

Seluruh restart dan seluruh snapshot dioptimalkan **sekaligus** sebagai satu
batch: masalahnya saling bebas, jadi menjumlahkan objektifnya memberi gradien
yang sama persis seperti menjalankannya satu per satu, dengan biaya jauh lebih
kecil (§4.3 memperkirakan 1,2e7 iterasi gradien per varian).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..system import signal_model as sm
from .common import Snapshot, SystemConstants, evaluate_decision
from .geometric import phases as geometric_phases


@dataclass(frozen=True)
class OracleGDSettings:
    iterations: int
    restarts: int
    learning_rate: float
    softmin_temperature: float
    device: str

    @classmethod
    def from_config(cls, cfg: dict) -> "OracleGDSettings":
        g = cfg["baselines"]["oracle_gd"]
        return cls(iterations=int(g["iterations"]), restarts=int(g["restarts"]),
                   learning_rate=float(g["learning_rate"]),
                   softmin_temperature=float(g["softmin_temperature"]),
                   device=str(g["device"]))


def _resolve_device(name: str) -> str:
    import torch
    if name == "cuda" and not torch.cuda.is_available():
        return "cpu"
    return name


def _initial_phases(snap: Snapshot, settings: OracleGDSettings,
                    rng) -> np.ndarray:
    """(R, B, M): restart 0 geometris, sisanya acak (§6.2 "geometris + acak")."""
    out = rng.uniform(0.0, 2.0 * np.pi,
                      size=(settings.restarts, snap.batch, snap.num_elements))
    if settings.restarts > 0:
        entities = np.concatenate([snap.g_user, snap.g_tgt[:, :1, :]], axis=1)
        omega = np.ones(entities.shape[1])
        out[0] = geometric_phases(entities, snap.G, omega)
    return out


def optimize(snap: Snapshot, const: SystemConstants,
             settings: OracleGDSettings, seed: int = 0,
             progress: bool = False) -> dict:
    """Jalankan Oracle-GD pada seluruh snapshot sekaligus.

    :returns: dict berisi ``phi`` (B, M), ``rho`` (B,), ``weights`` (B, K),
        ``reward`` (B,), dan ``restart`` (B,) indeks restart yang menang.
    """
    import torch

    from ..system import signal_model_torch as smt

    device = _resolve_device(settings.device)
    cplx = torch.complex128
    real = torch.float64
    rng = np.random.default_rng(seed)
    r, b, m = settings.restarts, snap.batch, snap.num_elements
    k = snap.num_users

    def t_c(x):
        return torch.as_tensor(np.asarray(x), dtype=cplx, device=device)

    def t_r(x):
        return torch.as_tensor(np.asarray(x, dtype=float), dtype=real,
                               device=device)

    G, H, Hc = t_c(snap.G), t_c(snap.H), t_c(snap.Hc)
    hd_user = t_c(snap.hd_user).expand(r, *snap.hd_user.shape)
    g_user = t_c(snap.g_user).expand(r, *snap.g_user.shape)
    hd_tx = t_c(snap.hd_tgt_tx).expand(r, *snap.hd_tgt_tx.shape)
    hd_rx = t_c(snap.hd_tgt_rx).expand(r, *snap.hd_tgt_rx.shape)
    g_tgt = t_c(snap.g_tgt).expand(r, *snap.g_tgt.shape)
    p_max = t_r(snap.p_max_watt).expand(r, b)
    sqrt_p = torch.sqrt(p_max)

    alpha = (float(k) * const.noise_power_watt / float(np.max(snap.p_max_watt)))
    tau = float(settings.softmin_temperature)

    phi = torch.tensor(_initial_phases(snap, settings, rng), dtype=real,
                       device=device, requires_grad=True)
    rho_raw = torch.zeros(r, b, dtype=real, device=device, requires_grad=True)
    p_raw = torch.zeros(r, b, k, dtype=real, device=device, requires_grad=True)
    optimiser = torch.optim.Adam([phi, rho_raw, p_raw],
                                 lr=float(settings.learning_rate))

    def forward():
        rho = torch.sigmoid(rho_raw)
        weights = torch.softmax(p_raw, dim=-1)
        h_eff = smt.effective_channel(hd_user, g_user, phi, G)
        Wc = smt.communication_precoder(h_eff, weights, 1.0, rho, alpha)
        Wc = Wc * sqrt_p[..., None, None].to(cplx)
        # CSI sempurna: beam sensing dibangun dari g_t yang sebenarnya.
        c_hat = smt.estimated_sensing_channel(g_tgt[..., 0, :], phi, G)
        ws = smt.sensing_beam(c_hat, 1.0, rho) * sqrt_p[..., None].to(cplx)
        c, bb = smt.sensing_channels(hd_tx, hd_rx, g_tgt, phi, G, H)
        rates = smt.rate(smt.sinr(h_eff, Wc, ws, const.noise_power_watt,
                                  const.beta_s))
        scnr = smt.scnr(c, bb, Wc, ws, Hc, const.eta, const.noise_power_watt,
                        const.integration_samples, const.clutter_residual)
        scnr_db = 10.0 * torch.log10(scnr.clamp_min(1e-300))
        return rates, scnr_db.amin(dim=-1), rho, weights

    for step in range(int(settings.iterations)):
        optimiser.zero_grad(set_to_none=True)
        rates, scnr_db, _, _ = forward()
        soft_min = -tau * torch.logsumexp(-rates / tau, dim=-1)
        deficit = torch.nn.functional.softplus(
            float(const.scnr_threshold_db) - scnr_db)
        objective = soft_min - const.reward_lambda * deficit / const.hinge_scale_db
        (-objective.sum()).backward()
        optimiser.step()
        if progress and (step + 1) % max(1, int(settings.iterations) // 5) == 0:
            print(f"    iterasi {step + 1}/{settings.iterations}: "
                  f"objektif halus {float(objective.mean()):.4f}", flush=True)

    with torch.no_grad():
        rates, scnr_db, rho, weights = forward()
        hard = (rates.amin(dim=-1)
                - const.reward_lambda
                * torch.clamp(float(const.scnr_threshold_db) - scnr_db, min=0.0)
                / const.hinge_scale_db)                        # (R, B)
        best = torch.argmax(hard, dim=0)                       # (B,)

    idx = best.cpu().numpy()
    rows = np.arange(b)
    phi_np = np.mod(phi.detach().cpu().numpy()[idx, rows], 2.0 * np.pi)
    rho_np = rho.detach().cpu().numpy()[idx, rows]
    w_np = weights.detach().cpu().numpy()[idx, rows]

    # Dilaporkan ulang lewat mesin evaluasi NumPy yang sama dengan metode lain,
    # supaya angka B3 tidak bergantung pada jalur hitung yang berbeda.
    out = evaluate_decision(snap, const, phi_np, rho_np, w_np)
    return {"phi": phi_np, "rho": rho_np, "weights": w_np,
            "restart": idx, **out}


def hold_decisions(phi: np.ndarray, rho: np.ndarray, weights: np.ndarray,
                   period: int):
    """B4 - Oracle-GD-stale(D): keputusan langkah t dipakai ulang sampai t+D.

    Masukan berbentuk (T, ...) sepanjang satu episode; keluarannya sama
    bentuknya, dengan baris t diganti baris ``(t // D) * D``.
    """
    period = max(1, int(period))
    t = len(phi)
    index = (np.arange(t) // period) * period
    return phi[index], rho[index], weights[index]
