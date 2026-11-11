"""B1 - Random (docs/EXPERIMENT_DESIGN.md §6.2).

Fasa RIS diacak seragam setiap langkah; ``rho`` dipilih sekali dari grid pada
split **val** dan dibekukan. Bobot daya seragam.

B1 bukan sekadar "pembanding lemah": ia memisahkan dua sumbu yang mudah
tertukar. Penguatan apa pun yang datang semata dari MEMILIKI RIS dengan fasa
sembarang sudah ada di B1, sehingga selisih metode lain terhadap B1 adalah
nilai dari MENGATUR fasa, bukan dari memasang RIS.
"""

from __future__ import annotations

import numpy as np

from ..system.ris import random_phases
from .common import Snapshot, SystemConstants, evaluate_decision, uniform_weights


def decide(snap: Snapshot, rng, sensing_fraction: float):
    """Keputusan B1: ``(phi, rho, weights)``."""
    phi = random_phases(rng, snap.num_elements, size=(snap.batch,))
    rho = np.full(snap.batch, float(sensing_fraction))
    return phi, rho, uniform_weights(snap.batch, snap.num_users)


def tune_sensing_fraction(snap: Snapshot, const: SystemConstants,
                          rho_grid, seed: int = 0,
                          g_hat_tgt: np.ndarray | None = None) -> dict:
    """Pilih ``rho`` terbaik dari grid berdasarkan reward rata-rata di val.

    Grid disapu pada fasa acak yang SAMA untuk setiap rho (seed tetap),
    sehingga perbandingannya tidak tercemar keberuntungan fasa.
    """
    rng = np.random.default_rng(seed)
    phi = random_phases(rng, snap.num_elements, size=(snap.batch,))
    weights = uniform_weights(snap.batch, snap.num_users)

    rows = []
    for rho in rho_grid:
        out = evaluate_decision(snap, const, phi,
                                np.full(snap.batch, float(rho)), weights,
                                g_hat_tgt)
        rows.append({"rho": float(rho),
                     "reward": float(np.mean(out["reward"])),
                     "min_rate": float(np.mean(out["min_rate"])),
                     "scnr_db": float(np.median(out["worst_scnr_db"])),
                     "detection_rate": float(np.mean(out["detected"]))})
    best = max(rows, key=lambda r: r["reward"])
    return {"best_rho": best["rho"], "grid": rows}
