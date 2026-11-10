"""E1 — kelayakan link budget dan peta cakupan, plus pemeriksaan Gate 1.

docs/TASKS.md Fase 1, docs/EXPERIMENT_DESIGN.md §7 (E1).

    python scripts/run_e1_coverage.py --config configs/base.yaml

Gate 1 (docs/TASKS.md):
  1. BS->RIS harus LoS.
  2. BS->ROI harus NLoS di 100% titik grid ROI.
  3. Dengan M = 144 dan P_max = 30 dBm, SNR lewat RIS > 0 dB di >= 80% titik ROI.

Keluar dengan kode 0 bila Gate 1 lolos, 1 bila tidak.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from risisac.channels.patterns import register_cosine_pattern          # noqa: E402
from risisac.channels.rt_extract import (RayTracingSettings,           # noqa: E402
                                         narrowband_coefficients)
from risisac.config import config_hash, load_config, noise_power_watt  # noqa: E402
from risisac.eval.plots import plot_f1_layout, plot_f2_coverage        # noqa: E402
from risisac.scene.placement import Placement                          # noqa: E402
from risisac.scene.synthetic_l import SyntheticLSpec, load_synthetic_l, write_xml  # noqa: E402
from risisac.scene.visibility import los_mask, verify_against_path_solver  # noqa: E402


def dbm_to_watt(dbm: float) -> float:
    return 10.0 ** ((float(dbm) - 30.0) / 10.0)


def m_to_rows_cols(m: int) -> tuple[int, int]:
    """M harus persegi sempurna agar panel RIS tetap bujur sangkar."""
    r = int(round(np.sqrt(m)))
    if r * r != m:
        raise ValueError(f"experiments.e1.m_values: {m} bukan kuadrat sempurna.")
    return r, r


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", default="base")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", default=None, help="direktori hasil (default results/e1/<hash>)")
    args = ap.parse_args()

    np.random.seed(args.seed)
    cfg = load_config(args.config)
    chash = config_hash(cfg)
    repo = Path(__file__).resolve().parents[1]
    out_dir = Path(args.out) if args.out else repo / "results" / "e1" / chash
    out_dir.mkdir(parents=True, exist_ok=True)

    e1 = cfg["experiments"]["e1"]
    radio, ris_cfg = cfg["radio"], cfg["radio"]["ris"]
    fc = float(radio["carrier_frequency_hz"])
    sigma2 = noise_power_watt(cfg)

    print(f"config hash : {chash}")
    print(f"hasil       : {out_dir}")
    print(f"f_c         : {fc / 1e9:.2f} GHz | sigma_n^2 = {10 * np.log10(sigma2) + 30:.2f} dBm")

    # ---------------------------------------------------------------- scene
    spec = SyntheticLSpec.from_config(cfg)
    placement = Placement.from_config(cfg)
    register_cosine_pattern()

    import sionna.rt as rt
    scene = load_synthetic_l(spec)
    scene.frequency = fc
    write_xml(spec, out_dir / "synthetic_l.xml")

    grid = placement.roi_grid()
    print(f"grid ROI    : {len(grid)} titik @ {placement.roi_grid_spacing} m")

    # ----------------------------------------------------- Gate 1: LoS (1,2)
    t0 = time.time()
    los_bs_ris = bool(los_mask(scene, placement.bs_tx, placement.ris_position[None, :])[0])
    los_bs_roi = los_mask(scene, placement.bs_tx, grid)
    los_ris_roi = los_mask(scene, placement.ris_position, grid)
    print(f"LoS checks  : {time.time() - t0:.2f}s")
    print(f"  BS->RIS LoS          : {los_bs_ris}")
    print(f"  BS->ROI LoS fraction : {los_bs_roi.mean():.4f}  (harus 0)")
    print(f"  RIS->ROI LoS fraction: {los_ris_roi.mean():.4f}")

    # Uji silang oracle LoS terhadap PathSolver depth-0 pada subhimpunan titik.
    n_verify = min(int(e1["los_verify_samples"]), len(grid))
    idx = np.random.default_rng(args.seed).choice(len(grid), n_verify, replace=False)
    verify_scene = load_synthetic_l(spec)
    verify_scene.frequency = fc
    verify_scene.tx_array = rt.PlanarArray(num_rows=1, num_cols=1, pattern="iso",
                                           polarization="V")
    verify_scene.rx_array = rt.PlanarArray(num_rows=1, num_cols=1, pattern="iso",
                                           polarization="V")
    vr = verify_against_path_solver(verify_scene, placement.bs_tx, grid[idx])
    print(f"  uji silang ray_test vs PathSolver(depth=0): "
          f"{vr['num_mismatch']}/{vr['num_points']} ketidakcocokan")

    # ------------------------------------------------------------- channels
    settings = RayTracingSettings.from_config(cfg)
    nt = int(radio["bs"]["num_tx"])
    bs_array = rt.PlanarArray(num_rows=1, num_cols=nt,
                              vertical_spacing=0.5, horizontal_spacing=0.5,
                              pattern=str(radio["bs"]["pattern"]), polarization="V")
    rx_single = rt.PlanarArray(num_rows=1, num_cols=1,
                               pattern=str(radio["user"]["pattern"]), polarization="V")

    # (a) Kanal langsung BS -> grid.
    t0 = time.time()
    hd = narrowband_coefficients(scene, bs_array, rx_single, placement.bs_tx, grid,
                                 settings, tx_look_at=placement.ris_position)[:, 0, :]
    print(f"BS->grid    : {time.time() - t0:.1f}s, hd {hd.shape}")
    p_direct_unit = np.sum(np.abs(hd) ** 2, axis=1)       # gain MRT, per Watt pancar

    # (b) Lewat RIS, untuk tiap M.
    spacing = float(ris_cfg["spacing_wavelengths"])
    pattern = str(ris_cfg["element_pattern"])
    ris_look_at = placement.ris_look_at()
    p_ris_unit: dict[int, np.ndarray] = {}

    for m in [int(v) for v in e1["m_values"]]:
        rows, cols = m_to_rows_cols(m)
        s_m = settings.for_array_size(m)
        ris_array = rt.PlanarArray(num_rows=rows, num_cols=cols,
                                   vertical_spacing=spacing, horizontal_spacing=spacing,
                                   pattern=pattern, polarization="V")
        t0 = time.time()
        # G: BS-tx -> RIS, bentuk (M, Nt) sesuai konvensi CLAUDE.md
        g_mat = narrowband_coefficients(scene, bs_array, ris_array, placement.bs_tx,
                                        placement.ris_position[None, :], s_m,
                                        tx_look_at=placement.ris_position,
                                        rx_look_at=ris_look_at)[0]
        # g: RIS -> tiap titik grid, bentuk (N, M)
        g_grid = narrowband_coefficients(scene, ris_array, rx_single,
                                         placement.ris_position, grid, s_m,
                                         tx_look_at=ris_look_at)[:, 0, :]

        # Precoder BS: vektor singular kanan utama G, ternormalisasi (desain §6.2 B2)
        _, _, vh = np.linalg.svd(g_mat, full_matrices=False)
        a_bar = np.conj(vh[0])
        a_bar = a_bar / np.linalg.norm(a_bar)
        u = g_mat @ a_bar                                  # (M,)

        # Gain koheren terbaik: fasa RIS menyejajarkan semua suku.
        amp = np.abs(g_grid) @ np.abs(u)                   # (N,)
        p_ris_unit[m] = amp ** 2
        print(f"RIS M={m:3d}  : {time.time() - t0:.1f}s, G {g_mat.shape}, g {g_grid.shape}")

    # ----------------------------------------------------------------- SNR
    p_values = [float(v) for v in e1["p_max_dbm_values"]]
    thr = float(e1["snr_threshold_db"])
    target = float(e1["coverage_target"])

    snr_direct = {p: 10 * np.log10(dbm_to_watt(p) * p_direct_unit / sigma2 + 1e-300)
                  for p in p_values}
    snr_ris = {(m, p): 10 * np.log10(dbm_to_watt(p) * p_ris_unit[m] / sigma2 + 1e-300)
               for m in p_ris_unit for p in p_values}

    print("\nCakupan (fraksi titik ROI dengan SNR >= "
          f"{thr:.0f} dB):")
    header = "  M      " + "".join(f"{p:>10.0f} dBm" for p in p_values)
    print(header)
    print("  langsung" + "".join(f"{(snr_direct[p] >= thr).mean():>14.3f}" for p in p_values))
    for m in sorted(p_ris_unit):
        print(f"  {m:<7d}" + "".join(f"{(snr_ris[(m, p)] >= thr).mean():>14.3f}"
                                     for p in p_values))

    # ------------------------------------------------------------- Gate 1
    m_default = int(ris_cfg["num_rows"]) * int(ris_cfg["num_cols"])
    p_default = float(radio["p_max_dbm"])
    if (m_default, p_default) in snr_ris:
        cov_default = float((snr_ris[(m_default, p_default)] >= thr).mean())
    else:
        cov_default = float("nan")

    checks = {
        "bs_ris_los": {"pass": los_bs_ris, "value": los_bs_ris},
        "bs_roi_nlos": {"pass": float(los_bs_roi.mean()) == 0.0,
                        "value": float(los_bs_roi.mean())},
        "ris_coverage": {"pass": bool(cov_default >= target), "value": cov_default,
                         "target": target, "M": m_default, "p_max_dbm": p_default},
        "los_oracle_agrees": {"pass": vr["num_mismatch"] == 0,
                              "value": vr["num_mismatch"], "of": vr["num_points"]},
    }
    passed = all(c["pass"] for c in checks.values())

    print("\nGate 1")
    print("------")
    for name, c in checks.items():
        print(f"  [{'PASS' if c['pass'] else 'FAIL'}] {name}: {c['value']}")
    print(f"\nGATE 1: {'LOLOS' if passed else 'GAGAL'}")

    # ----------------------------------------------------------------- simpan
    np.savez_compressed(
        out_dir / "e1_coverage.npz",
        grid=grid,
        los_bs_roi=los_bs_roi,
        los_ris_roi=los_ris_roi,
        p_direct_unit=p_direct_unit,
        m_values=np.array(sorted(p_ris_unit)),
        p_max_dbm_values=np.array(p_values),
        **{f"p_ris_unit_M{m}": v for m, v in p_ris_unit.items()},
    )
    (out_dir / "gate1.json").write_text(json.dumps(
        {"config_hash": chash, "passed": passed, "checks": checks,
         "num_roi_points": int(len(grid)),
         "ris_roi_los_fraction": float(los_ris_roi.mean())},
        indent=2, default=str), encoding="utf-8")
    (out_dir / "config_used.json").write_text(json.dumps(cfg, indent=2, default=str),
                                              encoding="utf-8")

    # ----------------------------------------------------------------- gambar
    plot_f1_layout(spec, placement, out_dir / "F1_layout.png",
                   los_ris_fraction=float(los_ris_roi.mean()))
    if m_default in p_ris_unit:
        plot_f2_coverage(grid[:, :2], snr_direct[p_default], snr_ris[(m_default, p_default)],
                         out_dir / "F2_coverage.png", m_elements=m_default,
                         p_max_dbm=p_default, threshold_db=thr)
    print(f"\nGambar dan hasil tersimpan di {out_dir}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
