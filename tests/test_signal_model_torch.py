"""Kesetaraan model sinyal NumPy dan PyTorch (docs/TASKS.md Fase 3).

Dua implementasi bisa menyimpang tanpa ada yang menyadarinya, dan versi torch
adalah yang dipakai Oracle-GD -- acuan atas yang menentukan Gate 3. Jadi
kesetaraannya diuji untuk masukan acak, bukan diandaikan.

Diuji juga bahwa objektif Oracle-GD benar-benar **terdiferensiasi** terhadap
phi, rho, dan p: gradien nol diam-diam akan membuat Oracle-GD tidak bergerak
dari titik awalnya dan terlihat seperti baseline yang lemah.
"""

import sys
from pathlib import Path

import numpy as np
import pytest
import torch

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from risisac.system import precoding as pc                           # noqa: E402
from risisac.system import signal_model as sm                        # noqa: E402
from risisac.system import signal_model_torch as smt                 # noqa: E402

NT, NR, M, K, Q = 8, 8, 64, 2, 1
SIGMA2, L, XI, P_MAX = 1e-12, 4096, 0.01, 1.0
CPLX = torch.complex128


@pytest.fixture
def arrays():
    rng = np.random.default_rng(11)

    def c(*shape):
        return 1e-5 * (rng.normal(size=shape) + 1j * rng.normal(size=shape))

    return {
        "G": c(M, NT), "H": c(NR, M), "Hc": c(NR, NT),
        "hd_user": 0.1 * c(K, NT), "g_user": c(K, M),
        "hd_tgt_tx": 0.1 * c(Q, NT), "hd_tgt_rx": 0.1 * c(Q, NR),
        "g_tgt": c(Q, M),
        "phi": rng.uniform(0, 2 * np.pi, M),
        "rho": 0.35,
        "weights": pc.softmax(rng.normal(size=K)),
    }


def torch_pack(a):
    return {k: (smt.to_tensor(v, CPLX) if np.iscomplexobj(v)
                else torch.as_tensor(np.asarray(v), dtype=torch.float64))
            for k, v in a.items()}


def test_kanal_efektif_setara(arrays):
    t = torch_pack(arrays)
    want = sm.effective_channel(arrays["hd_user"], arrays["g_user"],
                                arrays["phi"], arrays["G"])
    got = smt.effective_channel(t["hd_user"], t["g_user"], t["phi"], t["G"])
    assert np.allclose(got.numpy(), want, rtol=1e-12, atol=0)


def test_precoder_setara(arrays):
    t = torch_pack(arrays)
    alpha = pc.rzf_regularization(K, SIGMA2, P_MAX)
    h_np = sm.effective_channel(arrays["hd_user"], arrays["g_user"],
                                arrays["phi"], arrays["G"])
    h_t = smt.effective_channel(t["hd_user"], t["g_user"], t["phi"], t["G"])

    want = pc.communication_precoder(h_np, arrays["weights"], P_MAX,
                                     arrays["rho"], alpha)
    got = smt.communication_precoder(h_t, t["weights"], P_MAX,
                                     torch.as_tensor(arrays["rho"],
                                                     dtype=torch.float64), alpha)
    assert np.allclose(got.numpy(), want, rtol=1e-10, atol=1e-18)

    chat_np = pc.estimated_sensing_channel(arrays["g_tgt"][0], arrays["phi"],
                                           arrays["G"])
    chat_t = smt.estimated_sensing_channel(t["g_tgt"][0], t["phi"], t["G"])
    ws_np = pc.sensing_beam(chat_np, P_MAX, arrays["rho"])
    ws_t = smt.sensing_beam(chat_t, P_MAX,
                            torch.as_tensor(arrays["rho"], dtype=torch.float64))
    assert np.allclose(ws_t.numpy(), ws_np, rtol=1e-10, atol=1e-18)


def test_sinr_dan_scnr_setara(arrays):
    t = torch_pack(arrays)
    alpha = pc.rzf_regularization(K, SIGMA2, P_MAX)
    rho_t = torch.as_tensor(arrays["rho"], dtype=torch.float64)

    h_np = sm.effective_channel(arrays["hd_user"], arrays["g_user"],
                                arrays["phi"], arrays["G"])
    Wc_np = pc.communication_precoder(h_np, arrays["weights"], P_MAX,
                                      arrays["rho"], alpha)
    chat_np = pc.estimated_sensing_channel(arrays["g_tgt"][0], arrays["phi"],
                                           arrays["G"])
    ws_np = pc.sensing_beam(chat_np, P_MAX, arrays["rho"])
    c_np, b_np = sm.sensing_channels(arrays["hd_tgt_tx"], arrays["hd_tgt_rx"],
                                     arrays["g_tgt"], arrays["phi"],
                                     arrays["G"], arrays["H"])
    eta = sm.eta_factor(1.0, sm.wavelength_of(3.5e9))

    h_t = smt.effective_channel(t["hd_user"], t["g_user"], t["phi"], t["G"])
    Wc_t = smt.communication_precoder(h_t, t["weights"], P_MAX, rho_t, alpha)
    chat_t = smt.estimated_sensing_channel(t["g_tgt"][0], t["phi"], t["G"])
    ws_t = smt.sensing_beam(chat_t, P_MAX, rho_t)
    c_t, b_t = smt.sensing_channels(t["hd_tgt_tx"], t["hd_tgt_rx"], t["g_tgt"],
                                    t["phi"], t["G"], t["H"])

    assert np.allclose(smt.sinr(h_t, Wc_t, ws_t, SIGMA2).numpy(),
                       sm.sinr(h_np, Wc_np, ws_np, SIGMA2), rtol=1e-9)
    assert np.allclose(smt.rate(smt.sinr(h_t, Wc_t, ws_t, SIGMA2)).numpy(),
                       sm.rate(sm.sinr(h_np, Wc_np, ws_np, SIGMA2)), rtol=1e-9)
    assert np.allclose(
        smt.scnr(c_t, b_t, Wc_t, ws_t, t["Hc"], eta, SIGMA2, L, XI).numpy(),
        sm.scnr(c_np, b_np, Wc_np, ws_np, arrays["Hc"], eta, SIGMA2, L, XI),
        rtol=1e-8)
    assert np.allclose(smt.total_power(Wc_t, ws_t).numpy(),
                       sm.total_power(Wc_np, ws_np), rtol=1e-12)


def test_objektif_terdiferensiasi_ke_phi_rho_dan_p(arrays):
    """Gradien harus ada dan tidak nol untuk ketiga variabel Oracle-GD."""
    t = torch_pack(arrays)
    phi = torch.tensor(arrays["phi"], dtype=torch.float64, requires_grad=True)
    rho_raw = torch.tensor(0.0, dtype=torch.float64, requires_grad=True)
    p_raw = torch.zeros(K, dtype=torch.float64, requires_grad=True)
    alpha = pc.rzf_regularization(K, SIGMA2, P_MAX)
    eta = sm.eta_factor(1.0, sm.wavelength_of(3.5e9))

    rho = torch.sigmoid(rho_raw)
    weights = torch.softmax(p_raw, dim=-1)
    h = smt.effective_channel(t["hd_user"], t["g_user"], phi, t["G"])
    Wc = smt.communication_precoder(h, weights, P_MAX, rho, alpha)
    chat = smt.estimated_sensing_channel(t["g_tgt"][0], phi, t["G"])
    ws = smt.sensing_beam(chat, P_MAX, rho)
    c, b = smt.sensing_channels(t["hd_tgt_tx"], t["hd_tgt_rx"], t["g_tgt"],
                                phi, t["G"], t["H"])
    obj = (smt.rate(smt.sinr(h, Wc, ws, SIGMA2)).min()
           + 1e-3 * smt.scnr(c, b, Wc, ws, t["Hc"], eta, SIGMA2, L, XI).log10().sum())
    obj.backward()
    for name, var in (("phi", phi), ("rho", rho_raw), ("p", p_raw)):
        assert var.grad is not None, name
        assert torch.isfinite(var.grad).all(), name
        assert var.grad.abs().max() > 0, name
