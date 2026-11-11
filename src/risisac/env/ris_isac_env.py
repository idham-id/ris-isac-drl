"""Environment Gymnasium untuk RIS-ISAC (docs/EXPERIMENT_DESIGN.md §5).

Struktur frame (§5.1), tiap langkah t::

    1. agen memilih a_t dari o_t
    2. RIS diatur ke phi_t; BS mengestimasi h_e,k dari pilot (NMSE eps)
    3. BS menghitung W_c (RZF dari h_hat) dan w_s (dari estimasi posisi target)
    4. transmisi dan sensing; reward dihitung dari kanal SEBENARNYA
    5. tracker diperbarui; entitas bergerak

Yang membuat masalah ini sekuensial, dan bukan bandit:

* fasa RIS **inkremental** -- aksi hanya menggeser phi, sehingga keputusan
  sekarang membatasi yang berikutnya;
* iluminasi sekarang menentukan SCNR, SCNR menentukan ketepatan pengukuran
  posisi (§5.2), pengukuran menentukan estimasi tracker, dan estimasi itu
  menentukan beam sensing berikutnya;
* kanal berubah terhadap waktu karena entitas bergerak.

Environment **tidak mengimpor Sionna** dan hanya membaca HDF5 (CLAUDE.md).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import gymnasium as gym
import numpy as np
from gymnasium import spaces

from ..channels.database import (completed_trajectories, read_static,
                                 read_trajectory)
from ..channels.geometry import ris_element_positions, spherical_steering
from ..config import noise_power_watt
from ..scene.placement import Placement
from ..system import precoding as pc
from ..system import ris as ris_mod
from ..system import signal_model as sm

MODE_PARTIAL = "partial"
MODE_FULL = "full"


# ----------------------------------------------------------------- penyimpanan
class TrajectoryStore:
    """Seluruh lintasan satu split, dimuat ke memori sekali.

    Dimuat di muka supaya ``reset()`` tidak menyentuh disk: dengan 8 env
    paralel dan episode 50 langkah, membaca HDF5 tiap reset akan mendominasi
    waktu langkah dan menggagalkan Gate 4 (>= 1.000 langkah/detik).
    """

    def __init__(self, path: str | Path, split: str):
        self.path = Path(path)
        self.split = str(split)
        self.G, self.H, self.Hc, self.meta = read_static(self.path)
        ids = sorted(completed_trajectories(self.path, self.split))
        if not ids:
            raise ValueError(f"{self.path}: split '{split}' belum diprakomputasi.")
        self.trajectories = [read_trajectory(self.path, self.split, i) for i in ids]
        self.ids = ids

    def __len__(self) -> int:
        return len(self.trajectories)

    def __getitem__(self, index: int):
        return self.trajectories[index]


# -------------------------------------------------------------------- config
@dataclass(frozen=True)
class EnvConfig:
    """Seluruh angka dari ``configs/*.yaml``; tidak ada parameter di kode."""

    num_elements: int
    num_tx: int
    num_rx: int
    num_users: int
    num_targets: int
    episode_steps: int
    dt_s: float
    noise_power_watt: float
    eta: float
    integration_samples: int
    clutter_residual: float
    beta_s: float
    scnr_threshold_db: float
    reward_lambda: float
    hinge_scale_db: float
    p_max_eval_watt: float
    p_max_train_range_watt: tuple[float, float]
    phase_update: str
    phase_step_kappa: float
    init_phase: str
    observation_mode: str
    eff_channel_nmse: float
    sinr_quant_db: float
    sinr_clip_db: tuple[float, float]
    scnr_clip_db: tuple[float, float]
    user_pos_std_m: float
    target_pos_ref_std_m: float
    target_pos_max_std_m: float
    process_noise_std_mps2: float
    init_velocity_std_mps: float
    roi_bounds: tuple[float, float, float, float]
    target_speed_max_mps: float
    wavelength: float
    ris_position: np.ndarray
    ris_normal: np.ndarray
    ris_spacing: float
    ris_rows: int
    ris_cols: int
    roi_height: float

    @classmethod
    def from_config(cls, cfg: dict, observation_mode: str | None = None) -> "EnvConfig":
        radio, ris_cfg, sens = cfg["radio"], cfg["radio"]["ris"], cfg["sensing"]
        obs, act, mob = cfg["observation"], cfg["action"], cfg["mobility"]
        poly = np.asarray(cfg["scene"]["roi"]["polygon"], float)
        wavelength = sm.wavelength_of(float(radio["carrier_frequency_hz"]))
        lo, hi = [float(v) for v in radio["p_max_train_range_dbm"]]
        return cls(
            num_elements=int(ris_cfg["num_rows"]) * int(ris_cfg["num_cols"]),
            num_tx=int(radio["bs"]["num_tx"]), num_rx=int(radio["bs"]["num_rx"]),
            num_users=int(radio["user"]["num_users"]),
            num_targets=int(radio["target"]["num_targets"]),
            episode_steps=int(mob["episode_steps"]), dt_s=float(mob["dt_s"]),
            noise_power_watt=noise_power_watt(cfg),
            eta=sm.eta_factor(float(radio["target"]["rcs_m2"]), wavelength),
            integration_samples=int(sens["integration_samples"]),
            clutter_residual=float(sens["clutter_residual"]),
            beta_s=1.0 if bool(sens["sensing_interferes_users"]) else 0.0,
            scnr_threshold_db=float(sens["scnr_threshold_db"]),
            reward_lambda=float(cfg["reward"]["lambda"]),
            hinge_scale_db=float(cfg["reward"]["hinge_scale_db"]),
            p_max_eval_watt=sm.dbm_to_watt(float(radio["p_max_dbm"])),
            p_max_train_range_watt=(sm.dbm_to_watt(lo), sm.dbm_to_watt(hi)),
            phase_update=str(act["phase_update"]),
            phase_step_kappa=float(act["phase_step_kappa"]),
            init_phase=str(act["init_phase"]),
            observation_mode=str(observation_mode or obs["mode"]),
            eff_channel_nmse=10.0 ** (float(obs["eff_channel_nmse_db"]) / 10.0),
            sinr_quant_db=float(obs["sinr_report_quant_db"]),
            sinr_clip_db=tuple(float(v) for v in obs["sinr_report_clip_db"]),
            scnr_clip_db=tuple(float(v) for v in obs["scnr_clip_db"]),
            user_pos_std_m=float(obs["user_pos_std_m"]),
            target_pos_ref_std_m=float(obs["target_pos_ref_std_m"]),
            target_pos_max_std_m=float(obs["target_pos_max_std_m"]),
            process_noise_std_mps2=float(cfg["tracking"]["process_noise_std_mps2"]),
            init_velocity_std_mps=float(cfg["tracking"]["init_velocity_std_mps"]),
            roi_bounds=(float(poly[:, 0].min()), float(poly[:, 0].max()),
                        float(poly[:, 1].min()), float(poly[:, 1].max())),
            target_speed_max_mps=float(mob["target_speed_mps"][1]),
            wavelength=wavelength,
            ris_position=np.asarray(cfg["scene"]["ris_position"], float),
            ris_normal=np.asarray(cfg["scene"]["ris_normal"], float),
            ris_spacing=float(ris_cfg["spacing_wavelengths"]),
            ris_rows=int(ris_cfg["num_rows"]), ris_cols=int(ris_cfg["num_cols"]),
            roi_height=float(cfg["scene"]["roi"]["height"]),
        )

    @property
    def action_dim(self) -> int:
        """M + 1 + K (§5.3)."""
        return self.num_elements + 1 + self.num_users

    @property
    def observation_dim(self) -> int:
        """174 untuk mode parsial (§5.2); mode penuh menambah 2M(K+Q)."""
        base = (2 * self.num_tx * self.num_users      # h_hat_e
                + self.num_users                      # SINR terlapor
                + 2 * self.num_users                  # posisi pengguna
                + 4                                   # posisi + kecepatan target
                + 2                                   # flag deteksi, SCNR
                + 2 * self.num_elements               # fasa RIS (cos, sin)
                + 1                                   # rho sebelumnya
                + 1)                                  # P_max ternormalisasi
        if self.observation_mode == MODE_FULL:
            base += 2 * self.num_elements * (self.num_users + self.num_targets)
        return base


# --------------------------------------------------------------- environment
class RisIsacEnv(gym.Env):
    """``gymnasium.Env`` untuk RIS-assisted ISAC dengan observasi parsial."""

    metadata: dict = {"render_modes": []}

    def __init__(self, store: TrajectoryStore, env_cfg: EnvConfig,
                 train: bool = True, seed: int | None = None):
        super().__init__()
        self.store = store
        self.cfg = env_cfg
        self.train = bool(train)

        self.action_space = spaces.Box(low=-1.0, high=1.0,
                                       shape=(env_cfg.action_dim,),
                                       dtype=np.float32)
        self.observation_space = spaces.Box(low=-np.inf, high=np.inf,
                                            shape=(env_cfg.observation_dim,),
                                            dtype=np.float32)
        if seed is not None:
            self.np_random, _ = gym.utils.seeding.np_random(seed)
        self._ris_xyz = ris_element_positions(
            env_cfg.ris_position, env_cfg.ris_normal, env_cfg.ris_rows,
            env_cfg.ris_cols, env_cfg.wavelength, env_cfg.ris_spacing)
        self._alpha = pc.rzf_regularization(env_cfg.num_users,
                                            env_cfg.noise_power_watt,
                                            env_cfg.p_max_eval_watt)
        self._G = store.G.astype(np.complex128)
        self._H = store.H.astype(np.complex128)
        self._Hc = store.Hc.astype(np.complex128)
        self._traj = None
        self._episode_counter = -1
        self._reset_state()

    @property
    def G(self) -> np.ndarray:
        """Kanal BS-tx -> RIS (M, Nt); dibutuhkan baseline geometris (§6.2)."""
        return self._G

    @property
    def episode_counter(self) -> int:
        """Berapa kali ``reset()`` sudah dipanggil (mulai dari 0)."""
        return self._episode_counter

    @property
    def trajectory_index(self) -> int:
        """Indeks lintasan episode berjalan."""
        return int(self._traj_index)

    @property
    def _rng(self) -> np.random.Generator:
        """RNG milik Gymnasium, supaya ``reset(seed=...)`` benar-benar menentukan
        seluruh keacakan episode: pemilihan lintasan, P_max, fasa awal, galat
        estimasi kanal, galat posisi, dan derau pengukuran tracker."""
        return self.np_random

    # --------------------------------------------------------------- internal
    def _reset_state(self) -> None:
        self._t = 0
        self._traj_index = -1
        self._phi_prev = np.zeros(self.cfg.num_elements)
        self._rho_prev = 0.0
        self._h_hat = np.zeros((self.cfg.num_users, self.cfg.num_tx), complex)
        self._sinr_db = np.full(self.cfg.num_users, self.cfg.sinr_clip_db[0])
        self._scnr_db = self.cfg.scnr_clip_db[0]
        self._detected = False
        self._p_max = self.cfg.p_max_eval_watt
        self._tracker = None

    def _sample_p_max(self) -> float:
        if not self.train:
            return self.cfg.p_max_eval_watt
        lo, hi = self.cfg.p_max_train_range_watt
        return float(self._rng.uniform(lo, hi))

    def _estimate_channel(self, h_true: np.ndarray) -> np.ndarray:
        """Estimasi kanal efektif dengan NMSE eps (§5.2).

        Derau estimasi diskalakan per PENGGUNA terhadap daya kanal pengguna
        itu, sehingga NMSE-nya benar-benar eps untuk tiap pengguna dan bukan
        hanya rata-rata -- pengguna lemah kalau tidak akan punya estimasi yang
        jauh lebih baik daripada yang dimaksud desain.
        """
        power = np.sum(np.abs(h_true) ** 2, axis=-1, keepdims=True)
        scale = np.sqrt(self.cfg.eff_channel_nmse * power / h_true.shape[-1] / 2.0)
        noise = scale * (self._rng.normal(size=h_true.shape)
                         + 1j * self._rng.normal(size=h_true.shape))
        return h_true + noise

    def _estimated_target_channel(self) -> np.ndarray:
        """g_hat_t: model LoS gelombang sferis ke estimasi posisi tracker."""
        xy = self._tracker.position
        point = np.array([xy[0], xy[1], self.cfg.roi_height])
        return spherical_steering(self._ris_xyz, point, self.cfg.wavelength,
                                  include_amplitude=True)

    def _normalise_xy(self, xy: np.ndarray) -> np.ndarray:
        xmin, xmax, ymin, ymax = self.cfg.roi_bounds
        out = np.asarray(xy, float).reshape(-1, 2).copy()
        out[:, 0] = 2.0 * (out[:, 0] - xmin) / (xmax - xmin) - 1.0
        out[:, 1] = 2.0 * (out[:, 1] - ymin) / (ymax - ymin) - 1.0
        return out.ravel()

    def _observation(self) -> np.ndarray:
        cfg = self.cfg
        t = min(self._t, self._traj.target_pos.shape[1] - 1)

        # Kanal efektif ternormalisasi ke satuan amplitudo SNR: nilainya mentah
        # berorde 1e-5 dan akan membuat lapisan pertama jaringan bekerja di
        # rentang yang buruk bahkan dengan VecNormalize.
        scale = np.sqrt(self._p_max / cfg.noise_power_watt)
        h = (self._h_hat * scale).ravel()
        parts = [h.real, h.imag,
                 self._sinr_db,
                 self._user_position_feature(t),
                 self._target_state_feature(t),
                 np.array([1.0 if self._detected else 0.0, self._scnr_db]),
                 np.cos(self._phi_prev), np.sin(self._phi_prev),
                 np.array([self._rho_prev]),
                 np.array([self._p_max_feature()])]
        if cfg.observation_mode == MODE_FULL:
            g_u = self._traj.user_g[:, t, :].astype(np.complex128) * scale
            g_t = self._traj.target_g[:, t, :].astype(np.complex128) * scale
            parts += [g_u.real.ravel(), g_u.imag.ravel(),
                      g_t.real.ravel(), g_t.imag.ravel()]
        return np.concatenate(parts).astype(np.float32)

    def _user_position_feature(self, t: int) -> np.ndarray:
        true_xy = self._traj.user_pos[:, t, :2]
        if self.cfg.observation_mode == MODE_FULL:
            return self._normalise_xy(true_xy)
        noisy = true_xy + self._rng.normal(0.0, self.cfg.user_pos_std_m,
                                           size=true_xy.shape)
        return self._normalise_xy(noisy)

    def _target_state_feature(self, t: int) -> np.ndarray:
        if self.cfg.observation_mode == MODE_FULL:
            pos = self._traj.target_pos[0, t, :2]
            vel = self._traj.target_vel[0, t, :2]
        else:
            pos, vel = self._tracker.position, self._tracker.velocity
        return np.concatenate([self._normalise_xy(pos),
                               np.clip(vel / self.cfg.target_speed_max_mps,
                                       -2.0, 2.0)])

    def _p_max_feature(self) -> float:
        """P_max episode ini, dipetakan dari rentang pelatihan ke [-1, 1]."""
        lo, hi = self.cfg.p_max_train_range_watt
        lo_db, hi_db = sm.to_db(lo), sm.to_db(hi)
        return float(np.clip(2.0 * (sm.to_db(self._p_max) - lo_db)
                             / (hi_db - lo_db) - 1.0, -2.0, 2.0))

    def _quantise_sinr(self, sinr_linear: np.ndarray) -> np.ndarray:
        lo, hi = self.cfg.sinr_clip_db
        db = sm.to_db(sinr_linear)
        step = self.cfg.sinr_quant_db
        return np.clip(np.round(db / step) * step, lo, hi)

    # ------------------------------------------------------------------- API
    def baseline_context(self) -> dict:
        """Informasi yang dilihat baseline B1/B2 pada awal langkah (§6.2).

        B1 dan B2 bukan jaringan: keduanya tidak membaca vektor observasi,
        melainkan menghitung fasa dari geometri. Supaya keduanya tetap memakai
        informasi yang SAMA dengan agen -- bukan CSI sempurna -- yang diberikan
        di sini hanya: indeks langkah, posisi SEBENARNYA pengguna (pemanggil
        menambahkan galatnya sendiri dengan sigma yang sama seperti §5.2),
        estimasi kanal RIS->target dari tracker, dan P_max episode.

        ``g_hat_tgt`` sengaja diambil di SINI, sebelum ``step``: env membangun
        beam sensing dari state tracker di awal langkah lalu memperbarui
        tracker di akhir (§5.1). Mengambilnya setelah ``step`` menggeser
        baseline satu langkah dan menyelundupkan informasi masa depan.
        """
        t = min(self._t, self._traj.target_pos.shape[1] - 1)
        return {"step": int(self._t),
                "user_pos": self._traj.user_pos[:, t, :2].copy(),
                "target_pos": self._traj.target_pos[0, t, :2].copy(),
                "g_hat_tgt": self._estimated_target_channel(),
                "p_max_watt": float(self._p_max)}

    def reset(self, *, seed: int | None = None, options: dict | None = None):
        super().reset(seed=seed)
        self._reset_state()
        self._episode_counter += 1

        options = options or {}
        index = options.get("trajectory_index")
        if index is None:
            index = int(self._rng.integers(len(self.store)))
        self._traj = self.store[int(index) % len(self.store)]
        self._traj_index = int(index) % len(self.store)
        self._p_max = self._sample_p_max()
        self._phi_prev = ris_mod.initial_phases(self._rng, self.cfg.num_elements,
                                                self.cfg.init_phase)
        from ..tracking import ConstantVelocityKalman
        start = self._traj.target_pos[0, 0, :2]
        noisy = start + self._rng.normal(0.0, self.cfg.target_pos_ref_std_m, 2)
        self._tracker = ConstantVelocityKalman(
            dt_s=self.cfg.dt_s,
            process_noise_std_mps2=self.cfg.process_noise_std_mps2,
        ).initialize(noisy, (0.0, 0.0),
                     position_std_m=self.cfg.target_pos_ref_std_m,
                     velocity_std_mps=self.cfg.init_velocity_std_mps)

        # h_hat di bawah phi_prev: dibutuhkan o_0 (§5.2 "di bawah phi_{t-1}").
        h_true = sm.effective_channel(
            self._traj.user_hd[:, 0, :].astype(np.complex128),
            self._traj.user_g[:, 0, :].astype(np.complex128),
            self._phi_prev, self._G)
        self._h_hat = self._estimate_channel(h_true)
        return self._observation(), {"trajectory_index": self._traj_index}

    def step(self, action):
        cfg = self.cfg
        action = np.clip(np.asarray(action, dtype=float).ravel(), -1.0, 1.0)
        delta, rho_raw, p_raw = np.split(action, [cfg.num_elements,
                                                  cfg.num_elements + 1])
        phi = ris_mod.update_phases(self._phi_prev, delta, cfg.phase_update,
                                    cfg.phase_step_kappa)
        rho = float((rho_raw[0] + 1.0) / 2.0)
        weights = pc.softmax(p_raw)

        t = self._t
        hd_u = self._traj.user_hd[:, t, :].astype(np.complex128)
        g_u = self._traj.user_g[:, t, :].astype(np.complex128)
        hd_tx = self._traj.target_hd_tx[:, t, :].astype(np.complex128)
        hd_rx = self._traj.target_hd_rx[:, t, :].astype(np.complex128)
        g_t = self._traj.target_g[:, t, :].astype(np.complex128)

        # (§5.1 butir 2-3) BS mengestimasi kanal di bawah phi_t lalu precoding.
        h_true = sm.effective_channel(hd_u, g_u, phi, self._G)
        h_hat = self._estimate_channel(h_true)
        Wc = pc.communication_precoder(h_hat, weights, self._p_max, rho,
                                       self._alpha)
        c_hat = pc.estimated_sensing_channel(self._estimated_target_channel(),
                                             phi, self._G)
        ws = pc.sensing_beam(c_hat, self._p_max, rho)

        # (§5.1 butir 4) reward dari kanal SEBENARNYA, bukan dari estimasi.
        c, b = sm.sensing_channels(hd_tx, hd_rx, g_t, phi, self._G, self._H)
        sinr = sm.sinr(h_true, Wc, ws, cfg.noise_power_watt, cfg.beta_s)
        rates = sm.rate(sinr)
        scnr = sm.scnr(c, b, Wc, ws, self._Hc, cfg.eta, cfg.noise_power_watt,
                       cfg.integration_samples, cfg.clutter_residual)
        scnr_db = float(np.min(sm.to_db(scnr)))
        min_rate = float(np.min(rates))
        detected = scnr_db >= cfg.scnr_threshold_db
        deficit = max(cfg.scnr_threshold_db - scnr_db, 0.0)
        reward = float(min_rate - cfg.reward_lambda * deficit / cfg.hinge_scale_db)

        # (§5.1 butir 5) tracker diperbarui, lalu entitas bergerak.
        truth_xy = self._traj.target_pos[0, t, :2]
        if detected:
            from ..tracking import measurement_std
            std = measurement_std(scnr_db, cfg.scnr_threshold_db,
                                  cfg.target_pos_ref_std_m,
                                  cfg.target_pos_max_std_m)
            self._tracker.step(True, truth_xy + self._rng.normal(0.0, std, 2), std)
        else:
            self._tracker.step(False)
        tracker_error = float(np.linalg.norm(self._tracker.position - truth_xy))

        self._phi_prev = phi
        self._rho_prev = rho
        self._h_hat = h_hat
        self._sinr_db = self._quantise_sinr(sinr)
        self._scnr_db = float(np.clip(scnr_db, *cfg.scnr_clip_db))
        self._detected = detected
        self._t = t + 1

        in_roi = bool(self._traj.target_in_roi[0, self._t]) \
            if self._t < self._traj.target_in_roi.shape[1] else False
        truncated = (self._t >= cfg.episode_steps) or (not in_roi)
        info = {
            "rates": rates.copy(), "min_rate": min_rate,
            "sinr_db": sm.to_db(sinr), "scnr_db": scnr_db,
            "detected": detected, "tracker_error_m": tracker_error,
            "rho": rho, "power_weights": weights.copy(),
            "reward_rate_term": min_rate,
            "reward_penalty_term": cfg.reward_lambda * deficit / cfg.hinge_scale_db,
            "total_power": float(sm.total_power(Wc, ws)),
            "p_max_watt": self._p_max, "step": t,
            "trajectory_index": self._traj_index,
        }
        return self._observation(), reward, False, truncated, info
