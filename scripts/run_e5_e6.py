"""E5 dan E6 (P2) -> T3: ablasi fasa dan biaya komputasi.

    python scripts/run_e5_e6.py --precompute-seconds 520.1

**E5 (ablasi, §7).** Fasa inkremental lawan absolut, dibuat kuantitatif oleh
sapuan kappa. Angkanya diambil dari hasil **set test** yang sudah ditulis
``risisac.eval.evaluate`` untuk config ``base``, ``kappa025``, dan
``kappa050`` -- bukan dari val, dan bukan dijalankan ulang di sini.

**E6 (biaya komputasi, §7).** Waktu keputusan diukur di mesin ini, sekarang:
satu keputusan agen lawan satu langkah B2 lawan satu langkah Oracle-GD. Dua
angka dilaporkan untuk B3, dan perbedaannya besar:

* **daring** -- satu snapshot per panggilan, yaitu biaya yang benar-benar
  harus dibayar bila B3 dipakai sebagai pengendali;
* **terbatch** -- seluruh langkah set evaluasi sekaligus, yaitu cara B3
  dijalankan di sini sebagai acuan offline.

Melaporkan hanya yang terbatch akan membuat oracle tampak jauh lebih murah
daripada yang sebenarnya.

Waktu prakomputasi ray tracing TIDAK diukur ulang (CLAUDE.md: jangan
menjalankan ray tracing bersama proses GPU lain). Nilainya diberikan lewat
``--precompute-seconds`` dan sumbernya dicatat di ``T3_meta.json``.
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

from risisac.baselines.env_policy import (episode_snapshot,       # noqa: E402
                                          make_baseline,
                                          tune_baseline)
from risisac.channels.database import database_path               # noqa: E402
from risisac.config import (channel_config_hash, config_hash,     # noqa: E402
                            git_commit, load_config)
from risisac.env import EnvConfig, RisIsacEnv, TrajectoryStore    # noqa: E402
from risisac.env.vec import make_vec_env                          # noqa: E402
from risisac.train import METHODS, run_dir                        # noqa: E402

#: Baris E5: (label, config, paper_id). Urutannya mengikuti peran Fase 8:
#: metode utama lebih dulu, lalu ablasi OBSERVASI (A1-FullCSI, yang berbeda
#: dari A1 hanya pada mode observasi), lalu ablasi PARAMETERISASI FASA
#: (M1 beserta sapuan kappa, dan M2), lalu pembanding.
#: Label di sini hanya cadangan: tabel LaTeX memetakan labelnya sendiri dari
#: kolom ``metode`` dan ``config`` (``eval/tables.py``, E5_LABELS), supaya
#: teksnya bisa diubah tanpa menjalankan ulang E5 dan E6.
E5_ROWS = (
    ("A1 absolute phase, partial obs. (main)", "base", "A1"),
    ("A1-FullCSI absolute phase, full obs.", "base", "A1-FullCSI"),
    ("M1 incremental phase, kappa = 0.10", "base", "M1"),
    ("M1 incremental phase, kappa = 0.25", "kappa025", "M1"),
    ("M1 incremental phase, kappa = 0.50", "kappa050", "M1"),
    ("M2 incremental phase, full CSI", "base", "M2"),
    ("B0 no RIS (perfect direct CSI)", "base", "B0"),
    ("B2 geometric (absolute phase)", "base", "B2"),
    ("B3 oracle (absolute phase)", "base", "B3"),
)


def read_episodes(config: str):
    import pandas as pd

    cfg = load_config(config)
    path = REPO / "results" / "eval" / config_hash(cfg) / "episodes.parquet"
    if not path.exists():
        raise SystemExit(f"[!] {config}: {path} belum ada. Jalankan dulu "
                         f"`python -m risisac.eval.evaluate --config {config}`")
    return pd.read_parquet(path), cfg


def e5_table(seed: int = 0):
    """Tabel ablasi dari hasil test tiap config."""
    import pandas as pd

    from risisac.eval.metrics import cluster_bootstrap

    cache: dict[str, object] = {}
    rows = []
    for label, config, paper_id in E5_ROWS:
        if config not in cache:
            cache[config] = read_episodes(config)[0]
        episodes = cache[config]
        g = episodes[episodes["method"] == paper_id]
        if g.empty:
            print(f"   [!] {label}: {paper_id} tidak ada di {config}")
            continue
        entry = {"varian": label, "config": config, "metode": paper_id,
                 "episode": int(len(g))}
        for column in ("reward_per_step", "min_rate", "scnr_compliance",
                       "track_duration_s"):
            out = cluster_bootstrap(g[column].to_numpy(),
                                    g["train_seed"].to_numpy(),
                                    n_boot=2000, seed=seed)
            entry[column] = out["mean"]
            entry[f"{column}_lo"] = out["ci_low"]
            entry[f"{column}_hi"] = out["ci_high"]
        rows.append(entry)
    return pd.DataFrame(rows)


# ------------------------------------------------------------------- E6
def time_agent(cfg, db, method: str, seed: int, repeats: int) -> dict:
    """Waktu satu panggilan ``predict`` agen, di CPU seperti saat dipakai."""
    from stable_baselines3 import PPO
    from stable_baselines3.common.vec_env import VecFrameStack, VecNormalize

    spec = METHODS[method]
    d = run_dir(cfg, method, seed)
    if not (d / "done.json").exists():
        return {}
    venv = make_vec_env(db, "test", cfg,
                        observation_mode=spec["observation_mode"],
                        train=False, seed=9000, num_envs=1, subprocess=False,
                        normalize=False, frame_stack=1,
                        env_overrides=spec["env_overrides"])
    venv = VecNormalize.load(str(d / "vecnormalize_best.pkl"), venv)
    venv.training = False
    venv.norm_reward = False
    venv = VecFrameStack(venv, n_stack=int(cfg["observation"]["frame_stack"]))
    model = PPO.load(str(d / "model_best"), device="cpu")

    obs = venv.reset()
    for _ in range(20):                      # pemanasan
        model.predict(obs, deterministic=True)
    t0 = time.perf_counter()
    for _ in range(repeats):
        model.predict(obs, deterministic=True)
    elapsed = time.perf_counter() - t0
    out = {"ms_per_decision": 1e3 * elapsed / repeats,
           "observation_dim": int(obs.shape[-1]),
           "device": "cpu", "repeats": repeats}
    venv.close()
    return out


def time_baseline_b2(cfg, db, env_cfg, repeats: int, tuned: dict) -> dict:
    store = TrajectoryStore(db, "test")
    plain = dataclasses.replace(env_cfg, phase_update="absolute")
    env = RisIsacEnv(store, plain, train=False, seed=9000)
    env.reset(seed=9000, options={"trajectory_index": 0})
    policy = make_baseline("b2", cfg, plain, seed=9000, **tuned)
    policy.reset(env)
    for _ in range(10):
        policy.act(env)
    t0 = time.perf_counter()
    for _ in range(repeats):
        policy.act(env)
    return {"ms_per_decision": 1e3 * (time.perf_counter() - t0) / repeats,
            "repeats": repeats}


def time_oracle(cfg, db, env_cfg, online_calls: int) -> dict:
    """Biaya Oracle-GD: satu snapshot (daring) dan seluruh set (terbatch)."""
    from risisac.baselines import oracle_gd
    from risisac.baselines.common import SystemConstants
    from risisac.baselines.env_policy import episode_length

    store = TrajectoryStore(db, "test")
    const = SystemConstants.from_config(cfg)
    settings = oracle_gd.OracleGDSettings.from_config(cfg)

    one = episode_snapshot(store[0], store, env_cfg, 1)
    oracle_gd.optimize(one, const, settings, seed=0)          # pemanasan
    t0 = time.perf_counter()
    for _ in range(online_calls):
        oracle_gd.optimize(one, const, settings, seed=0)
    online_ms = 1e3 * (time.perf_counter() - t0) / online_calls

    indices = range(len(store))
    lengths = {i: episode_length(store[i], env_cfg) for i in indices}
    from risisac.baselines.env_policy import _concat_snapshots
    big = _concat_snapshots([episode_snapshot(store[i], store, env_cfg,
                                              lengths[i]) for i in indices])
    t0 = time.perf_counter()
    oracle_gd.optimize(big, const, settings, seed=0)
    batched = time.perf_counter() - t0
    return {"ms_per_decision_online": online_ms,
            "ms_per_decision_batched": 1e3 * batched / big.batch,
            "batch_steps": int(big.batch), "batch_seconds": batched,
            "device": settings.device, "iterations": settings.iterations,
            "restarts": settings.restarts, "online_calls": online_calls}


def training_cost(cfg) -> dict:
    """Waktu pelatihan tiap metode dari ``done.json`` (bukan diukur ulang)."""
    out = {}
    for method, spec in METHODS.items():
        times, steps = [], []
        for seed in range(int(cfg["training"]["num_seeds"])):
            path = run_dir(cfg, method, seed) / "done.json"
            if path.exists():
                d = json.loads(path.read_text(encoding="utf-8"))
                times.append(float(d["train_seconds"]))
                steps.append(float(d["steps_per_second"]))
        if times:
            out[spec["paper_id"]] = {
                "train_minutes_mean": float(np.mean(times)) / 60.0,
                "steps_per_second_mean": float(np.mean(steps)),
                "seeds": len(times)}
    return out


def main() -> int:
    import pandas as pd

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", default="base")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--repeats", type=int, default=2000)
    ap.add_argument("--oracle-online-calls", type=int, default=20)
    ap.add_argument("--precompute-seconds", type=float, default=None,
                    help="waktu prakomputasi ray tracing yang SUDAH tercatat "
                         "(docs/LOG.md); tidak diukur ulang di sini")
    ap.add_argument("--precompute-source", default="docs/LOG.md (Fase 2)")
    args = ap.parse_args()

    cfg = load_config(args.config)
    chash = config_hash(cfg)
    db = database_path(cfg, channel_config_hash(cfg),
                       root=REPO / cfg["paths"]["channel_db"])
    env_cfg = EnvConfig.from_config(cfg, "partial")
    out_dir = REPO / "results" / "eval" / chash
    out_dir.mkdir(parents=True, exist_ok=True)

    print("E5 - ablasi fasa (set test)")
    e5 = e5_table(args.seed)
    e5.to_csv(out_dir / "T3_e5_ablation.csv", index=False)
    with pd.option_context("display.width", 160,
                           "display.float_format", lambda v: f"{v:7.3f}"):
        print(e5[["varian", "episode", "reward_per_step", "min_rate",
                  "scnr_compliance", "track_duration_s"]].to_string(index=False))

    print("\nE6 - biaya komputasi (diukur di mesin ini)")
    plain = dataclasses.replace(env_cfg, phase_update="absolute")
    val_store = TrajectoryStore(db, "val")
    val_env = RisIsacEnv(val_store, plain, train=False, seed=args.seed + 1000)
    tuned_b2 = tune_baseline("b2", val_env, cfg, plain,
                             list(range(len(val_store))),
                             args.seed + 1000)["best"]

    e6 = {"agents": {}, "baselines": {}}
    for method, spec in METHODS.items():
        got = time_agent(cfg, db, method, 0, args.repeats)
        if got:
            e6["agents"][spec["paper_id"]] = got
            print(f"   {spec['paper_id']}: {got['ms_per_decision']:.3f} ms "
                  f"per keputusan (observasi {got['observation_dim']}, CPU)")
    e6["baselines"]["B2"] = time_baseline_b2(cfg, db, env_cfg, args.repeats,
                                             tuned_b2)
    print(f"   B2: {e6['baselines']['B2']['ms_per_decision']:.3f} ms "
          f"per keputusan")
    e6["baselines"]["B3"] = time_oracle(cfg, db, env_cfg,
                                        args.oracle_online_calls)
    b3 = e6["baselines"]["B3"]
    print(f"   B3: {b3['ms_per_decision_online']:.1f} ms per keputusan "
          f"DARING ({b3['iterations']} iterasi x {b3['restarts']} restart, "
          f"{b3['device']}); {b3['ms_per_decision_batched']:.2f} ms "
          f"teramortisasi saat {b3['batch_steps']} langkah dibatch")

    e6["training"] = training_cost(cfg)
    for paper_id, t in e6["training"].items():
        print(f"   latih {paper_id}: {t['train_minutes_mean']:.1f} menit "
              f"({t['steps_per_second_mean']:.0f} langkah/detik, "
              f"{t['seeds']} seed)")
    if args.precompute_seconds is not None:
        e6["precompute"] = {"seconds": float(args.precompute_seconds),
                            "minutes": float(args.precompute_seconds) / 60.0,
                            "source": args.precompute_source,
                            "measured_here": False}
        print(f"   prakomputasi ray tracing: "
              f"{e6['precompute']['minutes']:.1f} menit "
              f"({args.precompute_source}, tidak diukur ulang)")

    # Dilaporkan untuk metode utama (A1) dan untuk M1. Keduanya disimpan:
    # angka M1 sudah dikutip di Fase 6 dan di dokumen keputusan, jadi
    # menghapusnya akan membuat catatan lama tidak bisa dicocokkan lagi.
    print("")
    for paper_id, key in (("A1", "a1_vs_b3_online_speedup"),
                          ("M1", "m1_vs_b3_online_speedup")):
        value = (b3["ms_per_decision_online"]
                 / e6["agents"][paper_id]["ms_per_decision"]) \
            if paper_id in e6["agents"] else None
        e6[key] = value
        if value:
            print(f"   {paper_id} {value:,.0f}x lebih cepat daripada B3 "
                  f"daring per keputusan")

    (out_dir / "T3_e6_cost.json").write_text(
        json.dumps(e6, indent=2, default=str), encoding="utf-8")
    (out_dir / "T3_meta.json").write_text(json.dumps({
        "config": args.config, "config_hash": chash,
        "git_commit": git_commit(),
        "e5_source": "results/eval/<hash>/episodes.parquet (set test)",
        "e6_measured_on": "CPU i5-13600KF / GPU RTX 4070 (lihat docs/LOG.md)",
        "precompute_measured_here": False,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
    }, indent=2, default=str), encoding="utf-8")
    print(f"\nHasil: {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
