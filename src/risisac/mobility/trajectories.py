"""Lintasan target dan pengguna di jalan B (docs/EXPERIMENT_DESIGN.md §2.3).

- Delta t = 0,1 s, horizon T = 50 langkah (5 s).
- Target: Q = 1, kecepatan diacak per episode dari 1-10 m/s, bergerak di lajur
  jalan B dengan perubahan lajur acak kecil.
- Pengguna: K = 2, pejalan kaki 0-1,5 m/s, random waypoint di trotoar.
- Split 200 train / 30 val / 50 test dari seed terpisah.

Modul ini **tidak mengimpor Sionna** dan tidak menyentuh GPU: keluarannya murni
posisi, sehingga lintasan bisa dibangkitkan ulang kapan saja tanpa ray tracing
dan environment RL bisa memakainya langsung (CLAUDE.md).

Determinisme. Tiap lintasan memakai ``default_rng([seed_split, traj_id])``,
bukan satu generator berurutan, supaya lintasan ke-i identik berapa pun jumlah
lintasan yang diminta dan prakomputasi yang terputus bisa dilanjutkan di
tengah tanpa menggeser isi lintasan berikutnya.

KELUAR ROI. §2.3 memotong episode bila target keluar ROI. Posisi tetap
dibangkitkan sampai langkah ke-T supaya seluruh array berbentuk persegi, tetapi
**dijepit ke kotak ROI** dan ditandai ``in_roi = False`` sejak langkah target
benar-benar keluar. Penjepitan itu aman karena langkah-langkah tersebut tidak
pernah dipakai (episode sudah terpotong), dan mencegah titik penerima terbang
ke luar scene: target 10 m/s menempuh 50 m dalam 5 s sedangkan ROI hanya 20 m.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class MobilitySpec:
    """Parameter mobilitas, seluruhnya dari ``cfg['mobility']`` dan ``cfg['scene']``."""

    dt_s: float
    episode_steps: int
    num_users: int
    num_targets: int
    target_speed_mps: tuple[float, float]
    user_speed_mps: tuple[float, float]
    lane_x: tuple[float, ...]            # koordinat x pusat tiap lajur
    lane_y_bounds: tuple[float, float]   # rentang y lajur
    sidewalks: tuple[np.ndarray, ...]    # tiap (V, 2) poligon trotoar
    roi_bounds: tuple[float, float, float, float]   # xmin, xmax, ymin, ymax
    height: float
    lane_change_prob_per_step: float
    lane_change_duration_s: float
    lateral_jitter_std_m: float
    entry_margin_fraction: float

    @classmethod
    def from_config(cls, cfg: dict) -> "MobilitySpec":
        mob, scene, radio = cfg["mobility"], cfg["scene"], cfg["radio"]
        tgt = mob.get("target", {}) or {}
        lanes = [np.asarray(p, dtype=float) for p in (scene.get("target_lanes") or [])]
        if not lanes:
            raise ValueError("scene.target_lanes kosong; lintasan target butuh lajur.")
        # Tiap lajur adalah polyline lurus sepanjang y: x tetap, y membentang.
        lane_x = tuple(float(p[:, 0].mean()) for p in lanes)
        y_lo = min(float(p[:, 1].min()) for p in lanes)
        y_hi = max(float(p[:, 1].max()) for p in lanes)

        poly = np.asarray(scene["roi"]["polygon"], dtype=float)
        return cls(
            dt_s=float(mob["dt_s"]),
            episode_steps=int(mob["episode_steps"]),
            num_users=int(radio["user"]["num_users"]),
            num_targets=int(radio["target"]["num_targets"]),
            target_speed_mps=tuple(float(v) for v in mob["target_speed_mps"]),
            user_speed_mps=tuple(float(v) for v in mob["user_speed_mps"]),
            lane_x=lane_x,
            lane_y_bounds=(y_lo, y_hi),
            sidewalks=tuple(np.asarray(p, dtype=float)
                            for p in (scene.get("sidewalks") or [])),
            roi_bounds=(float(poly[:, 0].min()), float(poly[:, 0].max()),
                        float(poly[:, 1].min()), float(poly[:, 1].max())),
            height=float(scene["roi"]["height"]),
            lane_change_prob_per_step=float(tgt["lane_change_prob_per_step"]),
            lane_change_duration_s=float(tgt["lane_change_duration_s"]),
            lateral_jitter_std_m=float(tgt["lateral_jitter_std_m"]),
            entry_margin_fraction=float(tgt["entry_margin_fraction"]),
        )


@dataclass(frozen=True)
class Trajectory:
    """Satu episode. Sumbu waktu selalu ``episode_steps`` panjangnya."""

    traj_id: int
    split: str
    target_pos: np.ndarray      # (Q, T, 3)
    target_vel: np.ndarray      # (Q, T, 3) m/s
    target_in_roi: np.ndarray   # (Q, T) bool
    user_pos: np.ndarray        # (K, T, 3)
    target_speed_mps: np.ndarray  # (Q,) kecepatan nominal episode ini

    @property
    def num_steps(self) -> int:
        return int(self.target_pos.shape[1])

    def all_positions(self) -> np.ndarray:
        """Semua titik penerima episode ini, bentuk (Q*T + K*T, 3).

        Urutannya ditetapkan di sini dan dipakai ulang oleh prakomputasi kanal
        supaya pembongkaran hasil ray tracing tidak pernah salah susun:
        seluruh target dulu (q besar-kecil mengikuti sumbu 0), lalu pengguna.
        """
        return np.concatenate([self.target_pos.reshape(-1, 3),
                               self.user_pos.reshape(-1, 3)], axis=0)


def split_seed(cfg: dict, split: str) -> int:
    seeds = cfg["mobility"]["split_seeds"]
    if split not in seeds:
        raise ValueError(f"split '{split}' tidak ada di mobility.split_seeds "
                         f"({sorted(seeds)})")
    return int(seeds[split])


def num_trajectories(cfg: dict, split: str) -> int:
    n = cfg["mobility"]["num_trajectories"]
    if split not in n:
        raise ValueError(f"split '{split}' tidak ada di mobility.num_trajectories "
                         f"({sorted(n)})")
    return int(n[split])


def _lane_profile(rng, spec: MobilitySpec, steps: int) -> np.ndarray:
    """Koordinat x target per langkah: lajur + perubahan lajur yang mulus.

    Perubahan lajur dimodelkan sebagai interpolasi smoothstep antara dua pusat
    lajur selama ``lane_change_duration_s``, bukan lompatan seketika, supaya
    kecepatan lateral tetap terbatas dan tracker Kalman (§5.2) menghadapi
    gerakan yang masuk akal secara fisik.
    """
    lanes = np.asarray(spec.lane_x, dtype=float)
    lane = int(rng.integers(len(lanes)))
    x = np.full(steps, lanes[lane], dtype=float)

    dur = max(1, int(round(spec.lane_change_duration_s / spec.dt_s)))
    t = 0
    while t < steps:
        if len(lanes) > 1 and rng.random() < spec.lane_change_prob_per_step:
            new_lane = int(rng.choice([i for i in range(len(lanes)) if i != lane]))
            end = min(t + dur, steps)
            u = (np.arange(end - t) + 1.0) / dur
            u = np.clip(u, 0.0, 1.0)
            smooth = u * u * (3.0 - 2.0 * u)         # smoothstep: turunan nol di ujung
            x[t:end] = lanes[lane] + (lanes[new_lane] - lanes[lane]) * smooth
            x[end:] = lanes[new_lane]
            lane = new_lane
            t = end
        else:
            t += 1

    if spec.lateral_jitter_std_m > 0.0:
        x = x + _smooth_noise(rng, steps, spec.lateral_jitter_std_m,
                              spec.lane_change_duration_s / spec.dt_s / 2.0)
    return x


def _smooth_noise(rng, steps: int, std: float, correlation_steps: float) -> np.ndarray:
    """Derau berkorelasi waktu dengan simpangan baku ``std``.

    Derau putih per langkah TIDAK boleh dipakai di sini: kecepatan diturunkan
    dari selisih posisi, dan menurunkan derau putih menghasilkan kecepatan
    lateral yang melonjak (terukur 4,6 m/s untuk jitter 5 cm) -- gerakan yang
    tidak fisik dan merusak asumsi kecepatan-konstan tracker Kalman (§5.2).
    Derau di sini karena itu dihaluskan dengan kernel Gauss lalu dinormalkan
    ulang agar simpangan bakunya tetap ``std``.
    """
    if steps == 0:
        return np.zeros(0)
    sigma = max(1e-6, float(correlation_steps))
    half = max(1, int(np.ceil(3.0 * sigma)))
    t = np.arange(-half, half + 1, dtype=float)
    kernel = np.exp(-0.5 * (t / sigma) ** 2)
    kernel /= np.linalg.norm(kernel)          # jaga varians setelah konvolusi
    raw = rng.normal(0.0, 1.0, size=steps + 2 * half)
    return float(std) * np.convolve(raw, kernel, mode="valid")[:steps]


def _target_track(rng, spec: MobilitySpec) -> tuple[np.ndarray, np.ndarray, np.ndarray, float]:
    """Satu lintasan target: (pos (T,3), vel (T,3), in_roi (T,), kecepatan)."""
    steps = spec.episode_steps
    v_lo, v_hi = spec.target_speed_mps
    speed = float(rng.uniform(v_lo, v_hi))
    direction = 1.0 if rng.random() < 0.5 else -1.0

    # Target MASUK ke ROI, tidak muncul di tengahnya: mulai dekat tepi masuk
    # sesuai arah geraknya. Awal yang seragam di sepanjang ROI akan menyisakan
    # rata-rata hanya separuh ROI di depan target, sehingga episode terpotong
    # jauh lebih awal (terukur: median 17 dari 50 langkah, lawan 44 dengan
    # awal di tepi) dan sebagian besar anggaran ray tracing terbuang pada
    # langkah yang tidak pernah dipakai.
    y_lo, y_hi = spec.lane_y_bounds
    margin = spec.entry_margin_fraction * (y_hi - y_lo)
    if direction > 0:
        y0 = float(rng.uniform(y_lo, y_lo + margin))
    else:
        y0 = float(rng.uniform(y_hi - margin, y_hi))
    y = y0 + direction * speed * spec.dt_s * np.arange(steps)
    x = _lane_profile(rng, spec, steps)
    z = np.full(steps, spec.height)

    xmin, xmax, ymin, ymax = spec.roi_bounds
    inside = (y >= ymin) & (y <= ymax) & (x >= xmin) & (x <= xmax)
    # Sekali keluar, dianggap keluar seterusnya: episode dipotong di titik itu.
    in_roi = np.logical_and.accumulate(inside)

    pos = np.stack([np.clip(x, xmin, xmax), np.clip(y, ymin, ymax), z], axis=1)
    vel = np.zeros_like(pos)
    if steps > 1:
        vel[:-1] = (pos[1:] - pos[:-1]) / spec.dt_s
        vel[-1] = vel[-2]
    return pos, vel, in_roi, speed


def _polygon_bounds(poly: np.ndarray) -> tuple[float, float, float, float]:
    return (float(poly[:, 0].min()), float(poly[:, 0].max()),
            float(poly[:, 1].min()), float(poly[:, 1].max()))


def _random_waypoint(rng, spec: MobilitySpec, poly: np.ndarray) -> np.ndarray:
    """Random waypoint pejalan kaki di dalam satu poligon trotoar, (T, 3).

    Tiap kaki perjalanan memakai kecepatan baru dari ``user_speed_mps``;
    kecepatan 0 berarti pengguna berhenti sampai kaki berikutnya, yang memang
    bagian dari model (rentangnya dimulai dari 0).
    """
    steps = spec.episode_steps
    xmin, xmax, ymin, ymax = _polygon_bounds(poly)
    # Dipotong ke kotak ROI. Trotoar membentang sampai dinding, tetapi ROI
    # berhenti 0,25 m sebelumnya: tanpa pemotongan ini pengguna bisa berjalan
    # di luar ROI (dan 1 cm dari dinding, yang juga buruk untuk ray tracing),
    # padahal §2.1 mensyaratkan pengguna berada di dalam area yang dilayani.
    rxmin, rxmax, rymin, rymax = spec.roi_bounds
    xmin, xmax = max(xmin, rxmin), min(xmax, rxmax)
    ymin, ymax = max(ymin, rymin), min(ymax, rymax)
    if xmin >= xmax or ymin >= ymax:
        raise ValueError("Poligon trotoar tidak beririsan dengan ROI.")
    v_lo, v_hi = spec.user_speed_mps

    here = np.array([rng.uniform(xmin, xmax), rng.uniform(ymin, ymax)])
    goal = np.array([rng.uniform(xmin, xmax), rng.uniform(ymin, ymax)])
    speed = float(rng.uniform(v_lo, v_hi))

    out = np.empty((steps, 2), dtype=float)
    for t in range(steps):
        out[t] = here
        step = speed * spec.dt_s
        d = goal - here
        dist = float(np.linalg.norm(d))
        if dist <= step or dist < 1e-9:
            here = goal.copy()
            goal = np.array([rng.uniform(xmin, xmax), rng.uniform(ymin, ymax)])
            speed = float(rng.uniform(v_lo, v_hi))
        else:
            here = here + d / dist * step

    z = np.full((steps, 1), spec.height)
    return np.concatenate([out, z], axis=1)


def generate_trajectory(spec: MobilitySpec, split: str, traj_id: int,
                        seed: int) -> Trajectory:
    """Satu lintasan, ditentukan sepenuhnya oleh ``(seed, traj_id)``."""
    rng = np.random.default_rng([int(seed), int(traj_id)])

    pos, vel, in_roi, speeds = [], [], [], []
    for _ in range(spec.num_targets):
        p, v, m, s = _target_track(rng, spec)
        pos.append(p)
        vel.append(v)
        in_roi.append(m)
        speeds.append(s)

    if not spec.sidewalks:
        raise ValueError("scene.sidewalks kosong; §2.1 menempatkan pengguna di trotoar.")
    # Pengguna k ditempatkan di trotoar k (bergantian bila K > jumlah trotoar),
    # sehingga kedua pengguna berada di sisi jalan yang berlawanan. Keragaman
    # spasial itu yang membuat masalah multi-pengguna tidak sepele.
    users = [_random_waypoint(rng, spec, spec.sidewalks[k % len(spec.sidewalks)])
             for k in range(spec.num_users)]

    return Trajectory(
        traj_id=int(traj_id), split=str(split),
        target_pos=np.stack(pos), target_vel=np.stack(vel),
        target_in_roi=np.stack(in_roi), user_pos=np.stack(users),
        target_speed_mps=np.asarray(speeds, dtype=float),
    )


def generate_split(cfg: dict, split: str) -> list[Trajectory]:
    """Seluruh lintasan satu split, berurutan menurut ``traj_id``."""
    spec = MobilitySpec.from_config(cfg)
    seed = split_seed(cfg, split)
    return [generate_trajectory(spec, split, i, seed)
            for i in range(num_trajectories(cfg, split))]
