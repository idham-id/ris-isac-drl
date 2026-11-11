"""Pembaruan fasa RIS (docs/EXPERIMENT_DESIGN.md §5.3).

Dua mode, dipilih lewat ``action.phase_update`` di config:

* ``incremental`` (utama):  phi_t = (phi_{t-1} + kappa pi d_phi) mod 2 pi
* ``absolute``   (ablasi A1): phi_t = pi (d_phi + 1)

Mode inkremental membuat fasa RIS menjadi **state**: aksi hanya menggeser
sedikit, sehingga keputusan saat ini membatasi yang berikutnya dan masalahnya
benar-benar sekuensial. Mode absolut memutus ketergantungan itu, dan selisih
keduanya adalah isi ablasi A1.
"""

from __future__ import annotations

import numpy as np

TWO_PI = 2.0 * np.pi


def incremental_update(phi_prev: np.ndarray, delta: np.ndarray,
                       kappa: float) -> np.ndarray:
    """phi_t = (phi_{t-1} + kappa pi delta) mod 2 pi, dengan delta dalam [-1, 1]."""
    delta = np.clip(np.asarray(delta, dtype=float), -1.0, 1.0)
    return np.mod(np.asarray(phi_prev, dtype=float) + float(kappa) * np.pi * delta,
                  TWO_PI)


def absolute_update(delta: np.ndarray, *_unused) -> np.ndarray:
    """phi_t = pi (delta + 1), memetakan [-1, 1] ke [0, 2 pi)."""
    delta = np.clip(np.asarray(delta, dtype=float), -1.0, 1.0)
    return np.mod(np.pi * (delta + 1.0), TWO_PI)


def update_phases(phi_prev: np.ndarray, delta: np.ndarray, mode: str,
                  kappa: float) -> np.ndarray:
    """Terapkan mode pembaruan dari config."""
    if mode == "incremental":
        return incremental_update(phi_prev, delta, kappa)
    if mode == "absolute":
        return absolute_update(delta)
    raise ValueError(f"action.phase_update tidak dikenal: {mode!r} "
                     "(incremental | absolute)")


def random_phases(rng, num_elements: int, size=()) -> np.ndarray:
    """Fasa seragam di [0, 2 pi): inisialisasi episode dan baseline B1."""
    return rng.uniform(0.0, TWO_PI, size=tuple(size) + (int(num_elements),))


def initial_phases(rng, num_elements: int, mode: str = "random",
                   geometric: np.ndarray | None = None) -> np.ndarray:
    """phi_0 episode. ``random`` (default §5.5) atau ``geometric``.

    Mode ``geometric`` adalah mitigasi §10 bila PPO macet: mulai dari profil
    yang sudah masuk akal secara geometris alih-alih dari fasa acak.
    """
    if mode == "random":
        return random_phases(rng, num_elements)
    if mode == "geometric":
        if geometric is None:
            raise ValueError("init_phase 'geometric' butuh profil geometris.")
        return np.mod(np.asarray(geometric, dtype=float), TWO_PI)
    raise ValueError(f"action.init_phase tidak dikenal: {mode!r}")
