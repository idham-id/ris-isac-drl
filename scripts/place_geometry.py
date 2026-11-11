"""Cari koordinat BS, RIS, dan ROI yang memenuhi Gate 1 (Fase 1, §2.1).

Desain §2.1 meminta tiga hal sekaligus:
  (i)   BS-RIS ~ 20 m,
  (ii)  ROI = segmen jalan B, 10-30 m dari RIS diukur SEPANJANG jalan,
  (iii) 0% titik ROI punya LoS dari BS.

Ketiganya saling tarik. Bayangan sudut gedung baru menutupi seluruh lebar
jalan B bila BS cukup jauh ke barat, sehingga (iii) mendorong BS menjauh
sementara (i) menariknya mendekat. Syarat bayangannya (turunan di docs/LOG.md):

    u >= 2a / (s - 1),   a = setengah lebar jalan,
    s = (y_dekat - y_BS) / (a - y_BS),   u = jarak BS di barat tepi blok,

sehingga d(BS-RIS) ~ sqrt((2a + u)^2 + dy^2) mengecil cepat bila jalan
dipersempit. Lebar jalan karena itu ikut disapu: §2.2 tidak menetapkannya.

Pemetaan daerah layak memakai oracle LoS (ray_test pada scene sebenarnya),
lalu dipilih jarak BS-RIS terkecil yang masih layak -- SNR radar turun empat
hop terhadap jarak, jadi dekat jauh lebih baik.

    python scripts/place_geometry.py --config base
"""

from __future__ import annotations

import argparse
import dataclasses
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from risisac.config import load_config                                  # noqa: E402
from risisac.scene.synthetic_l import SyntheticLSpec, load_synthetic_l  # noqa: E402
from risisac.scene.visibility import los_mask                           # noqa: E402


def roi_bounds(y_ris: float, d_min: float, d_max: float) -> tuple[float, float]:
    """ROI = segmen jalan B, d_min..d_max dari RIS diukur sepanjang jalan (+y)."""
    return y_ris + d_min, y_ris + d_max


def roi_points(y_ris, half_width, d_min, d_max, height, spacing):
    """Titik grid di dalam segmen ROI, bentuk (N, 3)."""
    xr = half_width - 1.0
    y_lo, y_hi = roi_bounds(y_ris, d_min, d_max)
    xs = np.arange(-xr + spacing / 2, xr, spacing)
    ys = np.arange(y_lo + spacing / 2, y_hi, spacing)
    gx, gy = np.meshgrid(xs, ys, indexing="xy")
    pts = np.stack([gx.ravel(), gy.ravel()], axis=1)
    return np.concatenate([pts, np.full((len(pts), 1), height)], axis=1)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", default="base")
    ap.add_argument("--spacing", type=float, default=1.0, help="grid pencarian (m)")
    ap.add_argument("--widths", nargs="+", type=float, default=[10, 12, 14, 16, 20],
                    help="lebar jalan yang disapu (m)")
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    cfg = load_config(args.config)
    base_spec = SyntheticLSpec.from_config(cfg)
    d_min, d_max = [float(v) for v in cfg["scene"]["roi"]["distance_from_ris_m"]]
    h_roi = float(cfg["scene"]["roi"]["height"])
    z_bs, z_ris = 10.0, 6.0
    fc = float(cfg["radio"]["carrier_frequency_hz"])

    print(f"ROI = segmen jalan B {d_min:.0f}-{d_max:.0f} m dari RIS (sepanjang jalan)")
    print(f"sapuan lebar jalan: {args.widths}")
    print()
    print(f"{'lebar':>6s} {'y_RIS':>6s} {'x_BS':>7s} {'y_BS':>6s} {'d(BS-RIS)':>10s} "
          f"{'n_ROI':>6s} {'LoS BS-ROI':>11s}  layak")

    best = None
    for width in args.widths:
        spec = dataclasses.replace(base_spec, street_width_m=float(width))
        scene = load_synthetic_l(spec)
        scene.frequency = fc
        a = spec.half_width
        for y_ris in (a + 1.0, a + 3.0):
            ris = np.array([a - 0.1, y_ris, z_ris])
            roi = roi_points(y_ris, a, d_min, d_max, h_roi, args.spacing)
            y_bs = -(a - 2.0)
            found = False
            for x_bs in np.arange(-(a + 2.0), -80.0, -2.0):
                bs = np.array([x_bs, y_bs, z_bs])
                if not bool(los_mask(scene, bs, ris[None, :])[0]):
                    continue
                frac = float(los_mask(scene, bs, roi).mean())
                d = float(np.linalg.norm(bs - ris))
                if frac == 0.0:
                    print(f"{width:6.0f} {y_ris:6.1f} {x_bs:7.1f} {y_bs:6.1f} "
                          f"{d:10.1f} {len(roi):6d} {frac:11.3f}  YA")
                    if best is None or d < best["d"]:
                        best = {"d": d, "bs": bs, "ris": ris, "y_ris": y_ris,
                                "width": float(width), "spec": spec, "n_roi": len(roi)}
                    found = True
                    break
            if not found:
                print(f"{width:6.0f} {y_ris:6.1f} {'-':>7s} {y_bs:6.1f} "
                      f"{'-':>10s} {len(roi):6d} {'-':>11s}  tidak ada")

    if best is None:
        print()
        print("TIDAK ADA konfigurasi layak pada rentang pencarian.")
        return 1

    bs, ris, spec = best["bs"], best["ris"], best["spec"]
    a = spec.half_width
    y_lo, y_hi = roi_bounds(best["y_ris"], d_min, d_max)
    centre = np.array([0.0, (y_lo + y_hi) / 2.0, h_roi])
    u1 = (bs - ris) / np.linalg.norm(bs - ris)
    u2 = (centre - ris) / np.linalg.norm(centre - ris)
    nrm = (u1 + u2) / np.linalg.norm(u1 + u2)
    ang = np.degrees(np.arccos(np.clip([u1 @ nrm, u2 @ nrm], -1.0, 1.0)))
    xr = a - 1.0
    lane = a / 2.0

    print()
    print(f"TERPILIH: lebar jalan {best['width']:.0f} m, "
          f"d(BS-RIS) = {best['d']:.1f} m, {best['n_roi']} titik ROI")
    print(f"  sudut dari normal RIS: BS {ang[0]:.1f} deg, pusat ROI {ang[1]:.1f} deg")
    print(f"  ROI: x in [{-xr:.1f}, {xr:.1f}], y in [{y_lo:.1f}, {y_hi:.1f}]")
    print()
    print("--- tempel ke configs/base.yaml (scene:) ---")
    print(f"    street_width_m: {best['width']:.1f}")
    print(f"  bs_position: [{bs[0]:.1f}, {bs[1]:.1f}, {bs[2]:.1f}]")
    print(f"  ris_position: [{ris[0]:.1f}, {ris[1]:.1f}, {ris[2]:.1f}]")
    print(f"  ris_normal: [{nrm[0]:.3f}, {nrm[1]:.3f}, {nrm[2]:.3f}]")
    print(f"  roi:")
    print(f"    polygon: [[{-xr:.1f}, {y_lo:.1f}], [{xr:.1f}, {y_lo:.1f}], "
          f"[{xr:.1f}, {y_hi:.1f}], [{-xr:.1f}, {y_hi:.1f}]]")
    print(f"  target_lanes: [[[{-lane:.1f}, {y_lo:.1f}], [{-lane:.1f}, {y_hi:.1f}]], "
          f"[[{lane:.1f}, {y_lo:.1f}], [{lane:.1f}, {y_hi:.1f}]]]")
    print(f"  sidewalks: [[[{-xr:.1f}, {y_lo:.1f}], [{-xr + 2:.1f}, {y_lo:.1f}], "
          f"[{-xr + 2:.1f}, {y_hi:.1f}], [{-xr:.1f}, {y_hi:.1f}]], "
          f"[[{xr - 2:.1f}, {y_lo:.1f}], [{xr:.1f}, {y_lo:.1f}], "
          f"[{xr:.1f}, {y_hi:.1f}], [{xr - 2:.1f}, {y_hi:.1f}]]]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
