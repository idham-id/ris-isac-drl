"""Baseline B1-B4 dan precoder (docs/EXPERIMENT_DESIGN.md §5.3, §6.2).

Kanal dibuat sintetis supaya berkas ini cepat dan tidak bergantung pada
prakomputasi. Yang diuji adalah sifat yang membuat perbandingan antar-metode
sah: anggaran daya dipenuhi semua metode, B2 benar-benar memfokuskan, dan
Oracle-GD benar-benar bergerak naik dari titik awalnya.
"""

import sys
from pathlib import Path

import numpy as np
import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from risisac.baselines import geometric, oracle_gd, random_policy     # noqa: E402
from risisac.baselines.common import (Snapshot, SystemConstants,      # noqa: E402
                                      evaluate_decision, uniform_weights)
from risisac.channels.geometry import (focusing_phase_profile,        # noqa: E402
                                       ris_element_positions)
from risisac.system import precoding as pc                            # noqa: E402
from risisac.system import ris                                        # noqa: E402
from risisac.system import signal_model as sm                         # noqa: E402

NT, NR, M, K, Q, B = 8, 8, 16, 2, 1, 6


@pytest.fixture
def const():
    return SystemConstants(noise_power_watt=1e-12, eta=1.7e3,
                           integration_samples=4096, clutter_residual=0.01,
                           beta_s=1.0, scnr_threshold_db=13.0,
                           reward_lambda=1.0, hinge_scale_db=10.0)


@pytest.fixture
def snap():
    rng = np.random.default_rng(3)

    def c(*shape, scale=1e-5):
        return scale * (rng.normal(size=shape) + 1j * rng.normal(size=shape))

    return Snapshot(G=c(M, NT), H=c(NR, M), Hc=c(NR, NT),
                    hd_user=c(B, K, NT, scale=1e-6), g_user=c(B, K, M),
                    hd_tgt_tx=c(B, Q, NT, scale=1e-6),
                    hd_tgt_rx=c(B, Q, NR, scale=1e-6), g_tgt=c(B, Q, M),
                    p_max_watt=np.full(B, 1.0))


def g_hat_of(snap):
    """Estimasi kanal RIS->target: di sini dipakai nilai sebenarnya."""
    return snap.g_tgt[:, 0, :]


# -------------------------------------------------------------- anggaran daya
@pytest.mark.parametrize("rho", [0.0, 0.25, 0.5, 0.99])
def test_semua_metode_memenuhi_anggaran_daya(snap, const, rho):
    """tr(R_x) = P_max persis untuk B1 dan B2, berapa pun rho."""
    rng = np.random.default_rng(0)
    phi1, rho1, w1 = random_policy.decide(snap, rng, rho)
    out1 = evaluate_decision(snap, const, phi1, rho1, w1, g_hat_of(snap))
    assert np.allclose(out1["total_power"], snap.p_max_watt, rtol=1e-9)

    omega = np.ones(K + 1) / (K + 1)
    phi2, rho2, w2 = geometric.decide(snap, snap.g_user, g_hat_of(snap),
                                      omega, rho)
    out2 = evaluate_decision(snap, const, phi2, rho2, w2, g_hat_of(snap))
    assert np.allclose(out2["total_power"], snap.p_max_watt, rtol=1e-9)


def test_p_max_per_snapshot_dihormati(snap, const):
    """P_max diacak per episode saat pelatihan (§5.5): skalanya harus ikut."""
    varied = Snapshot(**{**snap.__dict__,
                         "p_max_watt": np.linspace(0.1, 2.0, B)})
    rng = np.random.default_rng(0)
    phi, rho, w = random_policy.decide(varied, rng, 0.3)
    out = evaluate_decision(varied, const, phi, rho, w, g_hat_of(varied))
    assert np.allclose(out["total_power"], varied.p_max_watt, rtol=1e-9)


# ---------------------------------------------------------------------- B1
def test_b1_fasa_berbeda_tiap_snapshot(snap):
    rng = np.random.default_rng(0)
    phi, _, _ = random_policy.decide(snap, rng, 0.3)
    assert phi.shape == (B, M)
    assert not np.allclose(phi[0], phi[1])
    assert np.all((phi >= 0) & (phi < 2 * np.pi))


def test_b1_memilih_rho_dengan_reward_terbaik(snap, const):
    grid = [0.1, 0.3, 0.5, 0.7]
    out = random_policy.tune_sensing_fraction(snap, const, grid,
                                              g_hat_tgt=g_hat_of(snap))
    assert out["best_rho"] in grid
    best = max(out["grid"], key=lambda r: r["reward"])
    assert best["rho"] == out["best_rho"]


# ---------------------------------------------------------------------- B2
def test_b2_satu_entitas_sama_dengan_profil_fokus():
    """Dengan satu entitas, rumus B2 harus kembali menjadi profil fokus.

    Diuji terhadap ``focusing_phase_profile`` yang diturunkan terpisah dari
    geometri, bukan terhadap dirinya sendiri.
    """
    wavelength = 0.0857
    centre = np.array([0.0, 0.0, 6.0])
    normal = np.array([1.0, 0.0, 0.0])
    xyz = ris_element_positions(centre, normal, 4, 4, wavelength, 0.5)
    source = np.array([-10.0, -12.0, 10.0])
    target = np.array([14.0, 3.0, 1.5])

    # G sedemikian rupa sehingga G a_bar = steering dari sumber ke tiap elemen.
    k = 2 * np.pi / wavelength
    r_src = np.linalg.norm(xyz - source, axis=1)
    u = np.exp(-1j * k * r_src) / r_src
    G = np.stack([u] + [np.zeros_like(u)] * (NT - 1), axis=1)
    r_tgt = np.linalg.norm(xyz - target, axis=1)
    g_hat = (np.exp(-1j * k * r_tgt) / r_tgt)[None, None, :]

    got = geometric.phases(g_hat, G, np.ones(1))[0]
    want = focusing_phase_profile(xyz, source, target, wavelength)
    diff = np.angle(np.exp(1j * (got - want)))
    assert np.max(np.abs(diff - np.median(diff))) < 1e-9   # sama sampai offset


def test_b2_mengungguli_fasa_acak(snap, const):
    """Kalau tidak, rumus geometrisnya salah tanda atau salah indeks."""
    omega = np.concatenate([np.full(K, 0.5 / K), [0.5]])
    phi2, rho2, w2 = geometric.decide(snap, snap.g_user, g_hat_of(snap),
                                      omega, 0.3)
    out2 = evaluate_decision(snap, const, phi2, rho2, w2, g_hat_of(snap))
    rng = np.random.default_rng(0)
    rewards = []
    for _ in range(20):
        phi1, rho1, w1 = random_policy.decide(snap, rng, 0.3)
        rewards.append(np.mean(evaluate_decision(snap, const, phi1, rho1, w1,
                                                 g_hat_of(snap))["reward"]))
    assert np.mean(out2["reward"]) > np.mean(rewards)


def test_b2_grid_mengembalikan_kombinasi_terbaik(snap, const):
    out = geometric.tune(snap, const, snap.g_user, g_hat_of(snap),
                         [0.25, 0.5, 0.75], [0.2, 0.5])
    best = max(out["grid"], key=lambda r: r["reward"])
    assert (best["omega_target"], best["rho"]) == (out["best_omega_target"],
                                                   out["best_rho"])
    assert len(out["grid"]) == 6


# ---------------------------------------------------------------------- B3
def test_b3_menaikkan_reward_dari_titik_awal(snap, const):
    """Oracle-GD harus benar-benar bergerak naik, bukan diam di inisialisasi."""
    settings = oracle_gd.OracleGDSettings(iterations=60, restarts=2,
                                          learning_rate=0.05,
                                          softmin_temperature=0.1, device="cpu")
    start_phi = oracle_gd._initial_phases(snap, settings, np.random.default_rng(0))
    base = evaluate_decision(snap, const, start_phi[0],
                             np.full(B, 0.5), uniform_weights(B, K))
    out = oracle_gd.optimize(snap, const, settings, seed=0)
    assert out["phi"].shape == (B, M)
    assert np.all((out["rho"] >= 0) & (out["rho"] <= 1))
    assert np.allclose(np.sum(out["weights"], axis=-1), 1.0)
    assert np.allclose(out["total_power"], snap.p_max_watt, rtol=1e-9)
    assert np.mean(out["reward"]) > np.mean(base["reward"])


def test_b3_mengungguli_b1(snap, const):
    """Acuan atas harus mengungguli baseline acak; kalau tidak, ada yang salah."""
    settings = oracle_gd.OracleGDSettings(iterations=80, restarts=2,
                                          learning_rate=0.05,
                                          softmin_temperature=0.1, device="cpu")
    out3 = oracle_gd.optimize(snap, const, settings, seed=0)
    rng = np.random.default_rng(0)
    phi1, rho1, w1 = random_policy.decide(snap, rng, 0.5)
    out1 = evaluate_decision(snap, const, phi1, rho1, w1, g_hat_of(snap))
    assert np.mean(out3["reward"]) > np.mean(out1["reward"])


# ---------------------------------------------------------------------- B4
def test_b4_menahan_keputusan(snap):
    t = 10
    phi = np.arange(t)[:, None] * np.ones((1, M))
    rho = np.arange(t, dtype=float)
    w = np.arange(t)[:, None] * np.ones((1, K))
    p, r, ww = oracle_gd.hold_decisions(phi, rho, w, 5)
    assert np.all(r[:5] == 0) and np.all(r[5:] == 5)
    assert np.all(p[3] == 0) and np.all(ww[7] == 5)
    p1, r1, _ = oracle_gd.hold_decisions(phi, rho, w, 1)
    assert np.array_equal(r1, rho)        # D = 1 berarti tanpa penahanan


# ------------------------------------------------------------------- fasa RIS
def test_pembaruan_fasa_inkremental_terbatas():
    phi = np.full(M, 1.0)
    out = ris.update_phases(phi, np.ones(M), "incremental", 0.1)
    assert np.allclose(out, 1.0 + 0.1 * np.pi)
    clipped = ris.update_phases(phi, np.full(M, 5.0), "incremental", 0.1)
    assert np.allclose(clipped, out)      # aksi di luar [-1, 1] dipotong


def test_pembaruan_fasa_absolut_menjangkau_seluruh_lingkaran():
    assert ris.update_phases(None, np.full(M, -1.0), "absolute", 0.1)[0] == \
        pytest.approx(0.0)
    assert ris.update_phases(None, np.zeros(M), "absolute", 0.1)[0] == \
        pytest.approx(np.pi)


def test_mode_fasa_tak_dikenal_ditolak():
    with pytest.raises(ValueError, match="phase_update"):
        ris.update_phases(np.zeros(M), np.zeros(M), "salah", 0.1)


# -------------------------------------------------------------------- RZF
def test_rzf_menekan_interferensi_antar_pengguna(snap, const):
    """RZF harus memberi SINR lebih tinggi daripada beamforming MRT."""
    phi = np.zeros((B, M))
    h_eff = sm.effective_channel(snap.hd_user, snap.g_user, phi, snap.G)
    alpha = pc.rzf_regularization(K, const.noise_power_watt, 1.0)
    weights = uniform_weights(B, K)
    rho = np.full(B, 0.0)
    Wc = pc.communication_precoder(h_eff, weights, 1.0, rho, alpha)
    ws = np.zeros((B, NT), dtype=complex)

    mrt = np.conj(h_eff)
    mrt = np.swapaxes(mrt, -1, -2)
    mrt = mrt / np.linalg.norm(mrt, axis=-2, keepdims=True) / np.sqrt(K)
    sinr_rzf = sm.sinr(h_eff, Wc, ws, const.noise_power_watt)
    sinr_mrt = sm.sinr(h_eff, mrt, ws, const.noise_power_watt)
    assert np.mean(np.min(sinr_rzf, axis=-1)) > np.mean(np.min(sinr_mrt, axis=-1))


# --------------------------------------- dominant_right_singular (E2/E5), Fase 7
def test_dominant_right_singular_memaksimalkan_daya_ke_ris():
    """``G a_bar`` harus mencapai nilai singular terbesar G.

    Itu definisi yang dipakai (E2)/(E5): a_bar adalah arah pancar BS yang
    menyalurkan daya terbanyak ke RIS. Dibandingkan dengan SVD numerik, bukan
    dengan dirinya sendiri.
    """
    rng = np.random.default_rng(0)
    G = (rng.normal(size=(M, NT)) + 1j * rng.normal(size=(M, NT))) / np.sqrt(2)
    a_bar = geometric.dominant_right_singular(G)

    assert a_bar.shape == (NT,)
    assert np.linalg.norm(a_bar) == pytest.approx(1.0)
    sigma_max = np.linalg.svd(G, compute_uv=False)[0]
    assert np.linalg.norm(G @ a_bar) == pytest.approx(sigma_max, rel=1e-10)


def test_dominant_right_singular_mengalahkan_arah_acak():
    """Arah acak mana pun tidak boleh mengungguli a_bar."""
    rng = np.random.default_rng(1)
    G = (rng.normal(size=(M, NT)) + 1j * rng.normal(size=(M, NT))) / np.sqrt(2)
    best = np.linalg.norm(G @ geometric.dominant_right_singular(G))
    for _ in range(50):
        v = rng.normal(size=NT) + 1j * rng.normal(size=NT)
        v /= np.linalg.norm(v)
        assert np.linalg.norm(G @ v) <= best + 1e-9


def test_dominant_right_singular_konjugasi_penting():
    """Tanpa konjugat, arahnya salah untuk konvensi transpose-tanpa-konjugat.

    ``vh[0]`` sendiri memaksimalkan ``norm(G @ conj(v))``, bukan
    ``norm(G @ v)``; pada G kompleks keduanya berbeda nyata.
    """
    rng = np.random.default_rng(2)
    G = (rng.normal(size=(M, NT)) + 1j * rng.normal(size=(M, NT))) / np.sqrt(2)
    _, _, vh = np.linalg.svd(G, full_matrices=False)
    tanpa_konjugat = vh[0] / np.linalg.norm(vh[0])
    benar = geometric.dominant_right_singular(G)
    assert np.linalg.norm(G @ benar) > np.linalg.norm(G @ tanpa_konjugat)
