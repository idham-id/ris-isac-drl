"""Model sinyal ISAC versi PyTorch, terdiferensiasi (§3, §6.2 B3).

Dipakai **hanya** oleh Oracle-GD, yang menurunkan gradien objektif terhadap
``phi``, ``rho``, dan ``p``. Jalur evaluasi utama memakai versi NumPy di
``signal_model.py``.

Duplikasi dua implementasi adalah risiko nyata: keduanya bisa menyimpang
tanpa ada yang menyadarinya, dan Oracle-GD adalah acuan atas yang menentukan
Gate 3. Karena itu kesetaraan numeriknya **diuji** di
``tests/test_signal_model_torch.py`` untuk masukan acak, bukan diandaikan.

Semua fungsi menerima tensor complex64/complex128 dan mengembalikan tensor
dengan bentuk sama seperti padanan NumPy-nya.
"""

from __future__ import annotations

import numpy as np
import torch


def ris_response(phi: torch.Tensor) -> torch.Tensor:
    """Theta = diag(e^{j phi}) sebagai vektor (..., M). Terdiferensiasi ke phi."""
    return torch.polar(torch.ones_like(phi), phi)


def effective_channel(hd: torch.Tensor, g: torch.Tensor, phi: torch.Tensor,
                      G: torch.Tensor) -> torch.Tensor:
    """h_e,k^T = h_d,k^T + g_k^T Theta G.  (E2)  -> (..., K, Nt)"""
    v = g * ris_response(phi).unsqueeze(-2)
    return hd + torch.einsum("mn,...km->...kn", G, v)


def total_power(Wc: torch.Tensor, ws: torch.Tensor) -> torch.Tensor:
    """tr(R_x) = ||W_c||_F^2 + ||w_s||^2.  (E1)"""
    return (Wc.abs().pow(2).sum(dim=(-2, -1)) + ws.abs().pow(2).sum(dim=-1))


def sinr(h_eff: torch.Tensor, Wc: torch.Tensor, ws: torch.Tensor,
         noise_power_watt: float, beta_s: float = 1.0) -> torch.Tensor:
    """SINR tiap pengguna.  (E3)  -> (..., K) riil"""
    cross = torch.einsum("...kn,...nj->...kj", h_eff, Wc)
    power = cross.abs().pow(2)
    signal = torch.diagonal(power, dim1=-2, dim2=-1)
    interference = power.sum(dim=-1) - signal
    leak = torch.einsum("...kn,...n->...k", h_eff, ws).abs().pow(2)
    return signal / (interference + float(beta_s) * leak + float(noise_power_watt))


def rate(sinr_linear: torch.Tensor) -> torch.Tensor:
    """R_k = log2(1 + SINR_k).  (E4)"""
    return torch.log2(1.0 + sinr_linear)


def sensing_channels(hd_tgt_tx: torch.Tensor, hd_tgt_rx: torch.Tensor,
                     g_tgt: torch.Tensor, phi: torch.Tensor,
                     G: torch.Tensor, H: torch.Tensor):
    """c^T = h_d,t^T + g_t^T Theta G,  b = h^(r)_d,t + H Theta g_t.  (E5)"""
    v = g_tgt * ris_response(phi).unsqueeze(-2)
    c = hd_tgt_tx + torch.einsum("mn,...qm->...qn", G, v)
    b = hd_tgt_rx + torch.einsum("rm,...qm->...qr", H, v)
    return c, b


def clutter_noise_covariance(Hc: torch.Tensor, Wc: torch.Tensor,
                             ws: torch.Tensor, clutter_residual: float,
                             noise_power_watt: float,
                             integration_samples: int) -> torch.Tensor:
    """R_cn = xi H_c R_x H_c^H + (sigma_n^2 / L) I.  (E7)"""
    hw = torch.einsum("rn,...nk->...rk", Hc, Wc)
    hs = torch.einsum("rn,...n->...r", Hc, ws)
    clutter = (torch.einsum("...rk,...sk->...rs", hw, hw.conj())
               + torch.einsum("...r,...s->...rs", hs, hs.conj()))
    nr = Hc.shape[0]
    eye = torch.eye(nr, dtype=Hc.dtype, device=Hc.device)
    noise = (float(noise_power_watt) / float(integration_samples)) * eye
    return float(clutter_residual) * clutter + noise


def forward_sensing_power(c: torch.Tensor, Wc: torch.Tensor,
                          ws: torch.Tensor) -> torch.Tensor:
    """c^T R_x c^* = ||c^T W_c||^2 + |c^T w_s|^2.  -> (..., Q) riil"""
    comm = torch.einsum("...qn,...nk->...qk", c, Wc).abs().pow(2).sum(dim=-1)
    sens = torch.einsum("...qn,...n->...q", c, ws).abs().pow(2)
    return comm + sens


def scnr(c: torch.Tensor, b: torch.Tensor, Wc: torch.Tensor, ws: torch.Tensor,
         Hc: torch.Tensor, eta: float, noise_power_watt: float,
         integration_samples: int, clutter_residual: float) -> torch.Tensor:
    """SCNR = eta (c^T R_x c^*) b^H R_cn^{-1} b.  (E7)  -> (..., Q) riil"""
    Rcn = clutter_noise_covariance(Hc, Wc, ws, clutter_residual,
                                   noise_power_watt, integration_samples)
    sol = torch.linalg.solve(Rcn.unsqueeze(-3), b.unsqueeze(-1)).squeeze(-1)
    ret = (b.conj() * sol).sum(dim=-1).real
    return float(eta) * forward_sensing_power(c, Wc, ws) * ret


# ------------------------------------------------------- precoder (§5.3)

def rzf_directions(h_eff: torch.Tensor, regularization: float) -> torch.Tensor:
    """Arah RZF ternormalisasi, (..., Nt, K). Padanan precoding.rzf_directions."""
    a = h_eff.transpose(-1, -2)
    gram = torch.einsum("...nk,...nj->...kj", a, a.conj())
    k = gram.shape[-1]
    eye = torch.eye(k, dtype=gram.dtype, device=gram.device)
    w = torch.linalg.solve((gram + float(regularization) * eye).transpose(-1, -2),
                           a.conj().transpose(-1, -2))
    w = w.transpose(-1, -2)
    return w / w.norm(dim=-2, keepdim=True).clamp_min(1e-30)


def communication_precoder(h_eff: torch.Tensor, power_weights: torch.Tensor,
                           p_max_watt: float, sensing_fraction: torch.Tensor,
                           regularization: float) -> torch.Tensor:
    """W_c = arah RZF diskalakan sqrt((1 - rho) P_max p_k).  (§5.3)"""
    directions = rzf_directions(h_eff, regularization)
    scale = torch.sqrt((1.0 - sensing_fraction).unsqueeze(-1)
                       * float(p_max_watt) * power_weights)
    return directions * scale.unsqueeze(-2).to(directions.dtype)


def sensing_beam(c_hat: torch.Tensor, p_max_watt: float,
                 sensing_fraction: torch.Tensor) -> torch.Tensor:
    """w_s = sqrt(rho P_max) c_hat^* / ||c_hat||.  (§5.3)"""
    norm = c_hat.norm(dim=-1, keepdim=True).clamp_min(1e-30)
    scale = torch.sqrt(sensing_fraction * float(p_max_watt)).unsqueeze(-1)
    return scale.to(c_hat.dtype) * c_hat.conj() / norm.to(c_hat.dtype)


def estimated_sensing_channel(g_hat_t: torch.Tensor, phi: torch.Tensor,
                              G: torch.Tensor) -> torch.Tensor:
    """c_hat^T = g_hat_t^T Theta G, (..., Nt)."""
    return torch.einsum("mn,...m->...n", G, g_hat_t * ris_response(phi))


def to_tensor(array, dtype=torch.complex128, device=None) -> torch.Tensor:
    """NumPy -> torch dengan dtype yang konsisten."""
    return torch.as_tensor(np.asarray(array), dtype=dtype, device=device)
