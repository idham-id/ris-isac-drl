"""Sapuan geometri untuk premis kuat: penguatan RIS >= 6 dB di >= 80% ROI.

Opsi (a) yang dipilih pengguna. Ukuran yang dipakai SAMA dengan kriteria
Gate 1 (MRT-dengan-RIS lawan MRT-tanpa-RIS), bukan perbandingan pada
precoder a_bar yang melebih-lebihkan peran RIS.

Hipotesis yang diuji: jalan B yang lebih sempit memaksa gelombang langsung
menempuh lebih banyak pantulan dinding untuk sampai ke ROI (jumlah pantulan
~ jarak/lebar), sedangkan hop RIS->ROI tetap LoS dan tidak terpengaruh.

PERINGATAN KEDALAMAN: pada jalan sempit gelombang terpandu butuh lebih banyak
interaksi, jadi max_depth yang terlalu rendah MENJATUHKAN jalur langsung dan
melebih-lebihkan penguatan RIS -- persis artefak +36 dB di v0.1. Sapuan ini
menerima --depth agar kandidat bisa diuji ulang pada kedalaman lebih tinggi.
"""
import argparse
import dataclasses
import sys
import time
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "scripts"))

from risisac.channels.patterns import register_cosine_pattern
from risisac.channels.rt_extract import (RayTracingSettings,
                                         narrowband_coefficients,
                                         release_gpu_memory)
from risisac.config import load_config, noise_power_watt
from risisac.scene.synthetic_l import SyntheticLSpec, load_synthetic_l
from risisac.scene.visibility import los_mask
from risisac.system.signal_model import (cascaded_coefficient, dbm_to_watt,
                                         eta_factor, focus_phases, ideal_scnr,
                                         to_db, wavelength_of)
from place_geometry import roi_bounds, roi_points


def build_arrays(cfg, rt):
    radio, ris_cfg = cfg["radio"], cfg["radio"]["ris"]
    pat = str(radio["bs"]["pattern"])
    sp = float(ris_cfg["spacing_wavelengths"])
    return (
        rt.PlanarArray(num_rows=1, num_cols=int(radio["bs"]["num_tx"]),
                       vertical_spacing=0.5, horizontal_spacing=0.5,
                       pattern=pat, polarization="V"),
        rt.PlanarArray(num_rows=1, num_cols=int(radio["bs"]["num_rx"]),
                       vertical_spacing=0.5, horizontal_spacing=0.5,
                       pattern=pat, polarization="V"),
        rt.PlanarArray(num_rows=1, num_cols=1,
                       pattern=str(radio["user"]["pattern"]), polarization="V"),
        rt.PlanarArray(num_rows=int(ris_cfg["num_rows"]),
                       num_cols=int(ris_cfg["num_cols"]),
                       vertical_spacing=sp, horizontal_spacing=sp,
                       pattern=str(ris_cfg["element_pattern"]), polarization="V"),
    )


def measure(scene, st, arrays, cfg, bs, ris, look, roi, env):
    """Metrik premis pada satu penempatan. Semua RT ada di sini."""
    bs_tx_a, bs_rx_a, rx1, ris_a = arrays
    bs_rx = bs + np.asarray(cfg["scene"]["bs_rx_offset"], float)

    def run(*a, **k):
        release_gpu_memory()
        return narrowband_coefficients(scene, *a, st, **k)

    hd = run(bs_tx_a, rx1, bs, roi, tx_look_at=ris)[:, 0, :]
    hd_rx = run(bs_rx_a, rx1, bs_rx, roi, tx_look_at=ris)[:, 0, :]
    G = run(bs_tx_a, ris_a, bs, ris[None, :], tx_look_at=ris, rx_look_at=look)[0]
    H = run(ris_a, bs_rx_a, ris, bs_rx[None, :], tx_look_at=look, rx_look_at=ris)[0]
    g = run(ris_a, rx1, ris, roi, tx_look_at=look)[:, 0, :]

    _, _, vh = np.linalg.svd(G, full_matrices=False)
    a_bar = np.conj(vh[0])
    a_bar /= np.linalg.norm(a_bar)
    u = G @ a_bar
    phi = focus_phases(u[None, :], g)
    c_casc = cascaded_coefficient(u[None, :], g, phi)
    c_dir = hd @ a_bar
    c_eff = c_dir + c_casc
    b = hd_rx + (np.exp(1j * phi) * g) @ H.T

    # Kriteria Gate 1: MRT dengan RIS lawan MRT tanpa RIS.
    h_eff = hd + (np.exp(1j * phi) * g) @ G
    gain_ris_mrt = np.sum(np.abs(h_eff) ** 2, axis=1)
    gain_dir_mrt = np.sum(np.abs(hd) ** 2, axis=1)
    gain = to_db(gain_ris_mrt) - to_db(gain_dir_mrt)

    p, sigma2, eta, n_int = env["p"], env["sigma2"], env["eta"], env["n_int"]
    snr_ris = to_db(p * np.abs(c_eff) ** 2 / sigma2)
    scnr = to_db(ideal_scnr(c_eff, b, p, eta, sigma2, n_int))
    return {
        "gain_med": float(np.median(gain)),
        "gain_p20": float(np.percentile(gain, 20)),
        "f_gain_0": float((gain > 0).mean()),
        "f_gain_6": float((gain > 6).mean()),
        "dir_med_db": float(np.median(to_db(gain_dir_mrt))),
        "casc_med_db": float(np.median(to_db(np.abs(c_casc) ** 2))),
        "comm_cov": float((snr_ris > env["comm_thr"]).mean()),
        "radar_cov": float((scnr >= env["radar_thr"]).mean()),
        "scnr_med": float(np.median(scnr)),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--widths", nargs="+", type=float, default=[6.0, 8.0, 10.0])
    ap.add_argument("--n-xbs", type=int, default=4, help="berapa posisi BS per lebar")
    ap.add_argument("--xbs-step", type=float, default=4.0)
    ap.add_argument("--z-bs", nargs="+", type=float, default=[10.0])
    ap.add_argument("--depth", type=int, default=None)
    ap.add_argument("--spacing", type=float, default=1.0)
    ap.add_argument("--d-roi", nargs=2, type=float, default=None)
    ap.add_argument("--y-ris-off", nargs="+", type=float, default=[1.0])
    ap.add_argument("--roi-margin", type=float, default=1.0,
                    help="jarak bebas ROI dari dinding; kecil agar trotoar ikut")
    args = ap.parse_args()

    cfg = load_config("base")
    base_spec = SyntheticLSpec.from_config(cfg)
    radio, sens = cfg["radio"], cfg["sensing"]
    fc = float(radio["carrier_frequency_hz"])
    gate = cfg["gate1"]
    env = {
        "p": dbm_to_watt(float(radio["p_max_dbm"])),
        "sigma2": noise_power_watt(cfg),
        "eta": eta_factor(float(radio["target"]["rcs_m2"]), wavelength_of(fc)),
        "n_int": int(sens["integration_samples"]),
        "comm_thr": float(gate["comm_snr_threshold_db"]),
        "radar_thr": float(sens["scnr_threshold_db"]) + float(gate["radar_margin_db"]),
    }
    if args.d_roi is None:
        d_min, d_max = [float(v) for v in cfg["scene"]["roi"]["distance_from_ris_m"]]
    else:
        d_min, d_max = args.d_roi
    h_roi = float(cfg["scene"]["roi"]["height"])

    st = RayTracingSettings.from_config(cfg)
    if args.depth is not None:
        st = dataclasses.replace(st, max_depth=args.depth)

    register_cosine_pattern()
    import sionna.rt as rt
    arrays = build_arrays(cfg, rt)

    print(f"depth {st.max_depth} | grid {args.spacing} m | ROI {d_min:.0f}-{d_max:.0f} m "
          f"dari RIS | P {radio['p_max_dbm']:.0f} dBm | M 64")
    print(f"{'lbr':>4s} {'yR':>5s} {'xBS':>6s} {'zBS':>5s} {'d1':>5s} {'n':>5s} | "
          f"{'dir':>7s} {'casc':>7s} | {'gain':>7s} {'p20':>7s} {'f>0':>6s} "
          f"{'f>6':>6s} | {'comm':>6s} {'radar':>6s} {'SCNR':>6s} {'s':>5s}")
    rows = []
    for width in args.widths:
        spec = dataclasses.replace(base_spec, street_width_m=width)
        scene = load_synthetic_l(spec)
        scene.frequency = fc
        a = spec.half_width
        for yoff in args.y_ris_off:
            y_ris = a + yoff
            ris = np.array([a - 0.1, y_ris, 6.0])
            roi = roi_points(y_ris, a, d_min, d_max, h_roi, args.spacing,
                             margin=args.roi_margin)
            centre = np.array([0.0, np.mean(roi_bounds(y_ris, d_min, d_max)), h_roi])
            u2 = (centre - ris) / np.linalg.norm(centre - ris)
            for z_bs in args.z_bs:
                y_bs = -(a - 2.0)
                done = 0
                first_x = None
                for x_bs in np.arange(-(a + 2.0), -90.0, -1.0):
                    if done >= args.n_xbs:
                        break
                    bs = np.array([x_bs, y_bs, z_bs])
                    if not bool(los_mask(scene, bs, ris[None, :])[0]):
                        continue
                    if float(los_mask(scene, bs, roi).mean()) != 0.0:
                        continue
                    if first_x is None:
                        first_x = x_bs
                    elif abs((x_bs - first_x) % args.xbs_step) > 1e-6:
                        continue
                    u1 = (bs - ris) / np.linalg.norm(bs - ris)
                    nrm = (u1 + u2) / np.linalg.norm(u1 + u2)
                    t0 = time.time()
                    m = measure(scene, st, arrays, cfg, bs, ris, ris + nrm, roi, env)
                    d1 = float(np.linalg.norm(bs - ris))
                    print(f"{width:4.0f} {y_ris:5.1f} {x_bs:6.1f} {z_bs:5.1f} {d1:5.1f} "
                          f"{len(roi):5d} | {m['dir_med_db']:7.1f} {m['casc_med_db']:7.1f} | "
                          f"{m['gain_med']:+7.1f} {m['gain_p20']:+7.1f} {m['f_gain_0']:6.3f} "
                          f"{m['f_gain_6']:6.3f} | {m['comm_cov']:6.3f} {m['radar_cov']:6.3f} "
                          f"{m['scnr_med']:6.1f} {time.time() - t0:5.1f}", flush=True)
                    rows.append((width, y_ris, x_bs, z_bs, d1, m))
                    done += 1
    ok = [r for r in rows if r[5]["f_gain_6"] >= 0.80 and r[5]["radar_cov"] >= 0.80
          and r[5]["comm_cov"] >= 0.90]
    print()
    print(f"kandidat lolos premis kuat (>=6 dB di >=80%): {len(ok)} dari {len(rows)}")
    for r in sorted(ok, key=lambda r: -r[5]["f_gain_6"])[:5]:
        print(f"  lebar {r[0]:.0f} y_RIS {r[1]:.1f} x_BS {r[2]:.1f} z_BS {r[3]:.1f} "
              f"d1 {r[4]:.1f} -> f>6 {r[5]['f_gain_6']:.3f}, median {r[5]['gain_med']:+.1f} dB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
