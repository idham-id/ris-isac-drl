"""Model sinyal ISAC (E1)-(E7), docs/TASKS.md Fase 3.

Empat uji yang diminta desain, masing-masing membandingkan bentuk tertutup
dengan sesuatu yang dihitung **dengan cara lain**, bukan dengan dirinya
sendiri: maksimum Rayleigh umum numerik, simulasi simbol Monte Carlo,
anggaran daya, dan persamaan radar bistatik.
"""

import sys
from pathlib import Path

import numpy as np
import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from risisac.system import precoding as pc                           # noqa: E402
from risisac.system import signal_model as sm                        # noqa: E402

NT, NR, M, K, Q = 8, 8, 64, 2, 1
SIGMA2 = 1e-12
L = 4096
XI = 0.01


def random_complex(rng, *shape):
    return (rng.normal(size=shape) + 1j * rng.normal(size=shape)) / np.sqrt(2)


@pytest.fixture
def setup():
    rng = np.random.default_rng(7)
    scale = 1e-5
    return {
        "rng": rng,
        "G": scale * random_complex(rng, M, NT),
        "H": scale * random_complex(rng, NR, M),
        "Hc": scale * random_complex(rng, NR, NT),
        "hd_user": 0.1 * scale * random_complex(rng, K, NT),
        "g_user": scale * random_complex(rng, K, M),
        "hd_tgt_tx": 0.1 * scale * random_complex(rng, Q, NT),
        "hd_tgt_rx": 0.1 * scale * random_complex(rng, Q, NR),
        "g_tgt": scale * random_complex(rng, Q, M),
        "phi": rng.uniform(0, 2 * np.pi, M),
    }


def make_precoders(s, p_max=1.0, rho=0.3):
    h_eff = sm.effective_channel(s["hd_user"], s["g_user"], s["phi"], s["G"])
    weights = pc.softmax(np.zeros(K))
    alpha = pc.rzf_regularization(K, SIGMA2, p_max)
    Wc = pc.communication_precoder(h_eff, weights, p_max, rho, alpha)
    c_hat = pc.estimated_sensing_channel(s["g_tgt"][0], s["phi"], s["G"])
    ws = pc.sensing_beam(c_hat, p_max, rho)
    return h_eff, Wc, ws


# ----------------------------------------------------------------- (E1)
def test_daya_pancar_tidak_pernah_melebihi_p_max(setup):
    """tr(R_x) <= P_max untuk sembarang rho dan bobot daya."""
    rng = setup["rng"]
    for _ in range(20):
        p_max = float(10 ** rng.uniform(-2, 1))
        rho = float(rng.uniform(0.0, 1.0))
        weights = pc.softmax(rng.normal(size=K))
        h_eff = sm.effective_channel(setup["hd_user"], setup["g_user"],
                                     setup["phi"], setup["G"])
        alpha = pc.rzf_regularization(K, SIGMA2, p_max)
        Wc = pc.communication_precoder(h_eff, weights, p_max, rho, alpha)
        c_hat = pc.estimated_sensing_channel(setup["g_tgt"][0], setup["phi"],
                                             setup["G"])
        ws = pc.sensing_beam(c_hat, p_max, rho)
        total = sm.total_power(Wc, ws)
        assert total <= p_max * (1 + 1e-9)
        assert total == pytest.approx(p_max, rel=1e-9)   # dipenuhi persis


def test_trace_kovarians_sama_dengan_total_power(setup):
    _, Wc, ws = make_precoders(setup)
    Rx = sm.transmit_covariance(Wc, ws)
    assert np.trace(Rx).real == pytest.approx(sm.total_power(Wc, ws), rel=1e-10)
    assert np.allclose(Rx, Rx.conj().T)                 # Hermitian
    # R_x berpangkat K + 1 = 3 dari Nt = 8, jadi lima nilai eigennya nol
    # secara struktural dan keluar sebagai +/- epsilon mesin. Ambang PSD
    # karena itu relatif terhadap nilai eigen terbesar, bukan mutlak.
    eigenvalues = np.linalg.eigvalsh(Rx)
    assert np.min(eigenvalues) > -1e-12 * np.max(eigenvalues)
    assert np.sum(eigenvalues > 1e-12 * np.max(eigenvalues)) == K + 1


# ----------------------------------------------------------------- (E3)
def test_sinr_sama_dengan_simulasi_simbol(setup):
    """(E3) dibandingkan dengan Monte Carlo atas simbol dan derau."""
    h_eff, Wc, ws = make_precoders(setup, p_max=1.0, rho=0.3)
    closed = sm.sinr(h_eff, Wc, ws, SIGMA2, beta_s=1.0)

    rng = np.random.default_rng(1234)
    n = 400_000
    sc = random_complex(rng, n, K)
    ss = random_complex(rng, n)
    noise = np.sqrt(SIGMA2) * random_complex(rng, n, K)

    x = sc @ Wc.T + ss[:, None] * ws[None, :]            # (n, Nt)
    y = x @ h_eff.T + noise                              # (n, K)
    desired = sc * (h_eff @ Wc)[np.arange(K), np.arange(K)][None, :]
    empirical = (np.mean(np.abs(desired) ** 2, axis=0)
                 / np.mean(np.abs(y - desired) ** 2, axis=0))
    assert np.allclose(empirical, closed, rtol=0.03)


def test_beta_s_nol_membuang_interferensi_sensing(setup):
    h_eff, Wc, ws = make_precoders(setup)
    assert np.all(sm.sinr(h_eff, Wc, ws, SIGMA2, beta_s=0.0)
                  >= sm.sinr(h_eff, Wc, ws, SIGMA2, beta_s=1.0))


def test_rate_monoton(setup):
    assert sm.rate(np.array([0.0, 1.0, 3.0])) == pytest.approx([0.0, 1.0, 2.0])


# ----------------------------------------------------------------- (E7)
def test_scnr_sama_dengan_maksimum_rayleigh_umum(setup):
    """Bentuk tertutup (E7) = maksimum atas combiner, dihitung numerik.

    SCNR(u) = eta (c^T R_x c^*) |u^H b|^2 / (u^H R_cn u); maksimumnya atas u
    adalah nilai eigen terbesar dari pasangan (b b^H, R_cn).
    """
    from scipy.linalg import eigh

    s = setup
    h_eff, Wc, ws = make_precoders(s)
    c, b = sm.sensing_channels(s["hd_tgt_tx"], s["hd_tgt_rx"], s["g_tgt"],
                               s["phi"], s["G"], s["H"])
    eta = sm.eta_factor(1.0, sm.wavelength_of(3.5e9))
    closed = sm.scnr(c, b, Wc, ws, s["Hc"], eta, SIGMA2, L, XI)

    Rcn = sm.clutter_noise_covariance(s["Hc"], Wc, ws, XI, SIGMA2, L)
    fwd = sm.forward_sensing_power(c, Wc, ws)
    for q in range(Q):
        bq = b[q]
        numeric = eigh(np.outer(bq, bq.conj()), Rcn, eigvals_only=True)[-1]
        assert closed[q] == pytest.approx(eta * fwd[q] * numeric, rel=1e-8)


def test_scnr_turun_saat_clutter_naik(setup):
    s = setup
    _, Wc, ws = make_precoders(s)
    c, b = sm.sensing_channels(s["hd_tgt_tx"], s["hd_tgt_rx"], s["g_tgt"],
                               s["phi"], s["G"], s["H"])
    eta = sm.eta_factor(1.0, sm.wavelength_of(3.5e9))
    low = sm.scnr(c, b, Wc, ws, s["Hc"], eta, SIGMA2, L, 1e-6)
    high = sm.scnr(c, b, Wc, ws, s["Hc"], eta, SIGMA2, L, 1.0)
    assert np.all(high < low)


def test_rcn_hermitian_positif_definit(setup):
    _, Wc, ws = make_precoders(setup)
    Rcn = sm.clutter_noise_covariance(setup["Hc"], Wc, ws, XI, SIGMA2, L)
    assert np.allclose(Rcn, Rcn.conj().T)
    assert np.min(np.linalg.eigvalsh(Rcn)) > 0.0


def test_scnr_tanpa_clutter_sama_dengan_bentuk_ideal(setup):
    """Dengan xi = 0 dan seluruh daya ke sensing, (E7) harus kembali ke
    ``ideal_scnr`` yang dipakai E1 di Fase 1."""
    s = setup
    p_max = 1.0
    c, b = sm.sensing_channels(s["hd_tgt_tx"], s["hd_tgt_rx"], s["g_tgt"],
                               s["phi"], s["G"], s["H"])
    eta = sm.eta_factor(1.0, sm.wavelength_of(3.5e9))
    a_bar = np.zeros(NT, dtype=complex)
    a_bar[0] = 1.0
    ws = np.sqrt(p_max) * a_bar
    Wc = np.zeros((NT, K), dtype=complex)
    full = sm.scnr(c, b, Wc, ws, s["Hc"], eta, SIGMA2, L, 0.0)
    ideal = sm.ideal_scnr(c @ a_bar, b, p_max, eta, SIGMA2, L)
    assert np.allclose(full, ideal, rtol=1e-10)


# ----------------------------------------------------------------- (E6)
def test_eta_cocok_dengan_persamaan_radar_bistatik():
    """eta = 4 pi sigma / lambda^2 membuat kanal ternormalisasi Friis setara
    dengan persamaan radar bistatik::

        P_r / P_t = G_t G_r lambda^2 sigma / ((4 pi)^3 R_t^2 R_r^2)

    Dengan antena isotropik dan ruang bebas, |c| = lambda/(4 pi R_t) dan
    |b| = lambda/(4 pi R_r), sehingga eta |b|^2 |c|^2 harus sama persis.
    """
    wavelength = sm.wavelength_of(3.5e9)
    sigma_rcs = 1.0
    eta = sm.eta_factor(sigma_rcs, wavelength)
    for r_t, r_r in ((20.0, 20.0), (13.0, 47.0), (5.0, 100.0)):
        c = wavelength / (4 * np.pi * r_t)
        b = wavelength / (4 * np.pi * r_r)
        hybrid = eta * c ** 2 * b ** 2
        bistatic = (wavelength ** 2 * sigma_rcs
                    / ((4 * np.pi) ** 3 * r_t ** 2 * r_r ** 2))
        assert hybrid == pytest.approx(bistatic, rel=1e-12)


def test_eta_nilai_desain():
    """§3.4: eta ~ 32,3 dB pada 3,5 GHz dengan sigma_rcs = 1 m^2."""
    eta_db = sm.to_db(sm.eta_factor(1.0, sm.wavelength_of(3.5e9)))
    assert eta_db == pytest.approx(32.3, abs=0.1)


# ----------------------------------------------------------------- (E9)
def test_reward_menghukum_hanya_di_bawah_ambang():
    base = sm.reward(np.array([5.0]), np.array([20.0]), 13.0, 1.0, 10.0)
    assert base == pytest.approx([5.0])                      # di atas: tanpa hukuman
    above = sm.reward(np.array([5.0]), np.array([40.0]), 13.0, 1.0, 10.0)
    assert above == pytest.approx([5.0])                     # lebih tinggi: tetap sama
    below = sm.reward(np.array([5.0]), np.array([3.0]), 13.0, 1.0, 10.0)
    assert below == pytest.approx([5.0 - 1.0 * 10.0 / 10.0])


# ------------------------------------------------------------- batching
def test_bentuk_batch_konsisten(setup):
    s = setup
    t = 6
    phi = np.tile(s["phi"], (t, 1))
    hd = np.tile(s["hd_user"], (t, 1, 1))
    g = np.tile(s["g_user"], (t, 1, 1))
    h_eff = sm.effective_channel(hd, g, phi, s["G"])
    assert h_eff.shape == (t, K, NT)
    single = sm.effective_channel(s["hd_user"], s["g_user"], s["phi"], s["G"])
    assert np.allclose(h_eff[3], single)

    weights = np.tile(pc.softmax(np.zeros(K)), (t, 1))
    rho = np.full(t, 0.3)
    Wc = pc.communication_precoder(h_eff, weights, 1.0,
                                   rho, pc.rzf_regularization(K, SIGMA2, 1.0))
    c_hat = pc.estimated_sensing_channel(np.tile(s["g_tgt"][0], (t, 1)), phi, s["G"])
    ws = pc.sensing_beam(c_hat, 1.0, rho)
    assert Wc.shape == (t, NT, K) and ws.shape == (t, NT)
    assert np.allclose(sm.total_power(Wc, ws), 1.0)

    c, b = sm.sensing_channels(np.tile(s["hd_tgt_tx"], (t, 1, 1)),
                               np.tile(s["hd_tgt_rx"], (t, 1, 1)),
                               np.tile(s["g_tgt"], (t, 1, 1)), phi, s["G"], s["H"])
    eta = sm.eta_factor(1.0, sm.wavelength_of(3.5e9))
    out = sm.scnr(c, b, Wc, ws, s["Hc"], eta, SIGMA2, L, XI)
    assert out.shape == (t, Q)
    assert np.allclose(out, out[0])


# ------------------------------------------------- rzf_directions (E3), Fase 7
def test_rzf_directions_ternormalisasi_dan_zero_forcing():
    """Dengan regularisasi -> 0, RZF harus menuju zero-forcing.

    Kriterianya diambil dari (E3): SINR memakai ``h_e,k^T w_j``, jadi yang
    harus mendiagonal adalah ``A^T W`` dengan h_e,k sebagai KOLOM ``A``.
    """
    rng = np.random.default_rng(0)
    h_eff = random_complex(rng, K, NT)                 # (K, Nt)
    w = pc.rzf_directions(h_eff, 1e-12)
    assert w.shape == (NT, K)
    assert np.allclose(np.linalg.norm(w, axis=-2), 1.0)

    cross = h_eff @ w                                   # (K, K) = A^T W
    off = cross - np.diag(np.diag(cross))
    assert np.max(np.abs(off)) < 1e-6 * np.max(np.abs(np.diag(cross)))


def test_rzf_directions_konvensi_gram_bukan_hermitian():
    """``A^T conj(A)`` bukan ``A^H A``: tertukar membuat SINR turun diam-diam.

    Docstring fungsi memperingatkan bahwa kekeliruan ini tidak terdeteksi uji
    daya mana pun. Tes ini mendeteksinya: varian ``A^H A`` gagal menolkan
    interferensi, sementara varian yang benar menolkannya.
    """
    rng = np.random.default_rng(1)
    h_eff = random_complex(rng, K, NT)
    a = np.swapaxes(h_eff, -1, -2)                      # (Nt, K)

    benar = pc.rzf_directions(h_eff, 1e-12)
    gram_salah = np.conj(a).T @ a                       # A^H A
    w_salah = np.conj(a) @ np.linalg.inv(gram_salah + 1e-12 * np.eye(K))
    w_salah = w_salah / np.linalg.norm(w_salah, axis=-2, keepdims=True)

    bocor = lambda w: np.max(np.abs(                    # noqa: E731
        (h_eff @ w) - np.diag(np.diag(h_eff @ w))))
    assert bocor(benar) < 1e-9
    assert bocor(w_salah) > 1e-3 * np.max(np.abs(h_eff @ w_salah))


def test_rzf_directions_regularisasi_menahan_kanal_hampir_kolinear():
    """Dua pengguna hampir kolinear: tanpa regularisasi normanya meledak."""
    rng = np.random.default_rng(2)
    h0 = random_complex(rng, NT)
    h_eff = np.stack([h0, h0 + 1e-6 * random_complex(rng, NT)])
    w = pc.rzf_directions(h_eff, 1e-2)
    assert np.all(np.isfinite(w))
    assert np.allclose(np.linalg.norm(w, axis=-2), 1.0)
