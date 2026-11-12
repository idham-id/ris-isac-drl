"""Gate 5 - konvergensi M1 dan perbandingan dengan B1/B2 di val (Fase 5).

    python scripts/run_gate5_check.py --config base

**Gate 5:** M1 konvergen (reward val naik < 2% dalam 20% langkah terakhir) dan
mengalahkan B1 serta B2 di val.

Kriteria "naik < 2%" dibuat eksplisit di sini, karena ditulis apa adanya ia
tidak terdefinisi: reward val mulai NEGATIF dan berakhir positif, sehingga
"naik 2%" relatif terhadap nilai awal bisa berarti apa saja (dan membagi
dengan nilai yang melewati nol meledak). Yang dipakai:

    kenaikan_20%_terakhir / total_kenaikan_sejak_langkah_0  <  0,02

yaitu "20% langkah terakhir menyumbang kurang dari 2% perbaikan total". Ini
bebas skala, tidak peduli tanda, dan menjawab pertanyaan yang dimaksud:
apakah pelatihan masih menanjak di ujungnya. Angka mentahnya ikut dilaporkan.

B1 dan B2 dijalankan **lewat environment yang sama** dengan agen, pada
lintasan val yang sama dan seed yang sama (lihat baselines/env_policy.py),
lalu rho (dan omega untuk B2) disapu di grid val sesuai Sec 6.2.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from risisac.baselines.env_policy import make_baseline, tune_baseline  # noqa: E402
from risisac.channels.database import database_path                    # noqa: E402
from risisac.config import (channel_config_hash, config_hash,          # noqa: E402
                            git_commit, load_config)
from risisac.env import EnvConfig, RisIsacEnv, TrajectoryStore         # noqa: E402
from risisac.env.vec import make_vec_env                               # noqa: E402
from risisac.eval.plots import plot_f4_training                        # noqa: E402
from risisac.eval.rollout import (rollout_agent, rollout_baseline,     # noqa: E402
                                  summarise)
from risisac.train import METHODS, run_dir                             # noqa: E402

METRIC = "reward_per_step"


def read_curve(path: Path) -> dict:
    """Baca ``eval_val.csv`` satu run menjadi dict kolom."""
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    header = lines[0].split(",")
    cols: dict[str, list[float]] = {h: [] for h in header}
    for line in lines[1:]:
        for key, value in zip(header, line.split(",")):
            cols[key].append(float(value))
    return cols


def convergence(timesteps, values, tail_fraction: float = 0.2,
                tolerance: float = 0.02) -> dict:
    """Apakah kurva sudah datar di ``tail_fraction`` langkah terakhir?"""
    timesteps = np.asarray(timesteps, dtype=float)
    values = np.asarray(values, dtype=float)
    total = timesteps[-1]
    window = timesteps >= (1.0 - tail_fraction) * total
    first_window = float(values[window][0])
    final = float(values[-1])
    initial = float(values[0])
    total_gain = final - initial
    tail_gain = final - first_window
    # Pembagi memakai |total_gain| supaya tandanya milik tail_gain saja:
    # kurva yang TURUN di ujung menghasilkan rasio negatif (< 0,02), yang
    # memang lolos kriteria "naik < 2%" -- tetapi angkanya terlihat dan bisa
    # dinilai sebagai ketidakstabilan, bukan konvergensi.
    ratio = tail_gain / abs(total_gain) if total_gain != 0 else float("inf")
    slope = float(np.polyfit(timesteps[window], values[window], 1)[0]) \
        if window.sum() >= 2 else 0.0
    return {"initial": initial, "final": final, "total_gain": total_gain,
            "tail_first": first_window, "tail_gain": tail_gain,
            "tail_ratio": float(ratio), "tail_slope_per_1e6": slope * 1e6,
            "converged": bool(ratio < tolerance),
            "tail_fraction": tail_fraction, "tolerance": tolerance}


def agent_runs(cfg, method: str, seeds) -> dict:
    """Kurva dan hasil akhir tiap seed satu metode."""
    out = {}
    for seed in seeds:
        d = run_dir(cfg, method, seed)
        if not (d / "done.json").exists():
            continue
        out[int(seed)] = {"dir": d,
                          "curve": read_curve(d / "eval_val.csv"),
                          "done": json.loads((d / "done.json")
                                             .read_text(encoding="utf-8"))}
    return out


def evaluate_baselines(cfg, db, seed: int, tune: bool, frozen: dict | None) -> dict:
    """Setel (atau pakai nilai beku) lalu evaluasi B1 dan B2 lewat env."""
    store = TrajectoryStore(db, "val")
    env_cfg = dataclasses.replace(EnvConfig.from_config(cfg, "partial"),
                                  phase_update="absolute")
    env = RisIsacEnv(store, env_cfg, train=False, seed=seed)
    indices = list(range(len(store)))

    out = {}
    for name in ("b1", "b2"):
        if tune or frozen is None or name not in frozen:
            t0 = time.time()
            tuned = tune_baseline(name, env, cfg, env_cfg, indices, seed,
                                  verbose=True)
            print(f"   {name.upper()} grid val: {tuned['best']} "
                  f"({time.time() - t0:.1f}s)")
            best = tuned["best"]
            grid = tuned["grid"]
        else:
            best, grid = frozen[name], None
        policy = make_baseline(name, cfg, env_cfg, seed=seed, **best)
        summary = summarise(rollout_baseline(env, policy, indices, seed))
        out[name.upper()] = {"tuned": best, "grid": grid, **summary}
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", default="base")
    ap.add_argument("--methods", nargs="+", default=list(METHODS))
    ap.add_argument("--seeds", nargs="+", type=int, default=None)
    ap.add_argument("--gate-method", default="ppo_po",
                    help="metode yang digate (M1)")
    ap.add_argument("--tail-fraction", type=float, default=0.2)
    ap.add_argument("--tolerance", type=float, default=0.02)
    ap.add_argument("--seed", type=int, default=0,
                    help="seed dasar evaluasi; val memakai seed+1000 seperti "
                         "saat pelatihan, supaya episodenya identik")
    ap.add_argument("--reeval-agents", action="store_true",
                    help="jalankan ulang model tersimpan alih-alih memakai "
                         "evaluasi terakhir dari eval_val.csv")
    args = ap.parse_args()

    cfg = load_config(args.config)
    repo = Path(__file__).resolve().parents[1]
    chash = config_hash(cfg)
    db = database_path(cfg, channel_config_hash(cfg),
                       root=repo / cfg["paths"]["channel_db"])
    seeds = args.seeds or list(range(int(cfg["training"]["num_seeds"])))
    out_dir = repo / "results" / "gate5" / chash
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"config hash : {chash}")
    print(f"basis data  : {db}")
    print(f"seed        : {seeds} | metode {args.methods}")

    runs = {m: agent_runs(cfg, m, seeds) for m in args.methods}
    missing = {m: [s for s in seeds if s not in runs[m]] for m in args.methods}
    for method, seed_list in missing.items():
        if seed_list:
            print(f"  [!] {method}: seed {seed_list} belum ada hasilnya.")

    # ------------------------------------------------------------- baseline
    print("\nBaseline lewat env (split val)")
    eval_seed = args.seed + 1000
    baselines = evaluate_baselines(cfg, db, eval_seed, tune=True, frozen=None)

    # --------------------------------------------------------------- agen
    methods_out: dict[str, dict] = {}
    curves: dict[str, dict] = {}
    for method, by_seed in runs.items():
        if not by_seed:
            continue
        paper_id = METHODS[method]["paper_id"]
        steps_ref = None
        seed_curves, finals = {}, {}
        for seed, info in sorted(by_seed.items()):
            curve = info["curve"]
            steps = curve["timesteps"]
            if steps_ref is None:
                steps_ref = steps
            if len(steps) != len(steps_ref):
                print(f"  [!] {method} seed {seed}: panjang kurva berbeda, "
                      "dilewati dari rata-rata F4.")
                continue
            seed_curves[seed] = curve[METRIC]
            # Yang dilaporkan adalah kebijakan TERPILIH (terbaik di val,
            # §6.1), bukan kebijakan akhir: ketiga seed A1 ambruk setelah
            # puncaknya, jadi model akhir bukan hasil pelatihan yang terbaik.
            finals[seed] = info["done"].get("best_val") or info["done"]["final_val"]
        curves[paper_id] = {"timesteps": steps_ref, "seeds": seed_curves}

        if args.reeval_agents:
            finals = reevaluate(cfg, db, method, by_seed, eval_seed)

        per_seed = {}
        for seed in seed_curves:
            per_seed[seed] = {
                "convergence": convergence(steps_ref, seed_curves[seed],
                                           args.tail_fraction, args.tolerance),
                "final_val": finals[seed]}
        mean_curve = np.mean([seed_curves[s] for s in sorted(seed_curves)], axis=0)
        methods_out[paper_id] = {
            "method": method,
            "seeds": per_seed,
            "mean_convergence": convergence(steps_ref, mean_curve,
                                            args.tail_fraction, args.tolerance),
            "mean_final": {k: float(np.mean([per_seed[s]["final_val"][k]
                                             for s in per_seed]))
                           for k in per_seed[next(iter(per_seed))]["final_val"]
                           if isinstance(per_seed[next(iter(per_seed))]
                                         ["final_val"][k], (int, float))},
            "std_final_reward": float(np.std([per_seed[s]["final_val"][METRIC]
                                              for s in per_seed])),
        }

    # ------------------------------------------------------------- laporan
    print(f"\nHasil val ({args.gate_method} = M1 adalah yang digate)")
    head = (f"   {'metode':<8s} {'reward/lgkh':>12s} {'min rate':>9s} "
            f"{'SCNR med':>9s} {'deteksi':>8s} {'galat trk':>10s} {'rho':>6s}")
    print(head)
    rows = [(name, out) for name, out in baselines.items()]
    rows += [(pid, out["mean_final"]) for pid, out in methods_out.items()]
    for name, out in rows:
        print(f"   {name:<8s} {out[METRIC]:12.3f} {out['min_rate']:9.3f} "
              f"{out['scnr_median_db']:9.1f} {out['detection_rate']:8.3f} "
              f"{out['tracker_error_m']:10.2f} {out['rho_mean']:6.3f}")

    gate_id = METHODS[args.gate_method]["paper_id"]
    gated = methods_out.get(gate_id)
    checks = {}
    if gated is None:
        print(f"\n[!] {gate_id} belum punya hasil; Gate 5 tidak bisa dinilai.")
        passed = False
    else:
        conv = gated["mean_convergence"]
        m1 = gated["mean_final"][METRIC]
        checks = {
            "m1_converged": conv["converged"],
            "m1_beats_b1": m1 > baselines["B1"][METRIC],
            "m1_beats_b2": m1 > baselines["B2"][METRIC],
            "all_seeds_converged": all(s["convergence"]["converged"]
                                       for s in gated["seeds"].values()),
            "all_seeds_beat_b2": all(s["final_val"][METRIC]
                                     > baselines["B2"][METRIC]
                                     for s in gated["seeds"].values()),
        }
        print(f"\nGate 5\n------")
        print(f"  [{'PASS' if checks['m1_converged'] else 'FAIL'}] "
              f"m1_converged: 20% langkah terakhir menyumbang "
              f"{100 * conv['tail_ratio']:.2f}% dari kenaikan total "
              f"({conv['tail_gain']:+.3f} dari {conv['total_gain']:+.3f}); "
              f"ambang {100 * args.tolerance:.0f}%")
        print(f"  [{'PASS' if checks['m1_beats_b1'] else 'FAIL'}] "
              f"m1_beats_b1: {m1:+.3f} lawan {baselines['B1'][METRIC]:+.3f}")
        print(f"  [{'PASS' if checks['m1_beats_b2'] else 'FAIL'}] "
              f"m1_beats_b2: {m1:+.3f} lawan {baselines['B2'][METRIC]:+.3f}")
        print(f"  [info] seed konvergen semua: {checks['all_seeds_converged']}; "
              f"seed mengalahkan B2 semua: {checks['all_seeds_beat_b2']}")
        # Gate 5 TETAP digate pada M1 (Fase 5), walau A1 menjadi metode utama
        # di Fase 8: ambang dan hasilnya sudah tercatat pada besaran itu, dan
        # menukar metode yang digate akan membuat riwayat gate tidak bisa
        # dibaca. Yang berubah hanya bahwa kestabilan metode utama ikut
        # DICETAK di sini, bukan hanya tersimpan di gate5.json -- A1 ambruk
        # setelah puncaknya dan itu tidak boleh tersembunyi di balik gate yang
        # menilai metode lain.
        for paper_id in ("A1", "A1-FullCSI"):
            info = methods_out.get(paper_id)
            if info is None:
                continue
            conv_main = info["mean_convergence"]
            print(f"  [info] {paper_id} (metode utama Fase 8, TIDAK digate): "
                  f"ekor {100 * conv_main['tail_ratio']:+.2f}% dari kenaikan "
                  f"total, konvergen={conv_main['converged']}, "
                  f"reward val {info['mean_final'][METRIC]:+.3f} "
                  f"(std antar-seed {info['std_final_reward']:.3f})")
        passed = all([checks["m1_converged"], checks["m1_beats_b1"],
                      checks["m1_beats_b2"]])
        print(f"\nGATE 5: {'LOLOS' if passed else 'GAGAL'}")

    if curves:
        fig = plot_f4_training(curves, out_dir / "F4_training.png",
                               baselines={k: v[METRIC]
                                          for k, v in baselines.items()})
        print(f"\nF4: {fig}")

    payload = {"config_hash": chash, "git_commit": git_commit(),
               "seeds": seeds, "metric": METRIC,
               "tail_fraction": args.tail_fraction, "tolerance": args.tolerance,
               "baselines": baselines, "methods": methods_out,
               "checks": checks, "passed": bool(passed),
               "curves": {k: {"timesteps": v["timesteps"],
                              "seeds": {str(s): vals
                                        for s, vals in v["seeds"].items()}}
                          for k, v in curves.items()}}
    (out_dir / "gate5.json").write_text(
        json.dumps(payload, indent=2, default=str), encoding="utf-8")
    print(f"Hasil: {out_dir}")
    return 0 if passed else 1


def reevaluate(cfg, db, method: str, by_seed: dict, eval_seed: int) -> dict:
    """Jalankan ulang model tersimpan (pemeriksaan silang eval_val.csv)."""
    from stable_baselines3 import PPO
    from stable_baselines3.common.vec_env import VecNormalize

    spec = METHODS[method]
    store_size = len(TrajectoryStore(db, "val"))
    out = {}
    for seed, info in sorted(by_seed.items()):
        # frame_stack=1 di sini: tumpukan frame dipasang SESUDAH VecNormalize
        # yang dimuat dari pkl, mengikuti urutan saat pelatihan (env/vec.py).
        venv = make_vec_env(db, "val", cfg,
                            observation_mode=spec["observation_mode"],
                            train=False, seed=eval_seed, num_envs=1,
                            subprocess=False, normalize=False, frame_stack=1,
                            env_overrides=spec["env_overrides"])
        venv = VecNormalize.load(str(info["dir"] / "vecnormalize_best.pkl"), venv)
        venv.training = False
        venv.norm_reward = False
        from stable_baselines3.common.vec_env import VecFrameStack
        venv = VecFrameStack(venv, n_stack=int(cfg["observation"]["frame_stack"]))
        model = PPO.load(str(info["dir"] / "model_best"), device="cpu")
        out[seed] = summarise(rollout_agent(model, venv,
                                            list(range(store_size)), eval_seed))
        venv.close()
    return out


if __name__ == "__main__":
    raise SystemExit(main())
