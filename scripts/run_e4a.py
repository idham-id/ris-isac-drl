"""E4a (P2) - kinerja terhadap P_max dan kecepatan target, tanpa latih ulang.

    python scripts/run_e4a.py --config base

§5.5 mengacak P_max 20-40 dBm dan kecepatan target saat pelatihan, justru
supaya satu agen bisa diuji di seluruh rentang tanpa dilatih ulang. E4a
menagih janji itu:

* **sapuan P_max** (``evaluation.p_max_eval_dbm``) memerlukan rollout baru di
  tiap nilai, karena P_max mengubah env;
* **kelompok kecepatan** (``mobility.speed_eval_bins_mps``) tidak memerlukan
  rollout baru sama sekali -- ia hanya memilah lintasan dari hasil E3 yang
  sudah ada menurut kecepatan targetnya. Menjalankannya ulang akan memberi
  angka yang sama persis dengan biaya penuh.

Keluaran: ``F7_pmax_speed.png`` dan ``E4a.csv`` di direktori hasil evaluasi.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
import time
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from risisac.channels.database import database_path            # noqa: E402
from risisac.config import (channel_config_hash, config_hash,  # noqa: E402
                            git_commit, load_config)
from risisac.env import EnvConfig, RisIsacEnv, TrajectoryStore  # noqa: E402
from risisac.eval.evaluate import run_agents, run_baselines     # noqa: E402
from risisac.eval.metrics import cluster_bootstrap              # noqa: E402
from risisac.eval.plots import plot_f7_pmax_speed               # noqa: E402
from risisac.baselines.env_policy import tune_baseline          # noqa: E402
from risisac.system import signal_model as sm                   # noqa: E402

#: Metrik yang digambar F7, dan apakah ia butuh ambang.
PANEL_METRICS = (("min_rate", "rate minimum (bit/s/Hz)"),
                 ("scnr_compliance", "pemenuhan SCNR"))


def speed_group(store, bins) -> dict[int, int]:
    """Petakan indeks lintasan -> indeks kelompok kecepatan (atau -1)."""
    out = {}
    for i in range(len(store)):
        speed = float(store[i].target_speed_mps[0])
        out[i] = -1
        for g, (lo, hi) in enumerate(bins):
            # Tepi atas inklusif: bin [[1,3],[4,7],[8,10]] meninggalkan celah
            # di 3-4 dan 7-8, jadi lintasan di celah itu dimasukkan ke bin
            # TERDEKAT ketimbang dibuang diam-diam.
            if float(lo) <= speed <= float(hi):
                out[i] = g
                break
        if out[i] == -1:
            centres = [0.5 * (float(lo) + float(hi)) for lo, hi in bins]
            out[i] = int(np.argmin([abs(speed - c) for c in centres]))
    return out


def aggregate(episodes, column: str, seed: int = 0) -> dict:
    return cluster_bootstrap(episodes[column].to_numpy(),
                             episodes["train_seed"].to_numpy(),
                             n_boot=2000, seed=seed)


def main() -> int:
    import pandas as pd

    from risisac.eval.metrics import episode_table

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", default="base")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--methods", nargs="+", default=["M1", "M2", "A1", "B2"])
    args = ap.parse_args()

    cfg = load_config(args.config)
    chash = config_hash(cfg)
    db = database_path(cfg, channel_config_hash(cfg),
                       root=REPO / cfg["paths"]["channel_db"])
    env_cfg = EnvConfig.from_config(cfg, "partial")
    out_dir = REPO / "results" / "eval" / chash
    out_dir.mkdir(parents=True, exist_ok=True)

    store = TrajectoryStore(db, "test")
    indices = list(range(len(store)))
    from risisac.eval.evaluate import noise_seeds
    seeds = noise_seeds(cfg, args.seed)
    train_seeds = list(range(int(cfg["training"]["num_seeds"])))
    dt_s = float(cfg["mobility"]["dt_s"])
    sigma_max = float(cfg["observation"]["target_pos_max_std_m"])
    gamma = float(cfg["sensing"]["scnr_threshold_db"])

    # ---------------------------------------------------- B1/B2 disetel di val
    plain = dataclasses.replace(env_cfg, phase_update="absolute")
    val_store = TrajectoryStore(db, "val")
    val_env = RisIsacEnv(val_store, plain, train=False, seed=args.seed + 1000)
    tuned = {n: tune_baseline(n, val_env, cfg, plain,
                              list(range(len(val_store))),
                              args.seed + 1000)["best"] for n in ("b1", "b2")}
    print(f"B1/B2 dari grid val: {tuned}")

    # ------------------------------------------------------------ sapuan P_max
    p_max_list = [float(v) for v in cfg["evaluation"]["p_max_eval_dbm"]]
    print(f"\nSapuan P_max {p_max_list} dBm "
          f"({len(p_max_list)} nilai x {len(indices)} lintasan "
          f"x {len(seeds)} seed derau)")
    rows = []
    t0 = time.time()
    for p_dbm in p_max_list:
        watt = sm.dbm_to_watt(p_dbm)
        swept = dataclasses.replace(env_cfg, p_max_eval_watt=watt)
        step_rows, _ = run_baselines(cfg, db, swept, indices, seeds, tuned,
                                     verbose=False, include_oracle=False)
        step_rows += run_agents(cfg, db, indices, seeds, train_seeds,
                                verbose=False,
                                extra_overrides={"p_max_eval_watt": watt})
        frame = pd.DataFrame(step_rows)
        frame["p_max_dbm"] = p_dbm
        rows.append(frame)
        print(f"   {p_dbm:5.1f} dBm selesai ({time.time() - t0:.0f}s)")
    steps = pd.concat(rows, ignore_index=True)
    steps.to_parquet(out_dir / "E4a_pmax_steps.parquet", index=False)

    pmax_rows = []
    for p_dbm, g in steps.groupby("p_max_dbm"):
        eps = episode_table(g, dt_s, sigma_max, gamma)
        for method, gm in eps.groupby("method"):
            if method not in args.methods:
                continue
            entry = {"axis": "p_max_dbm", "x": float(p_dbm), "method": method}
            for column, _ in PANEL_METRICS:
                out = aggregate(gm, column, args.seed)
                entry[column] = out["mean"]
                entry[f"{column}_lo"] = out["ci_low"]
                entry[f"{column}_hi"] = out["ci_high"]
            pmax_rows.append(entry)

    # ------------------------------------------------- kelompok kecepatan (E3)
    e3 = pd.read_parquet(out_dir / "steps.parquet")
    groups = speed_group(store, cfg["mobility"]["speed_eval_bins_mps"])
    e3 = e3.copy()
    e3["speed_group"] = e3["trajectory_index"].map(groups)
    bins = [list(map(float, b)) for b in cfg["mobility"]["speed_eval_bins_mps"]]
    counts = {g: int(sum(1 for v in groups.values() if v == g))
              for g in range(len(bins))}
    print(f"\nKelompok kecepatan (dari E3, P_max "
          f"{cfg['radio']['p_max_dbm']} dBm): {counts} lintasan")

    speed_rows = []
    for g, gg in e3.groupby("speed_group"):
        eps = episode_table(gg, dt_s, sigma_max, gamma)
        for method, gm in eps.groupby("method"):
            if method not in args.methods:
                continue
            entry = {"axis": "speed_group", "x": float(g), "method": method,
                     "speed_lo": bins[int(g)][0], "speed_hi": bins[int(g)][1],
                     "trajectories": counts[int(g)]}
            for column, _ in PANEL_METRICS:
                out = aggregate(gm, column, args.seed)
                entry[column] = out["mean"]
                entry[f"{column}_lo"] = out["ci_low"]
                entry[f"{column}_hi"] = out["ci_high"]
            speed_rows.append(entry)

    table = pd.DataFrame(pmax_rows + speed_rows)
    table.to_csv(out_dir / "E4a.csv", index=False)

    f7 = plot_f7_pmax_speed(table, out_dir / "F7_pmax_speed.png", bins,
                            metrics=PANEL_METRICS)
    (out_dir / "E4a_meta.json").write_text(json.dumps({
        "config": args.config, "config_hash": chash,
        "git_commit": git_commit(), "p_max_dbm": p_max_list,
        "speed_bins_mps": bins, "trajectories_per_bin": counts,
        "noise_seeds": seeds, "train_seeds": train_seeds,
        "tuned_baselines": tuned,
        "note": ("kelompok kecepatan memilah hasil E3, bukan rollout baru; "
                 "sapuan P_max memakai rollout baru tanpa latih ulang"),
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
    }, indent=2, default=str), encoding="utf-8")

    print("\nE4a - rate minimum dan pemenuhan SCNR")
    with pd.option_context("display.width", 150,
                           "display.float_format", lambda v: f"{v:7.3f}"):
        print(table[["axis", "x", "method", "min_rate",
                     "scnr_compliance"]].to_string(index=False))
    print(f"\nF7: {f7}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
