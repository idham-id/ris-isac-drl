"""Prakomputasi basis data kanal (docs/TASKS.md Fase 2, §4.3-4.4).

    python scripts/precompute_channels.py --config base --split train

Menghitung kanal statis (**G**, **H**, **H**_c) sekali, lalu untuk tiap langkah
tiap lintasan: **g**_k, **h**_{d,k} untuk pengguna dan **g**_t, **h**_{d,t},
**h**^{(r)}_{d,t} untuk target. Hasilnya ke HDF5 sesuai §4.4.

**Bisa dilanjutkan.** Lintasan yang sudah lengkap dilewati, jadi proses yang
terputus (OOM, listrik padam) tinggal dijalankan ulang dengan perintah yang
sama. Lintasan ke-i selalu identik berapa pun urutan pengerjaannya karena
RNG-nya diturunkan dari ``(seed_split, i)``.

Waktu dan puncak VRAM dicatat ke stdout dan ke ``meta`` di file HDF5
(CLAUDE.md: "Catat puncak VRAM dan waktu prakomputasi di docs/LOG.md").
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from risisac.channels.database import (TrajectoryChannels,        # noqa: E402
                                       database_path,
                                       missing_trajectories,
                                       write_static, write_trajectory)
from risisac.channels.patterns import register_cosine_pattern     # noqa: E402
from risisac.channels.rt_extract import (RayTracingSettings,      # noqa: E402
                                         clutter_channel,
                                         narrowband_coefficients,
                                         release_gpu_memory)
from risisac.config import config_hash, load_config               # noqa: E402
from risisac.mobility import (MobilitySpec, generate_trajectory,  # noqa: E402
                              split_seed)
from risisac.mobility.trajectories import num_trajectories        # noqa: E402
from risisac.scene.placement import Placement                     # noqa: E402
from risisac.scene.synthetic_l import load_scene_from_config      # noqa: E402


def git_commit() -> str:
    """Commit HEAD, atau "" bila git tidak tersedia."""
    import subprocess
    for exe in ("git", r"C:\Program Files\Git\cmd\git.exe"):
        try:
            out = subprocess.run([exe, "rev-parse", "HEAD"],
                                 cwd=str(Path(__file__).resolve().parents[1]),
                                 capture_output=True, text=True, timeout=10)
            if out.returncode == 0:
                return out.stdout.strip()
        except (OSError, subprocess.SubprocessError):
            continue
    return ""


def vram_used_gib() -> float:
    """VRAM terpakai saat ini [GiB], 0 bila tidak ada GPU."""
    try:
        import torch
        if not torch.cuda.is_available():
            return 0.0
        free, total = torch.cuda.mem_get_info()
        return (total - free) / 2 ** 30
    except Exception:
        return 0.0


def build_arrays(cfg, rt):
    """Array BS (tx, rx), penerima titik tunggal, dan array RIS per elemen."""
    radio, ris_cfg = cfg["radio"], cfg["radio"]["ris"]
    pat = str(radio["bs"]["pattern"])
    sp = float(ris_cfg["spacing_wavelengths"])
    return {
        "bs_tx": rt.PlanarArray(num_rows=1, num_cols=int(radio["bs"]["num_tx"]),
                                vertical_spacing=0.5, horizontal_spacing=0.5,
                                pattern=pat, polarization="V"),
        "bs_rx": rt.PlanarArray(num_rows=1, num_cols=int(radio["bs"]["num_rx"]),
                                vertical_spacing=0.5, horizontal_spacing=0.5,
                                pattern=pat, polarization="V"),
        "point": rt.PlanarArray(num_rows=1, num_cols=1,
                                pattern=str(radio["user"]["pattern"]),
                                polarization="V"),
        "ris": rt.PlanarArray(num_rows=int(ris_cfg["num_rows"]),
                              num_cols=int(ris_cfg["num_cols"]),
                              vertical_spacing=sp, horizontal_spacing=sp,
                              pattern=str(ris_cfg["element_pattern"]),
                              polarization="V"),
    }


def compute_static(scene, arrays, pl: Placement, st: RayTracingSettings):
    """**G** (M, Nt), **H** (Nr, M), **H**_c (Nr, Nt)."""
    look = pl.ris_look_at()
    release_gpu_memory()
    G = narrowband_coefficients(scene, arrays["bs_tx"], arrays["ris"], pl.bs_tx,
                                pl.ris_position[None, :], st,
                                tx_look_at=pl.ris_position, rx_look_at=look)[0]
    release_gpu_memory()
    H = narrowband_coefficients(scene, arrays["ris"], arrays["bs_rx"],
                                pl.ris_position, pl.bs_rx[None, :], st,
                                tx_look_at=look, rx_look_at=pl.ris_position)[0]
    release_gpu_memory()
    Hc = clutter_channel(scene, arrays["bs_tx"], arrays["bs_rx"], pl.bs_tx,
                         pl.bs_rx, st, tx_look_at=pl.ris_position,
                         rx_look_at=pl.ris_position)
    return G, H, Hc


def compute_trajectory(scene, arrays, pl: Placement, st: RayTracingSettings,
                       traj) -> TrajectoryChannels:
    """Kanal seluruh titik satu lintasan.

    Semua target dan pengguna disatukan menjadi SATU panggilan ray tracing per
    jenis link, lalu dipotong kembali memakai urutan ``Trajectory.all_positions``.
    Menggabungkannya penting: biaya per panggilan didominasi pemasangan
    perangkat ke scene, bukan jumlah penerima.
    """
    look = pl.ris_look_at()
    q, t = traj.target_pos.shape[:2]
    k = traj.user_pos.shape[0]
    n_tgt = q * t

    points = traj.all_positions()                 # (Q*T + K*T, 3)

    def run(tx_array, rx_array, tx_pos, rx_pos, **kw):
        release_gpu_memory()
        return narrowband_coefficients(scene, tx_array, rx_array, tx_pos,
                                       rx_pos, st, **kw)

    g = run(arrays["ris"], arrays["point"], pl.ris_position, points,
            tx_look_at=look)[:, 0, :]                        # (N, M)
    hd = run(arrays["bs_tx"], arrays["point"], pl.bs_tx, points,
             tx_look_at=pl.ris_position)[:, 0, :]            # (N, Nt)
    hd_rx = run(arrays["bs_rx"], arrays["point"], pl.bs_rx,
                points[:n_tgt], tx_look_at=pl.ris_position)[:, 0, :]   # (Q*T, Nr)

    return TrajectoryChannels(
        traj_id=traj.traj_id,
        user_pos=traj.user_pos,
        user_g=g[n_tgt:].reshape(k, t, -1),
        user_hd=hd[n_tgt:].reshape(k, t, -1),
        target_pos=traj.target_pos,
        target_vel=traj.target_vel,
        target_in_roi=traj.target_in_roi,
        target_g=g[:n_tgt].reshape(q, t, -1),
        target_hd_tx=hd[:n_tgt].reshape(q, t, -1),
        target_hd_rx=hd_rx.reshape(q, t, -1),
        target_speed_mps=traj.target_speed_mps,
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", default="base")
    ap.add_argument("--split", default="train", help="train | val | test | all")
    ap.add_argument("--limit", type=int, default=None,
                    help="hitung paling banyak N lintasan lalu berhenti")
    ap.add_argument("--out", default=None, help="path HDF5 (default dari config)")
    ap.add_argument("--rebuild", action="store_true",
                    help="hapus basis data yang ada dan hitung ulang dari nol")
    args = ap.parse_args()

    cfg = load_config(args.config)
    chash = config_hash(cfg)
    repo = Path(__file__).resolve().parents[1]
    path = (Path(args.out) if args.out
            else database_path(cfg, chash, root=repo / cfg["paths"]["channel_db"]))

    if args.rebuild and path.exists():
        print(f"--rebuild: menghapus {path}")
        path.unlink()

    # config_hash TIDAK menangkap perubahan KODE, hanya config. Basis data
    # yang dihitung dengan kode lama karena itu bisa terbaca sebagai lengkap
    # dan dipakai diam-diam -- persis yang terjadi pada bug normalize_delays
    # (docs/LOG.md 2026-11-11 (g)), di mana seluruh 42.000 titik harus dihitung
    # ulang. Commit disimpan dan ketidakcocokannya dilaporkan.
    head = git_commit()
    if path.exists():
        try:
            from risisac.channels.database import read_static as _rs
            stored = str(dict(_rs(path)[3]).get("git_commit", ""))
        except Exception:
            stored = ""
        if head and stored and stored != head:
            print("\n" + "!" * 72)
            print("PERINGATAN: basis data ini dihitung pada commit "
                  f"{stored[:12]}, sedangkan HEAD {head[:12]}.")
            print("Bila kode kanal berubah di antaranya, isinya TIDAK sah.")
            print("Jalankan ulang dengan --rebuild bila ragu.")
            print("!" * 72 + "\n")

    splits = (["train", "val", "test"] if args.split == "all" else [args.split])
    spec = MobilitySpec.from_config(cfg)
    pl = Placement.from_config(cfg)
    st = RayTracingSettings.from_config(cfg)

    register_cosine_pattern()
    import sionna
    import sionna.rt as rt

    scene = load_scene_from_config(cfg)
    arrays = build_arrays(cfg, rt)

    print(f"config hash : {chash}")
    print(f"basis data  : {path}")
    print(f"scene       : {cfg['scene']['id']} | M {spec and ''}"
          f"{int(cfg['radio']['ris']['num_rows']) * int(cfg['radio']['ris']['num_cols'])}"
          f" | Nt {cfg['radio']['bs']['num_tx']} | Nr {cfg['radio']['bs']['num_rx']}")
    print(f"RT          : depth {st.max_depth} | samples {st.samples_per_src:.0e} "
          f"| paths/src {st.max_num_paths_per_src:.0e} (total {st.max_paths_total:.0e}) "
          f"| batch {st.rx_batch_size}")

    peak = vram_used_gib()
    t_static = time.time()
    G, H, Hc = compute_static(scene, arrays, pl, st)
    peak = max(peak, vram_used_gib())
    t_static = time.time() - t_static
    print(f"kanal statis: G {G.shape} H {H.shape} Hc {Hc.shape} "
          f"dalam {t_static:.1f}s")

    write_static(path, G, H, Hc, {
        "config_hash": chash,
        "scene_id": str(cfg["scene"]["id"]),
        "carrier_frequency_hz": float(cfg["radio"]["carrier_frequency_hz"]),
        "bs_tx_position": pl.bs_tx.tolist(),
        "bs_rx_position": pl.bs_rx.tolist(),
        "ris_position": pl.ris_position.tolist(),
        "ris_normal": pl.ris_normal.tolist(),
        "ris_look_at": pl.ris_look_at().tolist(),
        "sionna_version": str(sionna.__version__),
        "git_commit": head,
        "rt_max_depth": int(st.max_depth),
        "rt_samples_per_src": int(st.samples_per_src),
        "rt_max_num_paths_per_src": int(st.max_num_paths_per_src),
        "rt_max_paths_total": int(st.max_paths_total),
        "rt_synthetic_array": bool(st.synthetic_array),
        "dt_s": float(cfg["mobility"]["dt_s"]),
        "episode_steps": int(cfg["mobility"]["episode_steps"]),
    })

    total_done = 0
    for split in splits:
        total = num_trajectories(cfg, split)
        todo = missing_trajectories(path, split, total)
        seed = split_seed(cfg, split)
        print(f"\n[{split}] {len(todo)} dari {total} lintasan belum dihitung "
              f"(seed {seed})")
        if not todo:
            continue
        t0 = time.time()
        for n, traj_id in enumerate(todo, 1):
            if args.limit is not None and total_done >= args.limit:
                print(f"  berhenti di --limit {args.limit}")
                break
            traj = generate_trajectory(spec, split, traj_id, seed)
            ch = compute_trajectory(scene, arrays, pl, st, traj)
            write_trajectory(path, split, ch)
            peak = max(peak, vram_used_gib())
            total_done += 1
            if n % 10 == 0 or n == len(todo):
                done = time.time() - t0
                rate = done / n
                print(f"  {n:4d}/{len(todo)}  {done:7.1f}s  "
                      f"{rate:5.2f}s/lintasan  sisa ~{rate * (len(todo) - n):6.1f}s  "
                      f"VRAM {vram_used_gib():.2f} GiB", flush=True)
        print(f"[{split}] selesai dalam {time.time() - t0:.1f}s")

    print(f"\npuncak VRAM terpakai: {peak:.2f} GiB")
    print(f"basis data: {path} ({path.stat().st_size / 2**20:.1f} MiB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
