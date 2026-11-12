"""E1 - peta cakupan komunikasi dan SNR radar ideal, plus Gate 1.

docs/TASKS.md Fase 1, docs/EXPERIMENT_DESIGN.md §7 (E1).

    python scripts/run_e1_coverage.py --config base

Gate 1 (docs/TASKS.md Fase 1):
  1. BS->RIS harus LoS.
  2. BS->ROI harus NLoS di 100% titik grid ROI.
  3. Pada P_max = 30 dBm: SNR komunikasi lewat RIS > 10 dB di >= 90% ROI.
  4. Pada P_max = 30 dBm: SNR radar ideal >= Gamma + 3 dB di >= 80% ROI.
  5. Penguatan RIS (MRT dengan RIS lawan MRT tanpa RIS) > 6 dB di >= 80% ROI.
     Kriteria (5) ditambahkan 2026-11-11: tanpa itu gate bisa lolos sementara
     jalur langsung mendominasi ROI, sehingga premis "RIS yang melayani ROI"
     gagal diam-diam. Ambangnya dinaikkan dari 0 dB / 90% ke 6 dB / 80% pada
     hari yang sama, karena 0 dB meloloskan geometri yang hanya menambah
     +1,4 dB. Ambang ada di configs/*.yaml (gate1:).

Keluar 0 bila Gate 1 lolos, 1 bila tidak.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from risisac.channels.patterns import register_cosine_pattern            # noqa: E402
from risisac.channels.rt_extract import (RayTracingSettings,             # noqa: E402
                                         narrowband_coefficients,
                                         release_gpu_memory)
from risisac.config import config_hash, load_config, noise_power_watt    # noqa: E402
from risisac.eval.plots import (plot_f1_layout,                         # noqa: E402
                                plot_f2_coverage)
from risisac.scene.placement import Placement                            # noqa: E402
from risisac.scene.synthetic_l import (SyntheticLSpec,                   # noqa: E402
                                       load_scene_from_config, write_xml)
from risisac.scene.visibility import (los_mask,                          # noqa: E402
                                      verify_against_path_solver)
from risisac.system.signal_model import (cascaded_coefficient,           # noqa: E402
                                         dbm_to_watt, eta_factor,
                                         focus_phases, ideal_scnr,
                                         snr_from_gain, to_db,
                                         wavelength_of)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", default="base")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    np.random.seed(args.seed)
    cfg = load_config(args.config)
    chash = config_hash(cfg)
    repo = Path(__file__).resolve().parents[1]
    out_dir = Path(args.out) if args.out else repo / "results" / "e1" / chash
    out_dir.mkdir(parents=True, exist_ok=True)

    radio, ris_cfg, sens = cfg["radio"], cfg["radio"]["ris"], cfg["sensing"]
    fc = float(radio["carrier_frequency_hz"])
    wl = wavelength_of(fc)
    sigma2 = noise_power_watt(cfg)
    eta = eta_factor(float(radio["target"]["rcs_m2"]), wl)
    gamma_db = float(sens["scnr_threshold_db"])
    n_int = int(sens["integration_samples"])
    m_elements = int(ris_cfg["num_rows"]) * int(ris_cfg["num_cols"])
    gate = cfg["gate1"]
    comm_thr = float(gate["comm_snr_threshold_db"])
    comm_target = float(gate["comm_coverage_target"])
    radar_thr = gamma_db + float(gate["radar_margin_db"])
    radar_target = float(gate["radar_coverage_target"])
    gain_thr = float(gate["ris_gain_threshold_db"])
    gain_target = float(gate["ris_gain_coverage_target"])
    p_values = [20.0, 30.0, 40.0]
    p_default = float(radio["p_max_dbm"])

    print(f"config hash : {chash}")
    print(f"hasil       : {out_dir}")
    print(f"f_c {fc / 1e9:.2f} GHz | lambda {wl * 100:.2f} cm | "
          f"sigma_n^2 {to_db(sigma2) + 30:.1f} dBm")
    print(f"eta {to_db(eta):.1f} dB | L {n_int} | Gamma {gamma_db:.0f} dB | "
          f"M {m_elements}")

    # ------------------------------------------------------------------ scene
    spec = SyntheticLSpec.from_config(cfg)
    pl = Placement.from_config(cfg)
    register_cosine_pattern()
    import sionna.rt as rt

    scene = load_scene_from_config(cfg)
    write_xml(spec, out_dir / "synthetic_l.xml")
    grid = pl.roi_grid()
    d_bs_ris = float(np.linalg.norm(pl.bs_tx - pl.ris_position))
    print(f"grid ROI    : {len(grid)} titik @ {pl.roi_grid_spacing} m | "
          f"d(BS-RIS) {d_bs_ris:.1f} m")

    # ------------------------------------------------------- Gate 1 (1) & (2)
    t0 = time.time()
    los_bs_ris = bool(los_mask(scene, pl.bs_tx, pl.ris_position[None, :])[0])
    los_bs_roi = los_mask(scene, pl.bs_tx, grid)
    los_ris_roi = los_mask(scene, pl.ris_position, grid)
    print(f"LoS         : {time.time() - t0:.2f}s | BS->RIS {los_bs_ris} | "
          f"BS->ROI {los_bs_roi.mean():.4f} | RIS->ROI {los_ris_roi.mean():.4f}")

    n_ver = min(64, len(grid))
    idx = np.random.default_rng(args.seed).choice(len(grid), n_ver, replace=False)
    vscene = load_scene_from_config(cfg)
    vscene.tx_array = rt.PlanarArray(num_rows=1, num_cols=1, pattern="iso",
                                     polarization="V")
    vscene.rx_array = rt.PlanarArray(num_rows=1, num_cols=1, pattern="iso",
                                     polarization="V")
    vr = verify_against_path_solver(vscene, pl.bs_tx, grid[idx])
    print(f"  ray_test vs PathSolver(depth=0): "
          f"{vr['num_mismatch']}/{vr['num_points']} beda")

    # --------------------------------------------------------------- kanal RT
    settings = RayTracingSettings.from_config(cfg)
    nt, nr = int(radio["bs"]["num_tx"]), int(radio["bs"]["num_rx"])
    bs_tx_arr = rt.PlanarArray(num_rows=1, num_cols=nt, vertical_spacing=0.5,
                               horizontal_spacing=0.5,
                               pattern=str(radio["bs"]["pattern"]),
                               polarization="V")
    bs_rx_arr = rt.PlanarArray(num_rows=1, num_cols=nr, vertical_spacing=0.5,
                               horizontal_spacing=0.5,
                               pattern=str(radio["bs"]["pattern"]),
                               polarization="V")
    rx1 = rt.PlanarArray(num_rows=1, num_cols=1,
                         pattern=str(radio["user"]["pattern"]), polarization="V")
    ris_arr = rt.PlanarArray(num_rows=int(ris_cfg["num_rows"]),
                             num_cols=int(ris_cfg["num_cols"]),
                             vertical_spacing=float(ris_cfg["spacing_wavelengths"]),
                             horizontal_spacing=float(ris_cfg["spacing_wavelengths"]),
                             pattern=str(ris_cfg["element_pattern"]),
                             polarization="V")
    look = pl.ris_look_at()

    def run(label, tx_arr, rx_arr, tx_pos, rx_pos, **kw):
        release_gpu_memory()
        t = time.time()
        a = narrowband_coefficients(scene, tx_arr, rx_arr, tx_pos, rx_pos,
                                    settings, **kw)
        print(f"  {label:<22s} {a.shape}  {time.time() - t:.1f}s")
        return a

    print("kanal:")
    hd = run("h_d  BS-tx -> grid", bs_tx_arr, rx1, pl.bs_tx, grid,
             tx_look_at=pl.ris_position)[:, 0, :]                      # (N, Nt)
    hd_rx = run("h_d  BS-rx -> grid", bs_rx_arr, rx1, pl.bs_rx, grid,
                tx_look_at=pl.ris_position)[:, 0, :]                   # (N, Nr)
    G = run("G    BS-tx -> RIS", bs_tx_arr, ris_arr, pl.bs_tx,
            pl.ris_position[None, :], tx_look_at=pl.ris_position,
            rx_look_at=look)[0]                                        # (M, Nt)
    H = run("H    RIS -> BS-rx", ris_arr, bs_rx_arr, pl.ris_position,
            pl.bs_rx[None, :], tx_look_at=look,
            rx_look_at=pl.ris_position)[0]                             # (Nr, M)
    g = run("g    RIS -> grid", ris_arr, rx1, pl.ris_position, grid,
            tx_look_at=look)[:, 0, :]                                  # (N, M)

    # Precoder BS: vektor singular kanan utama G (desain §6.2 B2).
    _, _, vh = np.linalg.svd(G, full_matrices=False)
    a_bar = np.conj(vh[0])
    a_bar = a_bar / np.linalg.norm(a_bar)
    u = G @ a_bar                                                       # (M,)

    # Fasa fokus terbaik per titik, lalu kanal efektif maju dan balik.
    phi = focus_phases(u[None, :], g)                                   # (N, M)
    c_casc = cascaded_coefficient(u[None, :], g, phi)                   # (N,)
    c_dir = hd @ a_bar                                                  # (N,)
    c_eff = c_dir + c_casc                                              # (N,)
    b = hd_rx + (np.exp(1j * phi) * g) @ H.T                            # (N, Nr)

    # Penguatan kaskade RIS atas jalur langsung, dengan precoder yang sama.
    ris_gain_db = to_db(np.abs(c_casc) ** 2) - to_db(np.abs(c_dir) ** 2)

    # Dua besaran berbeda, jangan tertukar:
    #   gain_direct_mrt : kasus TERBAIK sistem tanpa RIS (precoder MRT ke h_d).
    #   gain_direct     : jalur langsung dengan precoder a_bar yang SAMA dengan
    #                     jalur RIS -- satu-satunya pembanding yang apel-ke-apel
    #                     untuk pertanyaan "berapa yang ditambahkan RIS".
    gain_direct_mrt = np.sum(np.abs(hd) ** 2, axis=1)
    gain_direct = np.abs(c_dir) ** 2
    gain_ris = np.abs(c_eff) ** 2
    # Kanal efektif (E2): h_e = h_d + G^T (e^{j phi} . g). Dengan MRT, ini
    # pembanding yang adil terhadap gain_direct_mrt untuk pertanyaan "apakah
    # sistem ber-RIS mengungguli sistem tanpa RIS yang beamforming optimal".
    h_eff = hd + (np.exp(1j * phi) * g) @ G
    gain_ris_mrt = np.sum(np.abs(h_eff) ** 2, axis=1)

    # -------------------------------------------------------------------- SNR
    snr_direct = {p: to_db(snr_from_gain(gain_direct, dbm_to_watt(p), sigma2))
                  for p in p_values}
    snr_direct_mrt = {p: to_db(snr_from_gain(gain_direct_mrt, dbm_to_watt(p),
                                             sigma2)) for p in p_values}
    snr_ris = {p: to_db(snr_from_gain(gain_ris, dbm_to_watt(p), sigma2))
               for p in p_values}
    scnr = {p: to_db(ideal_scnr(c_eff, b, dbm_to_watt(p), eta, sigma2, n_int))
            for p in p_values}

    # SCNR ideal "sistem lawan sistem" (Fase 8, disetujui 2026-11-12). Yang di
    # atas memakai precoder a_bar untuk KEDUA sisi, dan itu pembanding yang
    # sama cacatnya dengan "precoder sama" di sisi komunikasi: a_bar
    # dioptimalkan untuk mencapai RIS. Di bawah ini tiap sistem memakai beam
    # TERBAIKNYA sendiri, yaitu MRT pada kanal maju yang dimilikinya:
    #   lewat RIS    : w ~ conj(h_e)/||h_e||  ->  |c^T w| = ||h_e||
    #   langsung saja: w ~ conj(h_d)/||h_d||  ->  |c^T w| = ||h_d||
    # Kanal baliknya ikut berbeda: dengan RIS b = h^(r)_d + H Theta g, tanpa
    # RIS b = h^(r)_d saja. Ini yang dipakai F2 panel (b).
    #
    # Gate 1 SENGAJA tetap memakai `scnr` berbasis a_bar: ambangnya ditetapkan
    # dan lolos di Fase 1 pada besaran itu, dan menukar besaran di bawah
    # kriteria yang sama akan membuat riwayat gate tidak bisa dibaca.
    c_ris_mrt = np.linalg.norm(h_eff, axis=1)                       # (N,)
    c_dir_mrt = np.linalg.norm(hd, axis=1)                          # (N,)
    scnr_ris_mrt = {p: to_db(ideal_scnr(c_ris_mrt, b, dbm_to_watt(p), eta,
                                        sigma2, n_int)) for p in p_values}
    scnr_direct_mrt = {p: to_db(ideal_scnr(c_dir_mrt, hd_rx, dbm_to_watt(p),
                                           eta, sigma2, n_int))
                       for p in p_values}

    print("\nFraksi titik ROI di atas ambang:")
    print(f"  {'P_max':>6s} {'komunikasi >10 dB':>19s} {'radar >=G+3':>13s} "
          f"{'median SNR_c':>13s} {'median SCNR':>12s}")
    for p in p_values:
        print(f"  {p:5.0f}  {float((snr_ris[p] > comm_thr).mean()):18.3f} "
              f"{float((scnr[p] >= radar_thr).mean()):13.3f} "
              f"{float(np.median(snr_ris[p])):12.1f} "
              f"{float(np.median(scnr[p])):12.1f}")
    print(f"  (BS langsung @30 dBm, precoder sama: median "
          f"{float(np.median(snr_direct[30.0])):.1f} dB; "
          f"MRT tanpa RIS: {float(np.median(snr_direct_mrt[30.0])):.1f} dB)")
    mrt_gain = to_db(gain_ris_mrt) - to_db(gain_direct_mrt)
    print(f"  MRT dengan RIS vs MRT tanpa RIS: median "
          f"{float(np.median(mrt_gain)):+.1f} dB, "
          f"RIS menang di {float((mrt_gain > 0).mean()):.3f} ROI")
    print("\nSCNR ideal sistem-lawan-sistem (MRT masing-masing, rho = 1):")
    print(f"  {'P_max':>6s} {'median lewat RIS':>17s} {'median langsung':>16s} "
          f"{'>=Gamma RIS':>12s} {'>=Gamma langsung':>17s}")
    for p in p_values:
        print(f"  {p:5.0f}  {float(np.median(scnr_ris_mrt[p])):16.1f} "
              f"{float(np.median(scnr_direct_mrt[p])):16.1f} "
              f"{float((scnr_ris_mrt[p] >= gamma_db).mean()):12.3f} "
              f"{float((scnr_direct_mrt[p] >= gamma_db).mean()):17.3f}")

    # ----------------------------------------------------------------- Gate 1
    cov_comm = float((snr_ris[p_default] > comm_thr).mean())
    cov_radar = float((scnr[p_default] >= radar_thr).mean())
    # Kriteria memakai MRT lawan MRT, BUKAN perbandingan pada precoder a_bar.
    # a_bar dioptimalkan untuk mencapai RIS dan melumpuhkan jalur langsung,
    # sehingga perbandingan pada precoder itu melebih-lebihkan peran RIS
    # (+8,8 dB) dibanding kenyataan tingkat sistem (+1,4 dB). Lihat LOG.
    ris_gain_db = to_db(gain_ris_mrt) - to_db(gain_direct_mrt)
    cov_gain = float((ris_gain_db > gain_thr).mean())
    print("")
    print(f"Penguatan RIS (MRT dengan vs tanpa RIS): median "
          f"{float(np.median(ris_gain_db)):+.1f} dB, p10 "
          f"{float(np.percentile(ris_gain_db, 10)):+.1f} dB, "
          f"> {gain_thr:.0f} dB di {cov_gain:.3f} ROI")
    checks = {
        "bs_ris_los": {"pass": los_bs_ris, "value": los_bs_ris},
        "bs_roi_nlos": {"pass": float(los_bs_roi.mean()) == 0.0,
                        "value": float(los_bs_roi.mean())},
        "comm_coverage": {"pass": cov_comm >= comm_target, "value": cov_comm,
                          "target": comm_target, "threshold_db": comm_thr,
                          "p_max_dbm": p_default},
        "radar_coverage": {"pass": cov_radar >= radar_target, "value": cov_radar,
                           "target": radar_target, "threshold_db": radar_thr,
                           "p_max_dbm": p_default},
        "ris_beats_direct": {"pass": cov_gain >= gain_target, "value": cov_gain,
                             "target": gain_target, "threshold_db": gain_thr,
                             "median_gain_db": float(np.median(ris_gain_db))},
        "los_oracle_agrees": {"pass": vr["num_mismatch"] == 0,
                              "value": vr["num_mismatch"],
                              "of": vr["num_points"]},
    }
    passed = all(c["pass"] for c in checks.values())
    print("\nGate 1\n------")
    for name, c in checks.items():
        print(f"  [{'PASS' if c['pass'] else 'FAIL'}] {name}: {c['value']}")
    print(f"\nGATE 1: {'LOLOS' if passed else 'GAGAL'}")

    # ----------------------------------------------------------------- simpan
    np.savez_compressed(
        out_dir / "e1_coverage.npz", grid=grid, los_bs_roi=los_bs_roi,
        los_ris_roi=los_ris_roi, gain_direct=gain_direct, gain_direct_mrt=gain_direct_mrt,
        gain_ris=gain_ris, gain_ris_mrt=gain_ris_mrt,
        ris_gain_db=ris_gain_db,
        scnr_db=np.stack([scnr[p] for p in p_values]),
        scnr_ris_mrt_db=np.stack([scnr_ris_mrt[p] for p in p_values]),
        scnr_direct_mrt_db=np.stack([scnr_direct_mrt[p] for p in p_values]),
        p_max_dbm_values=np.array(p_values), G=G, H=H, a_bar=a_bar,
    )
    (out_dir / "gate1.json").write_text(json.dumps(
        {"config_hash": chash, "passed": passed, "checks": checks,
         "num_roi_points": int(len(grid)), "d_bs_ris_m": d_bs_ris,
         "eta_db": float(to_db(eta)), "m_elements": m_elements,
         "ris_roi_los_fraction": float(los_ris_roi.mean())},
        indent=2, default=str), encoding="utf-8")
    (out_dir / "config_used.json").write_text(
        json.dumps(cfg, indent=2, default=str), encoding="utf-8")

    plot_f1_layout(spec, pl, out_dir / "F1_layout.png",
                   los_ris_fraction=float(los_ris_roi.mean()))
    plot_f2_coverage(grid[:, :2], ris_gain_db, scnr_ris_mrt[p_default],
                     scnr_direct_mrt[p_default], out_dir / "F2_coverage.png",
                     m_elements=m_elements, p_max_dbm=p_default,
                     gain_threshold_db=gain_thr, gamma_db=gamma_db)
    print(f"\nGambar dan hasil tersimpan di {out_dir}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
