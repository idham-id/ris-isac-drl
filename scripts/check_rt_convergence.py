"""Konvergensi solver pada geometri kandidat (jalan sempit).

Premis kuat (penguatan RIS >= 6 dB) bersandar pada klaim bahwa gelombang
LANGSUNG lemah di ROI. Klaim itu bisa palsu karena tiga sebab yang tidak
memunculkan error apa pun:

  1. max_depth terlalu rendah -> pantulan dinding yang dibutuhkan gelombang
     terpandu di lorong sempit tidak pernah dibangkitkan;
  2. max_num_paths_per_src terlalu rendah -> jalur dipotong diam-diam
     (di v0.1 ini menjatuhkan daya 28 dB);
  3. samples_per_src terlalu rendah -> jalur lemah tidak pernah ditemukan.

Ketiganya disapu di sini pada geometri kandidat, untuk kanal LANGSUNG
(8 sumber) dan kanal RIS->ROI (64 sumber, pemakai VRAM terbesar).
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
from risisac.config import load_config
from risisac.scene.synthetic_l import SyntheticLSpec, load_synthetic_l
from risisac.system.signal_model import to_db
from place_geometry import roi_bounds, roi_points
from sweep_premise import build_arrays


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--width", type=float, default=7.0)
    ap.add_argument("--x-bs", type=float, default=-14.5)
    ap.add_argument("--z-bs", type=float, default=10.0)
    ap.add_argument("--y-ris-off", type=float, default=1.0)
    ap.add_argument("--spacing", type=float, default=1.0)
    ap.add_argument("--depths", nargs="+", type=int, default=[3, 5, 7])
    ap.add_argument("--samples", nargs="+", type=float, default=[1e5, 1e6, 1e7])
    ap.add_argument("--paths", nargs="+", type=float, default=[1e5, 1e6])
    ap.add_argument("--link", default="direct", choices=["direct", "ris"])
    ap.add_argument("--batch", type=int, default=None)
    ap.add_argument("--ris-elements", nargs=2, type=int, default=None,
                    help="baris kolom subarray RIS; anggaran jalur bersifat "
                         "PER SUMBER, jadi tidak-mengikat pada 16 sumber "
                         "berlaku juga untuk 64")
    ap.add_argument("--no-diffuse", action="store_true",
                    help="matikan hamburan difus: set jalur jadi kecil dan "
                         "harus konvergen seketika")
    args = ap.parse_args()

    cfg = load_config("base")
    base_spec = SyntheticLSpec.from_config(cfg)
    spec = dataclasses.replace(base_spec, street_width_m=args.width)
    fc = float(cfg["radio"]["carrier_frequency_hz"])
    scene = load_synthetic_l(spec)
    scene.frequency = fc

    a = spec.half_width
    y_ris = a + args.y_ris_off
    ris = np.array([a - 0.1, y_ris, 6.0])
    bs = np.array([args.x_bs, -(a - 2.0), args.z_bs])
    d_min, d_max = [float(v) for v in cfg["scene"]["roi"]["distance_from_ris_m"]]
    h_roi = float(cfg["scene"]["roi"]["height"])
    roi = roi_points(y_ris, a, d_min, d_max, h_roi, args.spacing)
    centre = np.array([0.0, np.mean(roi_bounds(y_ris, d_min, d_max)), h_roi])
    u1 = (bs - ris) / np.linalg.norm(bs - ris)
    u2 = (centre - ris) / np.linalg.norm(centre - ris)
    look = ris + (u1 + u2) / np.linalg.norm(u1 + u2)

    register_cosine_pattern()
    import sionna.rt as rt
    if args.ris_elements is not None:
        cfg["radio"]["ris"] = dict(cfg["radio"]["ris"])
        cfg["radio"]["ris"]["num_rows"] = args.ris_elements[0]
        cfg["radio"]["ris"]["num_cols"] = args.ris_elements[1]
    bs_tx_a, _, rx1, ris_a = build_arrays(cfg, rt)
    n_src = (int(cfg["radio"]["ris"]["num_rows"]) * int(cfg["radio"]["ris"]["num_cols"])
             if args.link == "ris" else int(cfg["radio"]["bs"]["num_tx"]))

    base_st = RayTracingSettings.from_config(cfg)
    if args.batch is not None:
        base_st = dataclasses.replace(base_st, rx_batch_size=args.batch)
    if args.no_diffuse:
        base_st = dataclasses.replace(base_st, diffuse_reflection=False)

    print(f"kandidat: lebar {args.width:.1f} m, BS {bs.tolist()}, RIS {ris.tolist()}, "
          f"{len(roi)} titik ROI @ {args.spacing} m")
    print(f"link {args.link} | {n_src} sumber | batch {base_st.rx_batch_size}")
    print(f"{'depth':>6s} {'samples':>9s} {'paths':>9s} | {'median dB':>10s} "
          f"{'p10 dB':>9s} {'p90 dB':>9s} {'nol':>6s} {'detik':>7s}")
    ref = None
    for depth in args.depths:
        for samples in args.samples:
            for paths in args.paths:
                st = dataclasses.replace(
                    base_st, max_depth=depth, samples_per_src=int(samples),
                    max_num_paths_per_src=int(paths))
                release_gpu_memory()
                t0 = time.time()
                try:
                    if args.link == "direct":
                        c = narrowband_coefficients(scene, bs_tx_a, rx1, bs, roi,
                                                    st, tx_look_at=ris)[:, 0, :]
                    else:
                        c = narrowband_coefficients(scene, ris_a, rx1, ris, roi,
                                                    st, tx_look_at=look)[:, 0, :]
                except Exception as exc:  # OOM dan sejenisnya dilaporkan, bukan fatal
                    print(f"{depth:6d} {samples:9.0e} {paths:9.0e} | "
                          f"GAGAL: {type(exc).__name__}: {str(exc)[:60]}")
                    continue
                power = np.sum(np.abs(c) ** 2, axis=1)
                nz = int((power == 0).sum())
                db = to_db(np.where(power > 0, power, np.nan))
                med = float(np.nanmedian(db))
                if ref is None:
                    ref = med
                print(f"{depth:6d} {samples:9.0e} {paths:9.0e} | {med:10.2f} "
                      f"{float(np.nanpercentile(db, 10)):9.2f} "
                      f"{float(np.nanpercentile(db, 90)):9.2f} {nz:6d} "
                      f"{time.time() - t0:7.1f}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
