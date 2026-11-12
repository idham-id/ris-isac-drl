"""Baseline B0, B1, dan B2 sebagai kebijakan di dalam environment (§6.2).

Fase 3 mengevaluasi baseline pada *snapshot* lepas: satu batch langkah waktu
tanpa urutan. Itu cukup untuk uji kelayakan, tetapi tidak cukup untuk Gate 5,
yang membandingkan agen dengan B1 dan B2 pada **episode** yang sama. Dua hal
baru muncul begitu baseline dijalankan di dalam env:

* estimasi posisi target datang dari **tracker Kalman**, bukan dari galat
  Gaussian i.i.d. -- dan kualitas tracker bergantung pada keputusan sebelumnya,
  karena tracker hanya mendapat pengukuran pada langkah yang terdeteksi;
* episode berakhir saat target meninggalkan ROI, sehingga panjangnya berbeda
  antar-lintasan. Panjang itu **tidak** bergantung pada keputusan (``truncated``
  hanya membaca ``target_in_roi`` milik lintasan), jadi semua metode berjalan
  pada langkah yang sama persis -- yang justru membuat perbandingannya adil.

Yang pertama adalah bagian dari masalah yang diklaim paper. Karena itu angka
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


def power_weights_from_share(share: float, num_users: int) -> np.ndarray:
    """Bobot daya dari satu angka: ``share`` ke pengguna 0, sisanya dibagi rata.

    Disusun seperti ``omega`` pada B2 (satu angka untuk target, sisanya dibagi
    rata) supaya grid val B0 memakai bentuk yang sama dan bisa dibaca dengan
    cara yang sama. Dengan K = 2, grid {0,25; 0,5; 0,75} mencakup kedua arah
    ketidakseimbangan -- kedua pengguna punya kanal berbeda, jadi 0,25 dan
    0,75 bukan cerminan satu sama lain.
    """
    rest = (1.0 - float(share)) / max(int(num_users) - 1, 1)
    return np.array([float(share)] + [rest] * (int(num_users) - 1))


class NoRisEnvPolicy(BaselineEnvPolicy):
    """B0 -- sistem TANPA RIS sama sekali, dengan CSI langsung SEMPURNA.

    Dijalankan pada env ber-``no_ris=True`` dan ``perfect_csi=True``, sehingga
    kaskade RIS hilang dari (E2) dan (E5) sementara precoder dibangun dari
    h_d sebenarnya. B0 karena itu bukan "sistem tanpa RIS yang realistis"
    melainkan **batas atasnya**: apa pun yang RIS tambahkan di atas B0 tidak
    bisa dijelaskan sebagai kekurangan estimasi kanal di sisi pembanding.

    Keputusannya tidak bergantung pada waktu maupun observasi: tanpa kaskade,
    satu-satunya tuas yang tersisa adalah pembagian daya. ``delta`` dikirim
    nol; pada mode absolut itu berarti phi = pi untuk semua elemen, dan nilai
    itu memang tidak berpengaruh karena tiap suku yang memuatnya sudah hilang.
    """

    name = "B0"

    def __init__(self, num_elements: int, num_users: int,
                 sensing_fraction: float, weight_share: float):
        self.num_elements = int(num_elements)
        self.num_users = int(num_users)
        self.rho = float(sensing_fraction)
        self.weights = power_weights_from_share(weight_share, num_users)

    def act(self, env) -> np.ndarray:
        return np.concatenate([np.zeros(self.num_elements),
                               [2.0 * self.rho - 1.0],
                               _weights_to_raw(self.weights)])


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
    """Buat B0/B1/B2 dari config; ``tuned`` berisi hasil sapuan grid val."""
    from ..channels.geometry import ris_element_positions

    if name.lower() in ("b0", "no_ris"):
        return NoRisEnvPolicy(env_cfg.num_elements, env_cfg.num_users,
                              float(tuned["rho"]),
                              float(tuned["weight_share"]))
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
    raise ValueError(f"baseline tidak dikenal: {name!r} (b0 | b1 | b2)")


def tune_baseline(name: str, env, cfg: dict, env_cfg, indices, seed: int = 0,
                  verbose: bool = False) -> dict:
    """Sapu grid val untuk B0/B1/B2 **lewat env**, pilih reward/langkah terbaik.

    §6.2 menetapkan rho (dan omega untuk B2) "dari grid val"; sapuan ini
    dijalankan pada split val dengan seed tetap, lalu nilainya dibekukan untuk
    test. Dijalankan lewat env, bukan lewat mesin snapshot Fase 3, karena
    baseline yang dibandingkan di Gate 5 juga berjalan lewat env -- menyetel di
    satu jalur lalu melaporkan di jalur lain akan memberi baseline rho yang
    bukan optimalnya.

    B0 menyapu rho DAN bobot daya, karena tanpa kaskade RIS hanya itulah
    keputusan yang tersisa baginya; gridnya memakai kembali
    ``baselines.geometric.weight_grid`` ketimbang menambah kunci config baru,
    yang akan mengganti ``config_hash`` seluruh proyek demi tiga angka.
    """
    from ..eval.rollout import rollout_baseline, summarise

    rho_grid = [float(v) for v in cfg["baselines"]["rho_grid"]]
    if name.lower() in ("b0", "no_ris"):
        shares = [float(v) for v in cfg["baselines"]["geometric"]["weight_grid"]]
        combos = [{"weight_share": w, "rho": r}
                  for w in shares for r in rho_grid]
    elif name.lower() in ("b1", "random"):
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


# --------------------------------------------------------------- B3 dan B4
def episode_snapshot(traj, store, env_cfg, steps: int) -> "object":
    """Snapshot (§6.2) untuk ``steps`` langkah pertama satu lintasan.

    Oracle-GD melihat kanal **sebenarnya**, jadi snapshot dibangun langsung
    dari lintasan dan bukan dari observasi env.
    """
    from .common import Snapshot

    s = int(steps)
    return Snapshot(
        G=store.G.astype(np.complex128), H=store.H.astype(np.complex128),
        Hc=store.Hc.astype(np.complex128),
        hd_user=np.transpose(traj.user_hd[:, :s, :], (1, 0, 2)).astype(np.complex128),
        g_user=np.transpose(traj.user_g[:, :s, :], (1, 0, 2)).astype(np.complex128),
        hd_tgt_tx=np.transpose(traj.target_hd_tx[:, :s, :], (1, 0, 2)).astype(np.complex128),
        hd_tgt_rx=np.transpose(traj.target_hd_rx[:, :s, :], (1, 0, 2)).astype(np.complex128),
        g_tgt=np.transpose(traj.target_g[:, :s, :], (1, 0, 2)).astype(np.complex128),
        p_max_watt=np.full(s, float(env_cfg.p_max_eval_watt)),
    )


def episode_length(traj, env_cfg) -> int:
    """Berapa langkah yang benar-benar dijalankan env untuk lintasan ini.

    Env memotong episode saat ``t >= episode_steps`` atau saat target keluar
    ROI (``target_in_roi``). Keduanya **hanya** fungsi lintasan, bukan fungsi
    aksi, sehingga panjang episode sama untuk semua metode dan bisa dihitung
    di muka.
    """
    in_roi = np.asarray(traj.target_in_roi[0], dtype=bool)
    limit = min(int(env_cfg.episode_steps), int(in_roi.shape[0]))
    for t in range(1, limit):
        if not in_roi[t]:
            return t
    return limit


def precompute_oracle(store, cfg: dict, env_cfg, indices, seed: int = 0,
                      verbose: bool = False) -> dict:
    """Jalankan Oracle-GD sekali untuk seluruh (lintasan, langkah) set evaluasi.

    Keputusan B3 hanya bergantung pada kanal sebenarnya pada langkah itu dan
    pada P_max, yang tetap saat evaluasi (§8). Keputusannya karena itu **tidak**
    bergantung pada seed derau, tracker, atau urutan episode, sehingga seluruh
    himpunan dapat dioptimalkan sebagai satu batch dan dipakai ulang untuk
    ketiga seed derau. Menjalankannya per episode akan mengulang pekerjaan yang
    sama persis tiga kali.

    :returns: ``{"decisions": {indeks: (phi, rho, weights)}, "clipped": frac}``
    """
    from . import oracle_gd

    from .common import SystemConstants

    const = SystemConstants.from_config(cfg)
    settings = oracle_gd.OracleGDSettings.from_config(cfg)

    lengths = {int(i): episode_length(store[int(i)], env_cfg) for i in indices}
    snaps = [episode_snapshot(store[int(i)], store, env_cfg, lengths[int(i)])
             for i in indices]
    big = _concat_snapshots(snaps)
    if verbose:
        print(f"   B3: {len(snaps)} lintasan, {big.batch} langkah, "
              f"{settings.restarts} restart x {settings.iterations} iterasi")
    out = oracle_gd.optimize(big, const, settings, seed=int(seed),
                             progress=verbose)

    decisions, offset, outside = {}, 0, 0
    total = 0
    for i in indices:
        n = lengths[int(i)]
        phi = out["phi"][offset:offset + n]
        rho = out["rho"][offset:offset + n]
        w = out["weights"][offset:offset + n]
        p_raw = _weights_to_raw(w)
        outside += int(np.sum(np.abs(p_raw) > 1.0))
        total += int(p_raw.size)
        decisions[int(i)] = (phi, rho, w)
        offset += n
    return {"decisions": decisions, "lengths": lengths,
            "clipped_fraction": outside / max(total, 1),
            "oracle_reward_per_step": float(np.mean(out["reward"]))}


def _concat_snapshots(snaps):
    from .common import Snapshot
    return Snapshot(
        G=snaps[0].G, H=snaps[0].H, Hc=snaps[0].Hc,
        hd_user=np.concatenate([s.hd_user for s in snaps]),
        g_user=np.concatenate([s.g_user for s in snaps]),
        hd_tgt_tx=np.concatenate([s.hd_tgt_tx for s in snaps]),
        hd_tgt_rx=np.concatenate([s.hd_tgt_rx for s in snaps]),
        g_tgt=np.concatenate([s.g_tgt for s in snaps]),
        p_max_watt=np.concatenate([s.p_max_watt for s in snaps]),
    )


def _weights_to_raw(weights: np.ndarray) -> np.ndarray:
    """Balik ``softmax`` ke ``p_raw`` yang diterima env.

    ``softmax`` kebal terhadap pergeseran konstan, jadi logaritma bobot
    dipusatkan dulu. Tanpa pemusatan, bobot seimbang (0,5; 0,5) akan menjadi
    ``p_raw = (-0,69; -0,69)`` yang benar tetapi tidak perlu dekat ke batas
    pemotongan env di [-1, 1]; setelah dipusatkan ia menjadi (0, 0).
    """
    logw = np.log(np.clip(np.asarray(weights, dtype=float), 1e-12, None))
    return logw - np.mean(logw, axis=-1, keepdims=True)


class OracleEnvPolicy(BaselineEnvPolicy):
    """B3 (``hold_period = 1``) dan B4 (``hold_period = D``) dari keputusan beku.

    Keputusan sudah dihitung oleh :func:`precompute_oracle`; kelas ini hanya
    memutarnya kembali ke dalam env supaya metrik hilir -- panjang episode,
    tracker, pemenuhan SCNR -- dihitung oleh mesin yang sama dengan metode lain.
    Env harus dijalankan dengan ``perfect_csi=True`` dan
    ``phase_update='absolute'``.
    """

    def __init__(self, decisions: dict, hold_period: int = 1,
                 name: str | None = None):
        self.decisions = decisions
        self.hold_period = max(1, int(hold_period))
        self.name = name or ("B3" if self.hold_period == 1
                             else f"B4-D{self.hold_period}")
        self._phi = self._rho = self._w = None

    def reset(self, env) -> None:
        from .oracle_gd import hold_decisions

        phi, rho, w = self.decisions[int(env.trajectory_index)]
        if self.hold_period > 1:
            phi, rho, w = hold_decisions(phi, rho, w, self.hold_period)
        self._phi, self._rho, self._w = phi, rho, w

    def act(self, env) -> np.ndarray:
        t = min(int(env.baseline_context()["step"]), len(self._phi) - 1)
        delta = np.asarray(self._phi[t], dtype=float) / np.pi - 1.0
        return np.concatenate([delta, [2.0 * float(self._rho[t]) - 1.0],
                               _weights_to_raw(self._w[t])])
