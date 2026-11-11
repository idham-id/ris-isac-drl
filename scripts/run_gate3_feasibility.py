"""Gate 3 - uji kelayakan baseline (docs/TASKS.md Fase 3).

    python scripts/run_gate3_feasibility.py --config base --snapshots 200

Mengambil snapshot dari split **val**, lalu:

1. mengukur **dampak clutter** terhadap SCNR -- E1 memakai bentuk ideal tanpa
   clutter, jadi angkanya batas atas, bukan ramalan (docs/LOG.md 2026-11-11 (g));
2. menyapu grid ``rho`` untuk **B1** dan grid ``(omega, rho)`` untuk **B2**;
3. menjalankan **B3 (Oracle-GD)**.

**Gate 3:** B3 memenuhi SCNR >= Gamma pada >= 90% snapshot val dan jelas
mengungguli B1.

Keluar 0 bila Gate 3 lolos, 1 bila tidak.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from risisac.baselines import geometric, oracle_gd, random_policy   # noqa: E402
from risisac.baselines.common import (Snapshot, SystemConstants,    # noqa: E402
                                      evaluate_decision,
                                      uniform_weights)
from risisac.channels.database import (completed_trajectories,      # noqa: E402
                                       database_path, read_static,
                                       read_trajectory)
from risisac.channels.geometry import (ris_element_positions,       # noqa: E402
                                       spherical_steering)
from risisac.config import (channel_config_hash,  # noqa: E402
                            config_hash, load_config)                 # noqa: E402
from risisac.scene.placement import Placement                       # noqa: E402
from risisac.system import signal_model as sm                       # noqa: E402


def collect_snapshots(cfg, path, split, count, rng):
    """Ambil ``count`` langkah acak dari split, hanya yang target-nya di ROI."""
    G, H, Hc = read_static(path)[:3]
    traj_ids = sorted(completed_trajectories(path, split))
    if not traj_ids:
        raise SystemExit(f"split '{split}' belum diprakomputasi.")

    pool = []
    for tid in traj_ids:
        tr = read_trajectory(path, split, tid)
        for t in np.flatnonzero(tr.target_in_roi[0]):
            pool.append((tid, int(t)))
    if len(pool) < count:
        raise SystemExit(f"hanya {len(pool)} langkah tersedia, diminta {count}.")
    chosen = [pool[i] for i in rng.choice(len(pool), count, replace=False)]

    cache: dict[int, object] = {}
    fields = {k: [] for k in ("hd_user", "g_user", "hd_tgt_tx", "hd_tgt_rx",
                              "g_tgt", "user_pos", "target_pos")}
    for tid, t in chosen:
        if tid not in cache:
            cache[tid] = read_trajectory(path, split, tid)
        tr = cache[tid]
        fields["hd_user"].append(tr.user_hd[:, t, :])
        fields["g_user"].append(tr.user_g[:, t, :])
        fields["hd_tgt_tx"].append(tr.target_hd_tx[:, t, :])
        fields["hd_tgt_rx"].append(tr.target_hd_rx[:, t, :])
        fields["g_tgt"].append(tr.target_g[:, t, :])
        fields["user_pos"].append(tr.user_pos[:, t, :])
        fields["target_pos"].append(tr.target_pos[:, t, :])
    stacked = {k: np.stack(v).astype(np.complex128 if k.startswith(("hd", "g"))
                                     else np.float64) for k, v in fields.items()}

    p_max = np.full(count, sm.dbm_to_watt(float(cfg["radio"]["p_max_dbm"])))
    snap = Snapshot(G=G.astype(np.complex128), H=H.astype(np.complex128),
                    Hc=Hc.astype(np.complex128),
                    hd_user=stacked["hd_user"], g_user=stacked["g_user"],
                    hd_tgt_tx=stacked["hd_tgt_tx"],
                    hd_tgt_rx=stacked["hd_tgt_rx"], g_tgt=stacked["g_tgt"],
                    p_max_watt=p_max)
    return snap, stacked["user_pos"], stacked["target_pos"]


def los_channel_estimate(positions, ris_xyz, wavelength):
    """Model LoS gelombang sferis ke ``positions`` (..., 3) -> (..., M).

    Dipakai B2 dan beam sensing: §6.2 memberi baseline **estimasi** posisi,
    bukan kanal sebenarnya. Amplitudonya tidak perlu berskala sama dengan
    kanal ray tracing karena hanya fasanya yang dipakai (B2 mengambil -arg)
    dan beam sensing dinormalkan.
    """
    flat = np.asarray(positions, float).reshape(-1, 3)
    out = np.stack([spherical_steering(ris_xyz, p, wavelength,
                                       include_amplitude=True) for p in flat])
    return out.reshape(np.shape(positions)[:-1] + (len(ris_xyz),))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", default="base")
    ap.add_argument("--split", default="val")
    ap.add_argument("--snapshots", type=int, default=200)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--lambda-sweep", nargs="+", type=float,
                    default=[1.0, 3.0, 10.0, 30.0, 100.0],
                    help="bobot reward yang disapu untuk diagnosis B3")
    args = ap.parse_args()

    cfg = load_config(args.config)
    chash = config_hash(cfg)
    repo = Path(__file__).resolve().parents[1]
    db = database_path(cfg, channel_config_hash(cfg),
                       root=repo / cfg["paths"]["channel_db"])
    out_dir = repo / "results" / "gate3" / chash
    out_dir.mkdir(parents=True, exist_ok=True)

    rng = np.random.default_rng(args.seed)
    const = SystemConstants.from_config(cfg)
    pl = Placement.from_config(cfg)
    ris_cfg = cfg["radio"]["ris"]
    wavelength = sm.wavelength_of(float(cfg["radio"]["carrier_frequency_hz"]))
    ris_xyz = ris_element_positions(pl.ris_position, pl.ris_normal,
                                    int(ris_cfg["num_rows"]),
                                    int(ris_cfg["num_cols"]), wavelength,
                                    float(ris_cfg["spacing_wavelengths"]))

    print(f"config hash : {chash}")
    print(f"basis data  : {db}")
    snap, user_pos, target_pos = collect_snapshots(cfg, db, args.split,
                                                   args.snapshots, rng)
    print(f"snapshot    : {snap.batch} langkah dari split {args.split} | "
          f"M {snap.num_elements} | K {snap.num_users} | "
          f"P_max {cfg['radio']['p_max_dbm']:.0f} dBm | "
          f"Gamma {const.scnr_threshold_db:.0f} dB")

    # Estimasi posisi: galat Gaussian sesuai §5.2 (tracker penuh masuk Fase 4).
    obs = cfg["observation"]
    user_hat = user_pos + rng.normal(0.0, float(obs["user_pos_std_m"]),
                                     size=user_pos.shape)
    tgt_hat = target_pos + rng.normal(0.0, float(obs["target_pos_ref_std_m"]),
                                      size=target_pos.shape)
    g_hat_user = los_channel_estimate(user_hat, ris_xyz, wavelength)
    g_hat_tgt = los_channel_estimate(tgt_hat[:, 0, :], ris_xyz, wavelength)

    # ------------------------------------------------- 1) dampak clutter
    phi0 = rng.uniform(0, 2 * np.pi, (snap.batch, snap.num_elements))
    w0 = uniform_weights(snap.batch, snap.num_users)
    rho0 = np.full(snap.batch, 0.5)
    with_clutter = evaluate_decision(snap, const, phi0, rho0, w0, g_hat_tgt)
    no_clutter = evaluate_decision(
        snap, SystemConstants(**{**const.__dict__, "clutter_residual": 0.0}),
        phi0, rho0, w0, g_hat_tgt)
    loss = no_clutter["worst_scnr_db"] - with_clutter["worst_scnr_db"]
    clutter = {"median_loss_db": float(np.median(loss)),
               "p90_loss_db": float(np.percentile(loss, 90)),
               "max_loss_db": float(np.max(loss)),
               "scnr_with_db": float(np.median(with_clutter["worst_scnr_db"])),
               "scnr_without_db": float(np.median(no_clutter["worst_scnr_db"]))}
    print("\n1) Dampak clutter pada SCNR (fasa acak, rho = 0,5)")
    print(f"   tanpa clutter (xi = 0) : median {clutter['scnr_without_db']:7.1f} dB")
    print(f"   dengan clutter (xi={const.clutter_residual}) : "
          f"median {clutter['scnr_with_db']:7.1f} dB")
    print(f"   kerugian: median {clutter['median_loss_db']:.2f} dB, "
          f"p90 {clutter['p90_loss_db']:.2f} dB, maks {clutter['max_loss_db']:.2f} dB")

    # ------------------------------------------------------- 2) B1 dan B2
    rho_grid = [float(v) for v in cfg["baselines"]["rho_grid"]]
    weight_grid = [float(v) for v in cfg["baselines"]["geometric"]["weight_grid"]]

    t0 = time.time()
    b1 = random_policy.tune_sensing_fraction(snap, const, rho_grid,
                                             seed=args.seed, g_hat_tgt=g_hat_tgt)
    b2 = geometric.tune(snap, const, g_hat_user, g_hat_tgt, weight_grid, rho_grid)
    print(f"\n2) Sapuan grid val ({time.time() - t0:.1f}s)")
    print(f"   B1: rho terbaik {b1['best_rho']:.2f}")
    print(f"   {'rho':>5s} {'reward':>9s} {'min rate':>9s} {'SCNR':>8s} {'deteksi':>8s}")
    for row in b1["grid"]:
        print(f"   {row['rho']:5.2f} {row['reward']:9.3f} {row['min_rate']:9.3f} "
              f"{row['scnr_db']:8.1f} {row['detection_rate']:8.3f}")
    print(f"   B2: omega_target {b2['best_omega_target']:.2f}, "
          f"rho {b2['best_rho']:.2f}")
    best_rows = sorted(b2["grid"], key=lambda r: -r["reward"])[:5]
    print(f"   {'w_t':>5s} {'rho':>5s} {'reward':>9s} {'min rate':>9s} "
          f"{'SCNR':>8s} {'deteksi':>8s}")
    for row in best_rows:
        print(f"   {row['omega_target']:5.2f} {row['rho']:5.2f} "
              f"{row['reward']:9.3f} {row['min_rate']:9.3f} "
              f"{row['scnr_db']:8.1f} {row['detection_rate']:8.3f}")

    phi1, rho1, w1 = random_policy.decide(snap, np.random.default_rng(args.seed),
                                          b1["best_rho"])
    out1 = evaluate_decision(snap, const, phi1, rho1, w1, g_hat_tgt)
    omega = np.concatenate([
        np.full(snap.num_users,
                (1.0 - b2["best_omega_target"]) / snap.num_users),
        [b2["best_omega_target"]]])
    phi2, rho2, w2 = geometric.decide(snap, g_hat_user, g_hat_tgt, omega,
                                      b2["best_rho"])
    out2 = evaluate_decision(snap, const, phi2, rho2, w2, g_hat_tgt)

    # ------------------------------------------------------------- 3) B3
    settings = oracle_gd.OracleGDSettings.from_config(cfg)
    print(f"\n3) B3 Oracle-GD: {settings.iterations} iterasi x "
          f"{settings.restarts} restart, lr {settings.learning_rate}, "
          f"device {settings.device}")
    t0 = time.time()
    out3 = oracle_gd.optimize(snap, const, settings, seed=args.seed,
                              progress=True)
    print(f"   selesai dalam {time.time() - t0:.1f}s | "
          f"restart geometris menang di "
          f"{float(np.mean(out3['restart'] == 0)):.2f} snapshot")

    # ---------------------------------------------------------- ringkasan
    def summary(name, out):
        return {"method": name,
                "reward": float(np.mean(out["reward"])),
                "min_rate": float(np.mean(out["min_rate"])),
                "scnr_median_db": float(np.median(out["worst_scnr_db"])),
                "scnr_p10_db": float(np.percentile(out["worst_scnr_db"], 10)),
                "detection_rate": float(np.mean(out["detected"])),
                "max_power_excess": float(np.max(out["total_power"])
                                          / float(np.max(snap.p_max_watt)) - 1.0)}

    # ------------------------------------------- 4) diagnosis: sapuan lambda
    # Gate 3 bertanya apakah SCNR >= Gamma DAPAT dipenuhi. Bila B3 tidak
    # memenuhinya, ada dua sebab yang sangat berbeda: sistemnya tidak mampu,
    # atau reward (E9) tidak cukup menuntut sehingga B3 memilih tidak. Sapuan
    # lambda memisahkan keduanya: bila menaikkan lambda membuat B3 memenuhi
    # ambang, sistemnya mampu dan yang perlu ditinjau adalah bobot reward.
    lam_rows = []
    for lam in args.lambda_sweep:
        alt = SystemConstants(**{**const.__dict__, "reward_lambda": float(lam)})
        out = oracle_gd.optimize(snap, alt, settings, seed=args.seed)
        lam_rows.append({"lambda": float(lam),
                         "min_rate": float(np.mean(out["min_rate"])),
                         "scnr_median_db": float(np.median(out["worst_scnr_db"])),
                         "scnr_p10_db": float(np.percentile(out["worst_scnr_db"], 10)),
                         "detection_rate": float(np.mean(out["detected"]))})
    print("\n4) Diagnosis: B3 dengan bobot reward lambda berbeda")
    print(f"   {'lambda':>7s} {'min rate':>9s} {'SCNR med':>9s} {'SCNR p10':>9s} "
          f"{'deteksi':>8s}")
    for row in lam_rows:
        print(f"   {row['lambda']:7.1f} {row['min_rate']:9.3f} "
              f"{row['scnr_median_db']:9.1f} {row['scnr_p10_db']:9.1f} "
              f"{row['detection_rate']:8.3f}")

    rows = [summary("B1 random", out1), summary("B2 geometric", out2),
            summary("B3 oracle-GD", out3)]
    print("\nRingkasan val")
    print(f"   {'metode':<14s} {'reward':>8s} {'min rate':>9s} {'SCNR med':>9s} "
          f"{'SCNR p10':>9s} {'deteksi':>8s}")
    for r in rows:
        print(f"   {r['method']:<14s} {r['reward']:8.3f} {r['min_rate']:9.3f} "
              f"{r['scnr_median_db']:9.1f} {r['scnr_p10_db']:9.1f} "
              f"{r['detection_rate']:8.3f}")

    gate = cfg.get("gate3", {})
    target_detection = float(gate.get("oracle_detection_target", 0.90))
    margin = float(gate.get("oracle_over_random_reward_margin", 0.5))
    checks = {
        "oracle_detects": {
            "pass": rows[2]["detection_rate"] >= target_detection,
            "value": rows[2]["detection_rate"], "target": target_detection},
        "oracle_beats_random": {
            "pass": rows[2]["reward"] - rows[0]["reward"] >= margin,
            "value": rows[2]["reward"] - rows[0]["reward"], "target": margin},
        "power_budget": {
            "pass": max(r["max_power_excess"] for r in rows) < 1e-6,
            "value": max(r["max_power_excess"] for r in rows)},
    }
    passed = all(c["pass"] for c in checks.values())
    print("\nGate 3\n------")
    for name, c in checks.items():
        print(f"  [{'PASS' if c['pass'] else 'FAIL'}] {name}: {c['value']}")
    print(f"\nGATE 3: {'LOLOS' if passed else 'GAGAL'}")

    (out_dir / "gate3.json").write_text(json.dumps(
        {"config_hash": chash, "split": args.split, "snapshots": snap.batch,
         "passed": passed, "checks": checks, "methods": rows,
         "clutter": clutter, "b1_tuning": b1, "b2_tuning": b2,
         "lambda_sweep": lam_rows},
        indent=2, default=str), encoding="utf-8")
    (out_dir / "config_used.json").write_text(
        json.dumps(cfg, indent=2, default=str), encoding="utf-8")
    print(f"\nHasil: {out_dir}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
