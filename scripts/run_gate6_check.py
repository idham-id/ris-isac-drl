"""Gate 6 - T2, F5, F6, dan F8 lengkap (docs/TASKS.md Fase 6).

    python scripts/run_gate6_check.py                       # base + sapuan Gamma
    python scripts/run_gate6_check.py --config base

Membaca hasil yang sudah ditulis ``risisac.eval.evaluate`` (Parquet), lalu
membuat gambar dan memeriksa kelengkapannya. Tidak menjalankan ulang evaluasi:
gambar paper HARUS dibuat ulang dari file hasil, bukan dari proses yang
kebetulan masih hidup (CLAUDE.md).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from risisac.config import config_hash, load_config           # noqa: E402
from risisac.eval.metrics import seed_means, welch_ttest      # noqa: E402
from risisac.eval.plots import (plot_f5_rate_cdf,             # noqa: E402
                                plot_f6_episode, plot_f8_tradeoff)

#: Config yang menyusun F8, beserta Gamma-nya.
GAMMA_CONFIGS = (("gamma10", 10.0), ("base", 13.0), ("gamma16", 16.0))

#: Metode yang digambar F8. Sengaja dibatasi, dengan dua alasan.
#:
#: 1. Hanya metode yang dilatih ulang di KETIGA nilai Gamma boleh menjadi
#:    garis pada sapuan Gamma. A1-FullCSI dan M2 hanya ada di Gamma = 13 dB,
#:    jadi keduanya akan muncul sebagai satu titik yang tampak seperti ujung
#:    garis yang terpotong.
#: 2. Sepuluh garis di satu gambar trade-off tidak terbaca. Yang disisakan
#:    adalah lantai (B0, tanpa RIS), baseline terapan (B2), langit-langit
#:    (B3 oracle), metode utama (A1), dan ablasinya (M1).
F8_METHODS = ("B0", "B2", "B3", "A1", "M1")


def eval_dir(config: str) -> tuple[Path, dict]:
    cfg = load_config(config)
    return REPO / "results" / "eval" / config_hash(cfg), cfg


def load_eval(config: str):
    import pandas as pd

    d, cfg = eval_dir(config)
    if not (d / "steps.parquet").exists():
        raise SystemExit(
            f"[!] {config}: {d / 'steps.parquet'} belum ada. Jalankan dulu:\n"
            f"    python -m risisac.eval.evaluate --config {config}")
    return (pd.read_parquet(d / "steps.parquet"),
            pd.read_parquet(d / "episodes.parquet"), cfg, d)


def pick_episode(steps, episodes) -> int:
    """Lintasan contoh untuk F6: episode terpanjang yang dialami SEMUA metode.

    Dipilih yang terpanjang supaya dinamika sepanjang episode terlihat, bukan
    dipilih karena hasilnya bagus -- pemilihan berdasarkan hasil akan membuat
    F6 menjadi iklan, bukan ilustrasi.
    """
    lengths = episodes.groupby("trajectory_index")["steps"].max()
    return int(lengths.idxmax())


def f8_points(configs=GAMMA_CONFIGS, methods=F8_METHODS) -> list[dict]:
    """Titik F8: satu per (metode, Gamma), plus titik per seed untuk agen."""
    points = []
    for config, gamma in configs:
        _, episodes, _, _ = load_eval(config)
        for method, g in episodes.groupby("method"):
            if method not in methods:
                continue
            per_seed = [(float(s["scnr_compliance"].mean()),
                         float(s["min_rate"].mean()))
                        for _, s in g.groupby("train_seed")]
            points.append({
                "method": method, "gamma_db": float(gamma),
                "min_rate": float(np.mean([p[1] for p in per_seed])),
                "scnr_compliance": float(np.mean([p[0] for p in per_seed])),
                "per_seed": per_seed if method.startswith(("M", "A")) else [],
            })
    return points


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", default="base")
    ap.add_argument("--skip-f8", action="store_true")
    args = ap.parse_args()

    steps, episodes, cfg, out_dir = load_eval(args.config)
    gamma = float(cfg["sensing"]["scnr_threshold_db"])
    print(f"config      : {args.config} ({out_dir.name})")
    print(f"langkah     : {len(steps)} | episode: {len(episodes)}")

    made = {}
    made["T2"] = out_dir / "T2.csv"

    made["F5"] = plot_f5_rate_cdf(steps, out_dir / "F5_rate_cdf.png",
                                  scnr_threshold_db=gamma)
    index = pick_episode(steps, episodes)
    made["F6"] = plot_f6_episode(
        steps, out_dir / "F6_episode.png", index,
        scnr_threshold_db=gamma,
        sigma_max_m=float(cfg["observation"]["target_pos_max_std_m"]),
        dt_s=float(cfg["mobility"]["dt_s"]))
    print(f"F6          : lintasan {index} "
          f"({int(episodes.loc[episodes['trajectory_index'] == index, 'steps'].max())} langkah)")

    if not args.skip_f8:
        points = f8_points()
        made["F8"] = plot_f8_tradeoff(points, out_dir / "F8_tradeoff.png")
        (out_dir / "F8_points.json").write_text(
            json.dumps(points, indent=2), encoding="utf-8")
        print("\nF8 - trade-off (rata-rata antar-seed)")
        print(f"   {'metode':<8s} {'Gamma':>6s} {'rate min':>9s} {'pemenuhan':>10s}")
        for p in sorted(points, key=lambda r: (r["method"], r["gamma_db"])):
            print(f"   {p['method']:<8s} {p['gamma_db']:6.0f} "
                  f"{p['min_rate']:9.3f} {p['scnr_compliance']:10.3f}")

    # --------------------------------------------------------------- uji beda
    print("\nUji beda utama (§9; Welch atas rata-rata per seed, n = 3)")
    for column in ("reward_per_step", "min_rate", "scnr_compliance"):
        means = seed_means(episodes, column)
        for main, other in (("A1", "B0"), ("A1", "B2"), ("A1", "B4-D5"),
                            ("A1", "A1-FullCSI"), ("M1", "B2")):
            if main in means and other in means:
                r = welch_ttest(means[main], means[other])
                print(f"   {column:<16s} {main:<11s} vs {other:<11s} "
                      f"selisih {r['diff']:+7.3f}  p {r['p']:.4f}")

    # ----------------------------------------------------------------- gate 6
    print("\nGate 6\n------")
    ok = True
    for name, path in made.items():
        exists = Path(path).exists()
        ok = ok and exists
        print(f"  [{'PASS' if exists else 'FAIL'}] {name}: {path}")
    if args.skip_f8:
        ok = False
        print("  [FAIL] F8: dilewati (--skip-f8)")
    print(f"\nGATE 6: {'LOLOS' if ok else 'GAGAL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
