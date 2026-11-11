"""E0 - validasi ringan model kanal hibrida (docs/EXPERIMENT_DESIGN.md §4.5).

    python scripts/run_e0_validation.py --config base

Tiga bagian, semuanya di scene **ruang bebas** kecuali bagian 3:

1. **Uji implementasi.** Kanal per elemen dari Sionna RT dibandingkan dengan
   model Friis analitik per hop (``channels/validate_analytic.py``), lalu
   kaskade dijumlahkan untuk 3 profil fokus + 1 profil gradien. Ambang
   **< 0,1 dB**. Ini yang menangkap kesalahan konvensi fasa, orientasi array,
   dan indeks elemen -- kesalahan yang tidak menimbulkan error apa pun tetapi
   membuat seluruh hasil salah.
2. **Kalibrasi fisika.** Penguatan kaskade dibandingkan dengan Tang dkk.
   (2021) IEEE TWC Pers. (6), kasus far-field beamforming. Selisih konstannya
   dilaporkan sebagai ``calibration_db``.
3. **Per elemen vs synthetic array.** Selisih dB di grid ROI scene utama,
   untuk tahu apakah mode yang jauh lebih cepat bisa dipakai.

Keluaran: ``results/e0/<config_hash>/`` berisi ``T1_e0.json`` dan ``F3_e0.png``.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from risisac.channels.geometry import (focusing_phase_profile,        # noqa: E402
                                       look_at_angles,
                                       ris_element_positions)
from risisac.channels.patterns import register_cosine_pattern         # noqa: E402
from risisac.channels.rt_extract import (RayTracingSettings,          # noqa: E402
                                         narrowband_coefficients,
                                         release_gpu_memory)
from risisac.channels.validate_analytic import (                      # noqa: E402
    free_space_los_coefficients, tang2021_beamforming_gain, unit_cell_gain)
from risisac.config import config_hash, load_config                   # noqa: E402
from risisac.scene.placement import Placement                         # noqa: E402
from risisac.scene.synthetic_l import (load_free_space,               # noqa: E402
                                       load_scene_from_config)
from risisac.system.signal_model import to_db, wavelength_of          # noqa: E402


def build_arrays(cfg, rt):
    radio, ris_cfg = cfg["radio"], cfg["radio"]["ris"]
    sp = float(ris_cfg["spacing_wavelengths"])
    return {
        "bs_tx": rt.PlanarArray(num_rows=1, num_cols=int(radio["bs"]["num_tx"]),
                                vertical_spacing=0.5, horizontal_spacing=0.5,
                                pattern=str(radio["bs"]["pattern"]),
                                polarization="V"),
        "point": rt.PlanarArray(num_rows=1, num_cols=1,
                                pattern=str(radio["user"]["pattern"]),
                                polarization="V"),
        "ris": rt.PlanarArray(num_rows=int(ris_cfg["num_rows"]),
                              num_cols=int(ris_cfg["num_cols"]),
                              vertical_spacing=sp, horizontal_spacing=sp,
                              pattern=str(ris_cfg["element_pattern"]),
                              polarization="V"),
    }


def element_positions(centre, look_at, num_rows, num_cols, wavelength, spacing):
    """Posisi elemen array planar Sionna di koordinat dunia."""
    normal = np.asarray(look_at, float) - np.asarray(centre, float)
    return ris_element_positions(centre, normal, num_rows, num_cols,
                                 wavelength, spacing)


def phase_profiles(ris_xyz, source, points, wavelength, rng):
    """3 profil fokus (ke tiga titik berbeda) + 1 profil gradien (§4.5)."""
    profiles = {}
    for i, p in enumerate(points[:3]):
        profiles[f"fokus_{i}"] = focusing_phase_profile(ris_xyz, source, p,
                                                        wavelength)
    m = len(ris_xyz)
    profiles["gradien"] = np.mod(np.linspace(0.0, 6.0 * np.pi, m), 2.0 * np.pi)
    return profiles


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", default="base")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--tolerance-db", type=float, default=0.1)
    args = ap.parse_args()

    cfg = load_config(args.config)
    chash = config_hash(cfg)
    repo = Path(__file__).resolve().parents[1]
    out_dir = repo / "results" / "e0" / chash
    out_dir.mkdir(parents=True, exist_ok=True)

    radio, ris_cfg = cfg["radio"], cfg["radio"]["ris"]
    fc = float(radio["carrier_frequency_hz"])
    wl = wavelength_of(fc)
    rows, cols = int(ris_cfg["num_rows"]), int(ris_cfg["num_cols"])
    spacing = float(ris_cfg["spacing_wavelengths"])
    m_elements = rows * cols

    pl = Placement.from_config(cfg)
    st = RayTracingSettings.from_config(cfg)
    register_cosine_pattern()
    import sionna.rt as rt
    arrays = build_arrays(cfg, rt)

    print(f"config hash : {chash}")
    print(f"f_c {fc / 1e9:.2f} GHz | lambda {wl * 100:.2f} cm | M {m_elements} "
          f"({rows}x{cols}, {spacing} lambda)")

    # --------------------------------------------------- scene ruang bebas
    scene = load_free_space()
    scene.frequency = fc
    look = pl.ris_look_at()
    ris_xyz = element_positions(pl.ris_position, look, rows, cols, wl, spacing)
    bs_xyz = element_positions(pl.bs_tx, pl.ris_position, 1,
                               int(radio["bs"]["num_tx"]), wl, 0.5)

    rng = np.random.default_rng(args.seed)
    d_min, d_max = [float(v) for v in cfg["scene"]["roi"]["distance_from_ris_m"]]
    # Titik uji sepanjang jalan B di depan RIS, dalam medan jauh RIS.
    y_ris = float(pl.ris_position[1])
    points = np.stack([
        np.zeros(6),
        y_ris + np.linspace(d_min, d_max, 6),
        np.full(6, float(cfg["scene"]["roi"]["height"])),
    ], axis=1)

    def run(tx_arr, rx_arr, tx_pos, rx_pos, **kw):
        release_gpu_memory()
        return narrowband_coefficients(scene, tx_arr, rx_arr, tx_pos, rx_pos,
                                       st, **kw)

    G_rt = run(arrays["bs_tx"], arrays["ris"], pl.bs_tx,
               pl.ris_position[None, :], tx_look_at=pl.ris_position,
               rx_look_at=look)[0]                                  # (M, Nt)
    g_rt = run(arrays["ris"], arrays["point"], pl.ris_position, points,
               tx_look_at=look)[:, 0, :]                            # (N, M)

    G_an = free_space_los_coefficients(
        bs_xyz, ris_xyz, wl, tx_pattern=str(radio["bs"]["pattern"]),
        rx_pattern=str(ris_cfg["element_pattern"]),
        tx_orientation=look_at_angles(pl.bs_tx, pl.ris_position),
        rx_orientation=look_at_angles(pl.ris_position, look))
    g_an = free_space_los_coefficients(
        ris_xyz, points, wl, tx_pattern=str(ris_cfg["element_pattern"]),
        rx_pattern=str(radio["user"]["pattern"]),
        tx_orientation=look_at_angles(pl.ris_position, look),
        rx_orientation=(0.0, 0.0, 0.0))                             # (N, M)

    per_element = {
        "G_amplitude_max_db": float(np.max(np.abs(
            to_db(np.abs(G_rt) ** 2) - to_db(np.abs(G_an) ** 2)))),
        "g_amplitude_max_db": float(np.max(np.abs(
            to_db(np.abs(g_rt) ** 2) - to_db(np.abs(g_an) ** 2)))),
        "G_phase_max_deg": float(np.max(np.abs(np.angle(
            G_rt * np.conj(G_an) / np.abs(G_rt * np.conj(G_an)))) * 180 / np.pi)),
        "g_phase_max_deg": float(np.max(np.abs(np.angle(
            g_rt * np.conj(g_an) / np.abs(g_rt * np.conj(g_an)))) * 180 / np.pi)),
    }
    print("\n1) Uji implementasi -- per elemen (RT lawan Friis analitik)")
    for name, value in per_element.items():
        unit = "dB" if name.endswith("_db") else "deg"
        print(f"   {name:24s} {value:8.4f} {unit}")

    # Kaskade untuk 3 profil fokus + 1 gradien, memakai precoder yang sama.
    _, _, vh = np.linalg.svd(G_rt, full_matrices=False)
    a_bar = np.conj(vh[0])
    a_bar /= np.linalg.norm(a_bar)
    u_rt, u_an = G_rt @ a_bar, G_an @ a_bar

    profiles = phase_profiles(ris_xyz, pl.bs_tx, points, wl, rng)
    cascade = {}
    for name, phi in profiles.items():
        c_rt = (g_rt * np.exp(1j * phi)[None, :]) @ u_rt
        c_an = (g_an * np.exp(1j * phi)[None, :]) @ u_an
        diff = to_db(np.abs(c_rt) ** 2) - to_db(np.abs(c_an) ** 2)
        cascade[name] = {"max_abs_db": float(np.max(np.abs(diff))),
                         "mean_db": float(np.mean(diff)),
                         "power_rt_db": float(np.mean(to_db(np.abs(c_rt) ** 2)))}
        print(f"   kaskade {name:10s} selisih maks {cascade[name]['max_abs_db']:7.4f} dB"
              f"   (daya rata-rata {cascade[name]['power_rt_db']:7.2f} dB)")

    worst = max(v["max_abs_db"] for v in cascade.values())
    # Fasa per elemen ikut menjadi kriteria, bukan hanya amplitudo dan kaskade.
    # Kaskade saja TIDAK cukup: offset fasa global per pemanggilan ray tracing
    # lolos dari uji kaskade (magnitudonya tak berubah) tetapi merusak
    # penjumlahan koheren h_d + kaskade. Begitulah bug normalize_delays
    # ditemukan (docs/LOG.md 2026-11-11 (g)).
    phase_tol_deg = 1.0
    impl_pass = (worst < args.tolerance_db
                 and max(per_element["G_amplitude_max_db"],
                         per_element["g_amplitude_max_db"]) < args.tolerance_db
                 and max(per_element["G_phase_max_deg"],
                         per_element["g_phase_max_deg"]) < phase_tol_deg)
    per_element["phase_tolerance_deg"] = phase_tol_deg
    print(f"   -> selisih terburuk {worst:.4f} dB "
          f"({'LOLOS' if impl_pass else 'GAGAL'}, ambang {args.tolerance_db} dB)")

    # ---------------------------------------------- 2) kalibrasi fisika Tang
    # Kasus far-field beamforming SISO: satu antena pancar iso, satu titik iso.
    iso1 = rt.PlanarArray(num_rows=1, num_cols=1, pattern="iso", polarization="V")
    G1_rt = run(iso1, arrays["ris"], pl.bs_tx, pl.ris_position[None, :],
                tx_look_at=pl.ris_position, rx_look_at=look)[0][:, 0]   # (M,)
    normal = pl.ris_normal
    to_tx = pl.bs_tx - pl.ris_position
    cos_t = float(np.dot(to_tx / np.linalg.norm(to_tx), normal))
    d1 = float(np.linalg.norm(to_tx))

    calib_rows = []
    for point in points:
        to_rx = point - pl.ris_position
        d2 = float(np.linalg.norm(to_rx))
        cos_r = float(np.dot(to_rx / np.linalg.norm(to_rx), normal))
        g1_rt = run(arrays["ris"], arrays["point"], pl.ris_position,
                    point[None, :], tx_look_at=look)[0, 0, :]           # (M,)
        phi = focusing_phase_profile(ris_xyz, pl.bs_tx, point, wl)
        hybrid = float(np.abs(np.sum(G1_rt * np.exp(1j * phi) * g1_rt)) ** 2)
        tang = tang2021_beamforming_gain(
            d1=d1, d2=d2, wavelength=wl, num_rows=rows, num_cols=cols,
            cell_dx=spacing * wl, cell_dy=spacing * wl,
            gain_tx=1.0, gain_rx=1.0, cell_gain=unit_cell_gain(1.0),
            f_tx=max(cos_t, 0.0), f_rx=max(cos_r, 0.0))
        calib_rows.append({"d1_m": d1, "d2_m": d2,
                           "hybrid_db": to_db(hybrid),
                           "tang2021_db": to_db(tang),
                           "delta_db": to_db(hybrid) - to_db(tang)})

    deltas = np.array([r["delta_db"] for r in calib_rows])
    calibration_db = float(np.mean(deltas))
    print("\n2) Kalibrasi fisika -- Tang dkk. (2021) IEEE TWC Pers. (6)")
    print(f"   {'d2 [m]':>8s} {'hibrida':>10s} {'Tang':>10s} {'selisih':>9s}")
    for r in calib_rows:
        print(f"   {r['d2_m']:8.1f} {r['hybrid_db']:10.2f} "
              f"{r['tang2021_db']:10.2f} {r['delta_db']:+9.2f}")
    print(f"   calibration_db = {calibration_db:+.2f} dB "
          f"(sebaran {deltas.std():.2f} dB)")

    # ------------------------------- 3) per elemen vs synthetic array (scene utama)
    main_scene = load_scene_from_config(cfg)
    grid = pl.roi_grid()
    sub = grid[::max(1, len(grid) // 128)]
    st_syn = dataclasses.replace(st, synthetic_array=True)

    def run_main(settings, tx_arr, rx_arr, tx_pos, rx_pos, **kw):
        release_gpu_memory()
        return narrowband_coefficients(main_scene, tx_arr, rx_arr, tx_pos,
                                       rx_pos, settings, **kw)

    g_per = run_main(st, arrays["ris"], arrays["point"], pl.ris_position, sub,
                     tx_look_at=look)[:, 0, :]
    g_syn = run_main(st_syn, arrays["ris"], arrays["point"], pl.ris_position,
                     sub, tx_look_at=look)[:, 0, :]
    p_per = to_db(np.sum(np.abs(g_per) ** 2, axis=1))
    p_syn = to_db(np.sum(np.abs(g_syn) ** 2, axis=1))
    syn_delta = p_syn - p_per
    synthetic = {"num_points": int(len(sub)),
                 "median_db": float(np.median(syn_delta)),
                 "p95_abs_db": float(np.percentile(np.abs(syn_delta), 95)),
                 "max_abs_db": float(np.max(np.abs(syn_delta)))}
    print("\n3) Per elemen vs synthetic array (grid ROI scene utama)")
    print(f"   {synthetic['num_points']} titik | median {synthetic['median_db']:+.2f} dB"
          f" | p95 |selisih| {synthetic['p95_abs_db']:.2f} dB"
          f" | maks {synthetic['max_abs_db']:.2f} dB")

    # ------------------------------------------------------------- keluaran
    table = {"config_hash": chash, "wavelength_m": wl, "m_elements": m_elements,
             "tolerance_db": args.tolerance_db,
             "implementation_pass": bool(impl_pass),
             "per_element": per_element, "cascade": cascade,
             "calibration_db": calibration_db,
             "calibration_rows": calib_rows,
             "calibration_reference": (
                 "Tang, W., Chen, M. Z., Chen, X., Xu, J., Alexandropoulos, "
                 "G. C., Dai, L., Di Renzo, M., Cheng, Q., & Cui, T. J. (2021). "
                 "Wireless communications with reconfigurable intelligent "
                 "surface: Path loss modeling and experimental measurement. "
                 "IEEE Transactions on Wireless Communications, 20(1), 421-439. "
                 "https://doi.org/10.1109/TWC.2020.3024887 (Pers. 6)"),
             "synthetic_array": synthetic}
    (out_dir / "T1_e0.json").write_text(json.dumps(table, indent=2),
                                        encoding="utf-8")
    (out_dir / "config_used.json").write_text(
        json.dumps(cfg, indent=2, default=str), encoding="utf-8")
    np.save(out_dir / "e0_synthetic_delta_db.npy", syn_delta)

    # Gambar dibuat ULANG dari file hasil, bukan dari variabel dalam memori
    # (CLAUDE.md). Kalau JSON-nya salah, gambarnya ikut salah dan ketahuan.
    from risisac.eval.plots import plot_f3_e0
    loaded = json.loads((out_dir / "T1_e0.json").read_text(encoding="utf-8"))
    loaded["_synthetic_delta_db"] = np.load(out_dir / "e0_synthetic_delta_db.npy")
    plot_f3_e0(loaded, out_dir / "F3_e0.png", tolerance_db=args.tolerance_db)
    print(f"\nHasil: {out_dir}")
    print(f"GATE 2 (bagian E0): {'LOLOS' if impl_pass else 'GAGAL'}")
    return 0 if impl_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
