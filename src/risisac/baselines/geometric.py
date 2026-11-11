"""B2 - Geometric (docs/EXPERIMENT_DESIGN.md §6.2).

    phi_m = -arg( sum_i omega_i [g_hat_i]_m [G a_bar]_m )

dengan ``g_hat_i`` model LoS gelombang sferis ke **estimasi** posisi tiap
pengguna dan target, dan ``a_bar`` vektor singular kanan utama **G**.
``omega_i`` dan ``rho`` dipilih dari grid pada split val lalu dibekukan.

Interpretasinya: tiap entitas i ingin elemen m menyefasekan jalur
BS -> elemen m -> entitas i. Bila hanya ada satu entitas, rumus ini persis
profil fokus (``channels.geometry.focusing_phase_profile``). Dengan beberapa
entitas, bobot ``omega_i`` menentukan kompromi -- dan kompromi itu dibuat
sekali di val, tidak per langkah. Di situlah celah yang bisa dimanfaatkan
agen DRL: ia boleh menggeser kompromi mengikuti keadaan.

B2 memakai informasi yang SAMA dengan agen (§6.2): posisi hasil estimasi,
bukan posisi sebenarnya.
"""

from __future__ import annotations

import itertools

import numpy as np

from .common import Snapshot, SystemConstants, evaluate_decision, uniform_weights


def dominant_right_singular(G: np.ndarray) -> np.ndarray:
    """a_bar: vektor singular kanan utama G, dinormalkan.

    Dikonjugasikan agar ``G a_bar`` memaksimalkan daya yang sampai ke RIS
    dengan konvensi transpose-tanpa-konjugat yang dipakai (E2)/(E5).
    """
    _, _, vh = np.linalg.svd(np.asarray(G), full_matrices=False)
    a_bar = np.conj(vh[0])
    return a_bar / np.linalg.norm(a_bar)


def phases(g_hat: np.ndarray, G: np.ndarray, omega: np.ndarray) -> np.ndarray:
    """phi = -arg( sum_i omega_i g_hat_i . (G a_bar) ), bentuk (..., M).

    :param g_hat: (..., I, M) kanal RIS -> entitas (pengguna lalu target)
    :param omega: (I,) bobot, tidak harus berjumlah 1
    """
    u = np.asarray(G) @ dominant_right_singular(G)            # (M,)
    weighted = np.einsum("i,...im->...m", np.asarray(omega, dtype=float),
                         np.asarray(g_hat) * u)
    return np.mod(-np.angle(weighted), 2.0 * np.pi)


def decide(snap: Snapshot, g_hat_user: np.ndarray, g_hat_tgt: np.ndarray,
           omega: np.ndarray, sensing_fraction: float):
    """Keputusan B2: ``(phi, rho, weights)``.

    :param g_hat_user: (B, K, M) estimasi kanal RIS -> pengguna
    :param g_hat_tgt:  (B, M)    estimasi kanal RIS -> target
    """
    g_hat = np.concatenate([np.asarray(g_hat_user),
                            np.asarray(g_hat_tgt)[:, None, :]], axis=1)
    phi = phases(g_hat, snap.G, omega)
    rho = np.full(snap.batch, float(sensing_fraction))
    return phi, rho, uniform_weights(snap.batch, snap.num_users)


def tune(snap: Snapshot, const: SystemConstants, g_hat_user: np.ndarray,
         g_hat_tgt: np.ndarray, weight_grid, rho_grid) -> dict:
    """Sapu ``omega`` dan ``rho`` di val; pilih reward rata-rata terbaik.

    ``weight_grid`` adalah nilai bobot untuk TARGET; bobot pengguna dibuat
    saling melengkapi, sehingga grid satu dimensi ini sudah menjangkau seluruh
    kompromi komunikasi-sensing tanpa meledakkan jumlah kombinasi.
    """
    num_users = snap.num_users
    rows = []
    for w_tgt, rho in itertools.product(weight_grid, rho_grid):
        omega = np.concatenate([np.full(num_users, (1.0 - float(w_tgt)) / num_users),
                                [float(w_tgt)]])
        phi, rho_vec, weights = decide(snap, g_hat_user, g_hat_tgt, omega, rho)
        out = evaluate_decision(snap, const, phi, rho_vec, weights, g_hat_tgt)
        rows.append({"omega_target": float(w_tgt), "rho": float(rho),
                     "reward": float(np.mean(out["reward"])),
                     "min_rate": float(np.mean(out["min_rate"])),
                     "scnr_db": float(np.median(out["worst_scnr_db"])),
                     "detection_rate": float(np.mean(out["detected"]))})
    best = max(rows, key=lambda r: r["reward"])
    return {"best_omega_target": best["omega_target"], "best_rho": best["rho"],
            "grid": rows}
