"""Baseline B1 dan B2 sebagai kebijakan di dalam environment (§6.2).

Fase 3 mengevaluasi baseline pada *snapshot* lepas: satu batch langkah waktu
tanpa urutan. Itu cukup untuk uji kelayakan, tetapi tidak cukup untuk Gate 5,
yang membandingkan agen dengan B1 dan B2 pada **episode** yang sama. Dua hal
baru muncul begitu baseline dijalankan di dalam env:

* estimasi posisi target datang dari **tracker Kalman**, bukan dari galat
  Gaussian i.i.d. -- dan kualitas tracker bergantung pada keputusan sebelumnya;
* episode berakhir saat target meninggalkan ROI, sehingga panjang episode pun
  bergantung keputusan.

Keduanya justru bagian dari masalah yang diklaim paper. Karena itu angka
baseline untuk paper diambil dari jalur ini, bukan dari mesin snapshot.

**Mode fasa.** §6.2 mendefinisikan B1 sebagai "fasa acak per langkah" dan B2
sebagai rumus fasa ABSOLUT. Aksi inkremental (kappa = 0,1) secara prinsip
tidak bisa menghasilkan keduanya dalam satu langkah, jadi env untuk baseline
dijalankan pada ``phase_update='absolute'``. Ini bukan keuntungan yang
diberikan kepada baseline: justru sebaliknya, baseline boleh melompat ke fasa
mana pun seketika, sedangkan agen M1 harus merambat 0,1 pi per langkah.
"""

from __future__ import annotations

import numpy as np

from ..channels.geometry import spherical_steering
from ..system.ris import random_phases
from . import geometric


def los_channel_estimate(positions: np.ndarray, ris_xyz: np.ndarray,
                         wavelength: float, height: float) -> np.ndarray:
    """g_hat: model LoS gelombang sferis RIS -> titik, bentuk ``(..., M)``.

    ``positions`` berbentuk ``(..., 2)`` dalam meter (x, y); ketinggian diambil
    dari ``scene.roi.height`` karena pengguna dan target berada di bidang yang
    sama di versi ramping (§2.1).
    """
    pos = np.asarray(positions, dtype=float).reshape(-1, 2)
    out = np.stack([spherical_steering(ris_xyz,
                                       np.array([p[0], p[1], float(height)]),
                                       wavelength, include_amplitude=True)
                    for p in pos])
    return out.reshape(np.shape(positions)[:-1] + (ris_xyz.shape[0],))


class BaselineEnvPolicy:
    """Antarmuka bersama: ``act(env)`` mengembalikan aksi yang diterima env.

    Aksi env adalah ``[delta (M), rho_raw, p_raw (K)]`` dengan tiap komponen di
    ``[-1, 1]``. Pada mode absolut ``phi = pi (delta + 1)``, sehingga fasa apa
    pun dapat dinyatakan sebagai ``delta = phi / pi - 1``.
    """

    name = "baseline"

    def reset(self, env) -> None:  # noqa: D401 - antarmuka
        """Dipanggil sesudah ``env.reset()``; default tidak melakukan apa-apa."""

    def act(self, env) -> np.ndarray:
        raise NotImplementedError

    @staticmethod
    def _action(phi: np.ndarray, rho: float, num_users: int) -> np.ndarray:
        delta = np.asarray(phi, dtype=float) / np.pi - 1.0
        return np.concatenate([delta, [2.0 * float(rho) - 1.0],
                               np.zeros(int(num_users))])


class RandomEnvPolicy(BaselineEnvPolicy):
    """B1 -- fasa acak seragam tiap langkah, ``rho`` tetap dari grid val."""

    name = "B1"

    def __init__(self, num_elements: int, num_users: int,
                 sensing_fraction: float, seed: int = 0):
        self.num_elements = int(num_elements)
        self.num_users = int(num_users)
        self.rho = float(sensing_fraction)
        self.seed = int(seed)
        self._rng = np.random.default_rng(self.seed)

    def reset(self, env) -> None:
        # RNG diturunkan dari (seed, indeks LINTASAN), bukan dari penghitung
        # episode: dengan penghitung, hasil B1 pada satu lintasan berubah
        # tergantung berapa episode yang kebetulan dijalankan sebelumnya --
        # terukur menggeser reward/langkah 0,26 antara sapuan grid dan
        # evaluasi akhir, padahal keputusannya sama. Fasa acak B1 punya ragam
        # besar, jadi penomoran yang stabil itu bukan kemewahan.
        self._rng = np.random.default_rng((self.seed, env.trajectory_index))

    def act(self, env) -> np.ndarray:
        phi = random_phases(self._rng, self.num_elements)
        return self._action(phi, self.rho, self.num_users)


class GeometricEnvPolicy(BaselineEnvPolicy):
    """B2 -- fasa geometris dari estimasi posisi; ``omega`` dan ``rho`` dari val.

    Bobot ``omega`` disusun seperti di ``geometric.tune``: satu nilai untuk
    target, sisanya dibagi rata ke pengguna.
    """

    name = "B2"

    def __init__(self, num_users: int, ris_xyz: np.ndarray, wavelength: float,
                 roi_height: float, user_pos_std_m: float,
                 omega_target: float, sensing_fraction: float, seed: int = 0):
        self.num_users = int(num_users)
        self.ris_xyz = np.asarray(ris_xyz, dtype=float)
        self.wavelength = float(wavelength)
        self.roi_height = float(roi_height)
        self.user_pos_std_m = float(user_pos_std_m)
        self.omega_target = float(omega_target)
        self.rho = float(sensing_fraction)
        self.seed = int(seed)
        self._rng = np.random.default_rng(self.seed)
        share = (1.0 - self.omega_target) / self.num_users
        self.omega = np.concatenate([np.full(self.num_users, share),
                                     [self.omega_target]])

    def reset(self, env) -> None:
        self._rng = np.random.default_rng((self.seed, env.trajectory_index))

    def act(self, env) -> np.ndarray:
        ctx = env.baseline_context()
        # Galat posisi pengguna dengan sigma yang sama seperti observasi agen
        # (§5.2): B2 memakai informasi yang setara, bukan posisi sebenarnya.
        user_hat = ctx["user_pos"] + self._rng.normal(
            0.0, self.user_pos_std_m, size=ctx["user_pos"].shape)
        g_hat_user = los_channel_estimate(user_hat, self.ris_xyz,
                                          self.wavelength, self.roi_height)
        g_hat = np.concatenate([g_hat_user[None, ...],
                                ctx["g_hat_tgt"][None, None, :]], axis=1)
        phi = geometric.phases(g_hat, env.G, self.omega)[0]
        return self._action(phi, self.rho, self.num_users)


def make_baseline(name: str, cfg: dict, env_cfg, seed: int = 0,
                  **tuned) -> BaselineEnvPolicy:
    """Buat B1/B2 dari config; ``tuned`` berisi hasil sapuan grid val."""
    from ..channels.geometry import ris_element_positions

    if name.lower() in ("b1", "random"):
        return RandomEnvPolicy(env_cfg.num_elements, env_cfg.num_users,
                               float(tuned["rho"]), seed=seed)
    if name.lower() in ("b2", "geometric"):
        ris_xyz = ris_element_positions(env_cfg.ris_position, env_cfg.ris_normal,
                                        env_cfg.ris_rows, env_cfg.ris_cols,
                                        env_cfg.wavelength, env_cfg.ris_spacing)
        return GeometricEnvPolicy(env_cfg.num_users, ris_xyz,
                                  env_cfg.wavelength, env_cfg.roi_height,
                                  env_cfg.user_pos_std_m,
                                  float(tuned["omega_target"]),
                                  float(tuned["rho"]), seed=seed)
    raise ValueError(f"baseline tidak dikenal: {name!r} (b1 | b2)")


def tune_baseline(name: str, env, cfg: dict, env_cfg, indices, seed: int = 0,
                  verbose: bool = False) -> dict:
    """Sapu grid val untuk B1/B2 **lewat env**, pilih reward per langkah terbaik.

    §6.2 menetapkan rho (dan omega untuk B2) "dari grid val"; sapuan ini
    dijalankan pada split val dengan seed tetap, lalu nilainya dibekukan untuk
    test. Dijalankan lewat env, bukan lewat mesin snapshot Fase 3, karena
    baseline yang dibandingkan di Gate 5 juga berjalan lewat env -- menyetel di
    satu jalur lalu melaporkan di jalur lain akan memberi baseline rho yang
    bukan optimalnya.
    """
    from ..eval.rollout import rollout_baseline, summarise

    rho_grid = [float(v) for v in cfg["baselines"]["rho_grid"]]
    if name.lower() in ("b1", "random"):
        combos = [{"rho": r} for r in rho_grid]
    elif name.lower() in ("b2", "geometric"):
        weights = [float(v) for v in cfg["baselines"]["geometric"]["weight_grid"]]
        combos = [{"omega_target": w, "rho": r}
                  for w in weights for r in rho_grid]
    else:
        raise ValueError(f"baseline tidak dikenal: {name!r}")

    rows = []
    for combo in combos:
        policy = make_baseline(name, cfg, env_cfg, seed=seed, **combo)
        out = summarise(rollout_baseline(env, policy, indices, seed))
        rows.append({**combo, **{k: out[k] for k in
                                 ("reward_per_step", "min_rate",
                                  "scnr_median_db", "detection_rate")}})
        if verbose:
            desc = " ".join(f"{k} {v:.2f}" for k, v in combo.items())
            print(f"   {name} {desc} -> reward/langkah {rows[-1]['reward_per_step']:+.3f}")
    best = max(rows, key=lambda r: r["reward_per_step"])
    return {"best": {k: best[k] for k in combos[0]}, "grid": rows}
