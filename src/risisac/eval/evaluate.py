"""E3 - evaluasi semua metode pada set test (docs/EXPERIMENT_DESIGN.md §7).

    python -m risisac.eval.evaluate --config base

Protokol (§7 E3, §9): 50 lintasan test x 3 seed derau = 150 episode per seed
latih, P_max tetap 30 dBm. Agen dievaluasi pada ketiga seed latihnya, jadi
M1/M2/A1 masing-masing 450 episode. Baseline tidak punya seed latih; seed
deraunya dipakai sebagai seed "latih" semu supaya pengelompokan bootstrap
(§9) tetap punya tiga kelompok yang setara.

**Set test baru disentuh di sini.** Seluruh penyetelan -- rho dan omega untuk
B1/B2, pemilihan checkpoint agen (§6.1) -- sudah selesai di val sebelum file
ini dijalankan, dan nilainya dibekukan lalu dicatat di ``meta.json``.

Semua metode melewati **env yang sama**: lintasan sama, langkah sama, mesin
reward sama. Yang berbeda hanya keputusannya. Dua pengecualian yang disengaja
dan dinyatakan di §6.2:

* baseline berjalan pada ``phase_update='absolute'`` karena B1 ("fasa acak per
  langkah") dan B2 (rumus fasa absolut) tidak terdefinisi pada aksi
  inkremental. Ini merugikan agen M1, bukan menguntungkannya: M1 harus
  merambat 0,1 pi per langkah sementara baseline boleh melompat;
* B3/B4 berjalan dengan ``perfect_csi=True`` karena §6.2 memberi keduanya
  "CSI dan posisi sempurna". Keduanya acuan atas, bukan metode yang bisa
  diterapkan.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
import time
from pathlib import Path

import numpy as np

from ..baselines.env_policy import (OracleEnvPolicy, make_baseline,
                                    precompute_oracle, tune_baseline)
from ..channels.database import database_path
from ..config import (channel_config_hash, config_hash, git_commit,
                      load_config)
from ..env import EnvConfig, RisIsacEnv, TrajectoryStore
from ..env.vec import make_vec_env
from ..train import METHODS, run_dir
from .rollout import STEP_FIELDS, rollout_agent, rollout_baseline

#: Urutan metode di tabel dan gambar paper (Fase 8). A1 adalah metode utama;
#: M1 dan M2 turun menjadi ablasi parameterisasi fasa dan dicetak terakhir.
#: Kunci metode dan nama direktori hasil TIDAK ikut berubah -- yang berpindah
#: hanya peran dan urutan tampilan, supaya provenans tiap run tetap utuh.
METHOD_ORDER = ("B0", "B1", "B2", "B3", "B4-D5", "B4-D10",
                "A1", "A1-FullCSI", "M1", "M2")

#: Baseline yang disetel di val lalu dibekukan untuk test.
TUNED_BASELINES = ("b0", "b1", "b2")


def noise_seeds(cfg: dict, base_seed: int) -> list[int]:
    """Seed derau evaluasi, terpisah jauh dari seed val yang dipakai §6.1.

    Jaraknya 1000 karena ``rollout_*`` memakai ``seed + indeks_lintasan``:
    dengan 50 lintasan, jarak 1000 menjamin tidak ada seed yang bertabrakan
    antar-kelompok derau.
    """
    n = int(cfg["evaluation"]["noise_seeds_per_trajectory"])
    return [int(base_seed) + 2000 + 1000 * j for j in range(n)]


def episode_rows(episodes: list[dict], method: str, train_seed: int,
                 noise_seed: int) -> list[dict]:
    """Ubah keluaran ``rollout_*`` menjadi baris per langkah."""
    rows = []
    for ep in episodes:
        index = int(ep["trajectory_index"])
        for t in range(len(ep["reward"])):
            row = {"method": method, "train_seed": int(train_seed),
                   "noise_seed": int(noise_seed), "trajectory_index": index,
                   "step": t, "reward": float(ep["reward"][t])}
            row.update({k: float(ep[k][t]) for k in STEP_FIELDS})
            rows.append(row)
    return rows


# --------------------------------------------------------------- baseline
def baseline_env_configs(env_cfg: EnvConfig) -> dict:
    """Varian ``EnvConfig`` yang dipakai tiap keluarga baseline (§6.2).

    * ``plain``  -- B1/B2: hanya ``phase_update='absolute'``, informasi sama
      dengan agen.
    * ``b0``     -- tambahan ``no_ris`` dan ``perfect_csi``: sistem tanpa RIS
      dengan CSI langsung sempurna.
    * ``oracle`` -- tambahan ``perfect_csi``: B3/B4.

    Dikumpulkan di satu tempat supaya penyetelan di val dan evaluasi di test
    tidak bisa memakai varian env yang berbeda -- kesalahan yang hasilnya
    terlihat masuk akal dan karena itu tidak akan ketahuan.
    """
    plain = dataclasses.replace(env_cfg, phase_update="absolute")
    return {"plain": plain,
            "b0": dataclasses.replace(plain, no_ris=True, perfect_csi=True),
            "oracle": dataclasses.replace(plain, perfect_csi=True)}


def tune_baselines(cfg: dict, db: Path, env_cfg: EnvConfig, seed: int,
                   names=TUNED_BASELINES, verbose: bool = True) -> dict:
    """Sapu grid val untuk tiap baseline, lalu bekukan hasilnya untuk test."""
    variants = baseline_env_configs(env_cfg)
    val_store = TrajectoryStore(db, "val")
    val_indices = list(range(len(val_store)))
    tuned = {}
    for name in names:
        variant = variants["b0"] if name == "b0" else variants["plain"]
        env = RisIsacEnv(val_store, variant, train=False, seed=seed + 1000)
        res = tune_baseline(name, env, cfg, variant, val_indices, seed + 1000)
        tuned[name] = res["best"]
        if verbose:
            print(f"   {name.upper()}: {res['best']}")
    return tuned


def run_baselines(cfg: dict, db: Path, env_cfg: EnvConfig, indices,
                  seeds: list[int], tuned: dict, verbose: bool = True,
                  include_oracle: bool = True) -> list:
    """B1, B2, B3, B4(D) pada set test.

    :param include_oracle: ``False`` melewati B3/B4. Dipakai E4a, yang menyapu
        P_max untuk melihat kinerja AGEN tanpa latih ulang; acuan atas tidak
        menambah apa pun di sana dan Oracle-GD harus dijalankan ulang untuk
        tiap P_max.
    """
    store = TrajectoryStore(db, "test")
    variants = baseline_env_configs(env_cfg)
    plain, b0_cfg, oracle_cfg = (variants["plain"], variants["b0"],
                                 variants["oracle"])

    def run_plain(rows: list, noise_seed: int) -> list:
        """B0, B1, B2 pada satu seed derau. B0 memakai varian env-nya sendiri."""
        for name in [n for n in TUNED_BASELINES if n in tuned]:
            variant = b0_cfg if name == "b0" else plain
            env = RisIsacEnv(store, variant, train=False, seed=noise_seed)
            policy = make_baseline(name, cfg, variant, seed=noise_seed,
                                   **tuned[name])
            eps = rollout_baseline(env, policy, indices, noise_seed)
            rows += episode_rows(eps, name.upper(), noise_seed, noise_seed)
        return rows

    if not include_oracle:
        rows = []
        for noise_seed in seeds:
            run_plain(rows, noise_seed)
        return rows, None

    t0 = time.time()
    oracle = precompute_oracle(store, cfg, env_cfg, indices,
                               seed=int(seeds[0]), verbose=verbose)
    if verbose:
        print(f"   B3 praoptimasi: {time.time() - t0:.1f}s | "
              f"p_raw di luar kotak aksi env: "
              f"{100 * oracle['clipped_fraction']:.1f}% "
              f"(reward mesin snapshot {oracle['oracle_reward_per_step']:+.3f})")

    periods = [int(d) for d in cfg["baselines"]["stale_period_steps"]]
    rows = []
    for noise_seed in seeds:
        run_plain(rows, noise_seed)
        env_oracle = RisIsacEnv(store, oracle_cfg, train=False, seed=noise_seed)
        for period in [1] + periods:
            policy = OracleEnvPolicy(oracle["decisions"], period)
            eps = rollout_baseline(env_oracle, policy, indices, noise_seed)
            rows += episode_rows(eps, policy.name, noise_seed, noise_seed)
        if verbose:
            print(f"   seed derau {noise_seed}: baseline selesai")
    return rows, oracle


# ------------------------------------------------------------------- agen
def run_agents(cfg: dict, db: Path, indices, seeds: list[int],
               train_seeds: list[int], verbose: bool = True,
               extra_overrides: dict | None = None,
               methods: dict | None = None) -> list:
    """M1, M2, A1 pada set test, tiap seed latih x tiap seed derau.

    :param extra_overrides: field ``EnvConfig`` tambahan untuk evaluasi, mis.
        ``{"p_max_eval_watt": ...}`` pada E4a. Kebijakannya TIDAK dilatih
        ulang; inilah yang membuat E4a murah (§5.5: P_max diacak saat latih).
    """
    from stable_baselines3 import PPO
    from stable_baselines3.common.vec_env import VecFrameStack, VecNormalize

    rows = []
    for method, spec in (methods or METHODS).items():
        paper_id = spec["paper_id"]
        for train_seed in train_seeds:
            d = run_dir(cfg, method, train_seed)
            if not (d / "done.json").exists():
                print(f"   [!] {paper_id} seed {train_seed}: belum ada hasil.")
                continue
            model = PPO.load(str(d / "model_best"), device="cpu")
            for noise_seed in seeds:
                # frame_stack=1: tumpukan dipasang SESUDAH VecNormalize yang
                # dimuat dari pkl, persis seperti urutan saat pelatihan.
                venv = make_vec_env(db, "test", cfg,
                                    observation_mode=spec["observation_mode"],
                                    train=False, seed=noise_seed, num_envs=1,
                                    subprocess=False, normalize=False,
                                    frame_stack=1,
                                    env_overrides={**spec["env_overrides"],
                                                   **(extra_overrides or {})})
                venv = VecNormalize.load(str(d / "vecnormalize_best.pkl"), venv)
                venv.training = False
                venv.norm_reward = False
                venv = VecFrameStack(
                    venv, n_stack=int(cfg["observation"]["frame_stack"]))
                eps = rollout_agent(model, venv, indices, noise_seed)
                rows += episode_rows(eps, paper_id, train_seed, noise_seed)
                venv.close()
            if verbose:
                print(f"   {paper_id} seed latih {train_seed}: selesai")
    return rows


# ------------------------------------------------------------------- utama
def main(argv=None) -> int:
    import pandas as pd

    from .metrics import episode_table, seed_means, summary_table, welch_ttest

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", default="base")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--n-boot", type=int, default=None)
    ap.add_argument("--skip-agents", action="store_true")
    args = ap.parse_args(argv)

    cfg = load_config(args.config)
    repo = Path(__file__).resolve().parents[3]
    chash = config_hash(cfg)
    db = database_path(cfg, channel_config_hash(cfg),
                       root=repo / cfg["paths"]["channel_db"])
    env_cfg = EnvConfig.from_config(cfg, "partial")
    out_dir = repo / "results" / "eval" / chash
    out_dir.mkdir(parents=True, exist_ok=True)

    store = TrajectoryStore(db, "test")
    indices = list(range(len(store)))
    seeds = noise_seeds(cfg, args.seed)
    train_seeds = list(range(int(cfg["training"]["num_seeds"])))
    n_boot = args.n_boot or int(cfg["evaluation"]["bootstrap_samples"])

    print(f"config hash : {chash}")
    print(f"set test    : {len(indices)} lintasan | seed derau {seeds}")
    print(f"P_max eval  : {cfg['radio']['p_max_dbm']} dBm")

    # ---- penyetelan B0/B1/B2 di VAL, lalu dibekukan (§6.2)
    print("\nSetel B0/B1/B2 di val (set test tidak disentuh)")
    tuned = tune_baselines(cfg, db, env_cfg, args.seed)

    print("\nBaseline di test")
    rows, oracle = run_baselines(cfg, db, env_cfg, indices, seeds, tuned)

    if not args.skip_agents:
        print("\nAgen di test")
        rows += run_agents(cfg, db, indices, seeds, train_seeds)

    steps = pd.DataFrame(rows)
    steps.to_parquet(out_dir / "steps.parquet", index=False)

    episodes = episode_table(steps, float(cfg["mobility"]["dt_s"]),
                             float(cfg["observation"]["target_pos_max_std_m"]),
                             float(cfg["sensing"]["scnr_threshold_db"]))
    episodes.to_parquet(out_dir / "episodes.parquet", index=False)

    t2 = summary_table(episodes, n_boot=n_boot, seed=args.seed)
    order = [m for m in METHOD_ORDER if m in t2.index]
    t2 = t2.loc[order]
    t2.to_csv(out_dir / "T2.csv")

    # ---- uji beda (§9). Pembandingnya mengikuti peran Fase 8: A1 adalah
    # metode utama, jadi ia diuji terhadap lantai tanpa RIS (B0), terhadap
    # baseline terapan (B2), terhadap oracle usang (B4), dan terhadap dirinya
    # sendiri ber-CSI-penuh (A1-FullCSI, ablasi observasi). M1 tetap diuji
    # supaya angka Fase 6 masih bisa dibandingkan baris per baris.
    tests = {}
    for column in ("reward_per_step", "min_rate", "scnr_compliance"):
        means = seed_means(episodes, column)
        for main in ("A1", "M1"):
            for other in ("B0", "B2", "B4-D5", "B4-D10", "A1-FullCSI"):
                if main in means and other in means and main != other:
                    tests[f"{column}|{main}_vs_{other}"] = welch_ttest(
                        means[main], means[other])
    meta = {
        "config": args.config, "config_hash": chash,
        "channel_config_hash": channel_config_hash(cfg),
        "git_commit": git_commit(), "split": "test",
        "trajectories": len(indices), "noise_seeds": seeds,
        "train_seeds": train_seeds,
        "episodes_per_seed": len(indices) * len(seeds),
        "p_max_eval_dbm": float(cfg["radio"]["p_max_dbm"]),
        "tuned_baselines": tuned,
        "oracle_clipped_fraction": oracle["clipped_fraction"],
        "oracle_snapshot_reward_per_step": oracle["oracle_reward_per_step"],
        "bootstrap_samples": n_boot,
        "tests": tests,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    (out_dir / "meta.json").write_text(
        json.dumps(meta, indent=2, default=str), encoding="utf-8")
    (out_dir / "config.yaml").write_text(
        (repo / "configs" / f"{args.config}.yaml").read_text(encoding="utf-8"),
        encoding="utf-8")

    print(f"\nT2 ({len(episodes)} episode total)")
    show = ["episodes", "reward_per_step", "min_rate", "scnr_compliance",
            "track_duration_s", "tracker_error_m"]
    with pd.option_context("display.width", 140,
                           "display.float_format", lambda v: f"{v:8.3f}"):
        print(t2[show].to_string())
    print(f"\nHasil: {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
