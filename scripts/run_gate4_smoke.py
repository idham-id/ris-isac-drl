"""Gate 4 - uji asap environment RL (docs/TASKS.md Fase 4).

    python scripts/run_gate4_smoke.py --config base --steps 300000

Melatih PPO-PO sebentar lalu membandingkannya dengan B1 di split **val**:

**Gate 4:** semua tes lulus; uji asap lolos (PPO-PO mengalahkan B1 di val);
laju >= 1.000 langkah/detik per proses.

B1 dievaluasi lewat environment yang sama dengan mode fasa **absolut**, karena
§6.2 mendefinisikannya sebagai "fasa acak per langkah" -- yang tidak bisa
dihasilkan aksi inkremental. Keduanya dinilai pada lintasan val yang sama
dengan seed yang sama, sehingga selisihnya adalah selisih kebijakan.

Keluar 0 bila uji asap lolos, 1 bila tidak.
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

from risisac.channels.database import database_path                  # noqa: E402
from risisac.config import (channel_config_hash, config_hash,        # noqa: E402
                            load_config)
from risisac.env import EnvConfig, RisIsacEnv, TrajectoryStore       # noqa: E402
from risisac.env.vec import make_vec_env                             # noqa: E402


def find_vecnormalize(venv):
    """Cari lapisan VecNormalize di dalam tumpukan pembungkus."""
    from stable_baselines3.common.vec_env import VecNormalize
    while venv is not None:
        if isinstance(venv, VecNormalize):
            return venv
        venv = getattr(venv, "venv", None)
    return None


def evaluate_policy(model, venv, store_size: int, seed: int) -> dict:
    """Jalankan kebijakan deterministik pada tiap lintasan val satu kali."""
    rewards, rates, scnr, detections, steps, rhos = [], [], [], [], [], []
    for index in range(store_size):
        venv.seed(seed + index)
        venv.set_options([{"trajectory_index": index}])
        obs = venv.reset()
        total, n = 0.0, 0
        ep_rate, ep_scnr, ep_det, ep_rho = [], [], [], []
        while True:
            action, _ = model.predict(obs, deterministic=True)
            obs, reward, done, infos = venv.step(action)
            info = infos[0]
            total += float(reward[0])
            n += 1
            ep_rate.append(info["min_rate"])
            ep_scnr.append(info["scnr_db"])
            ep_det.append(float(info["detected"]))
            ep_rho.append(float(info["rho"]))
            if done[0]:
                break
        rewards.append(total)
        steps.append(n)
        rates.append(float(np.mean(ep_rate)))
        scnr.append(float(np.median(ep_scnr)))
        detections.append(float(np.mean(ep_det)))
        rhos.append(float(np.mean(ep_rho)))
    return {"episode_reward": float(np.mean(rewards)),
            "reward_per_step": float(np.sum(rewards) / np.sum(steps)),
            "min_rate": float(np.mean(rates)),
            "scnr_median_db": float(np.median(scnr)),
            "detection_rate": float(np.mean(detections)),
            "episode_steps": float(np.mean(steps)),
            "rho_mean": float(np.mean(rhos))}


def evaluate_random(cfg, store, seed: int, sensing_fraction: float) -> dict:
    """B1: fasa acak per langkah (mode absolut), rho dari grid val Gate 3."""
    env_cfg = dataclasses.replace(EnvConfig.from_config(cfg, "partial"),
                                  phase_update="absolute")
    env = RisIsacEnv(store, env_cfg, train=False, seed=seed)
    m, k = env_cfg.num_elements, env_cfg.num_users
    rho_raw = 2.0 * float(sensing_fraction) - 1.0
    rng = np.random.default_rng(seed)
    rewards, rates, scnr, detections, steps, rhos = [], [], [], [], [], []
    for index in range(len(store)):
        env.reset(seed=seed + index, options={"trajectory_index": index})
        total, n = 0.0, 0
        ep_rate, ep_scnr, ep_det, ep_rho = [], [], [], []
        while True:
            action = np.concatenate([rng.uniform(-1, 1, m), [rho_raw],
                                     np.zeros(k)])
            _, reward, _, trunc, info = env.step(action)
            total += reward
            n += 1
            ep_rate.append(info["min_rate"])
            ep_scnr.append(info["scnr_db"])
            ep_det.append(float(info["detected"]))
            ep_rho.append(float(info["rho"]))
            if trunc:
                break
        rewards.append(total)
        steps.append(n)
        rates.append(float(np.mean(ep_rate)))
        scnr.append(float(np.median(ep_scnr)))
        detections.append(float(np.mean(ep_det)))
        rhos.append(float(np.mean(ep_rho)))
    return {"episode_reward": float(np.mean(rewards)),
            "reward_per_step": float(np.sum(rewards) / np.sum(steps)),
            "min_rate": float(np.mean(rates)),
            "scnr_median_db": float(np.median(scnr)),
            "detection_rate": float(np.mean(detections)),
            "episode_steps": float(np.mean(steps)),
            "rho_mean": float(np.mean(rhos))}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", default="base")
    ap.add_argument("--steps", type=int, default=300_000)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--b1-rho", type=float, default=None,
                    help="rho B1; default dari hasil Gate 3 bila ada")
    args = ap.parse_args()

    from stable_baselines3 import PPO

    cfg = load_config(args.config)
    repo = Path(__file__).resolve().parents[1]
    db = database_path(cfg, channel_config_hash(cfg),
                       root=repo / cfg["paths"]["channel_db"])
    out_dir = repo / "results" / "gate4" / config_hash(cfg)
    out_dir.mkdir(parents=True, exist_ok=True)

    ppo = cfg["training"]["ppo"]
    print(f"config hash : {config_hash(cfg)}")
    print(f"basis data  : {db}")
    print(f"PPO-PO      : {args.steps} langkah | {cfg['training']['n_envs']} env "
          f"| device {cfg['training']['device']} | net {ppo['net_arch']}")

    train_venv = make_vec_env(db, "train", cfg, observation_mode="partial",
                              train=True, seed=args.seed)
    print(f"observasi   : {train_venv.observation_space.shape[0]} "
          f"(174 x frame_stack {cfg['observation']['frame_stack']})")

    model = PPO("MlpPolicy", train_venv, device=str(cfg["training"]["device"]),
                learning_rate=float(ppo["learning_rate"]),
                n_steps=int(ppo["n_steps"]), batch_size=int(ppo["batch_size"]),
                n_epochs=int(ppo["n_epochs"]), gamma=float(cfg["training"]["gamma"]),
                gae_lambda=float(ppo["gae_lambda"]),
                clip_range=float(ppo["clip_range"]),
                ent_coef=float(ppo["ent_coef"]),
                policy_kwargs={"net_arch": list(ppo["net_arch"])},
                seed=args.seed, verbose=0)

    t0 = time.time()
    model.learn(total_timesteps=int(args.steps), progress_bar=False)
    train_time = time.time() - t0
    print(f"pelatihan   : {train_time:.1f}s "
          f"({args.steps / train_time:.0f} langkah/detik)")

    store = TrajectoryStore(db, "val")
    eval_venv = make_vec_env(db, "val", cfg, observation_mode="partial",
                             train=False, seed=args.seed + 1000, num_envs=1,
                             subprocess=False)
    src, dst = find_vecnormalize(train_venv), find_vecnormalize(eval_venv)
    dst.obs_rms = src.obs_rms
    dst.training = False
    dst.norm_reward = False

    t0 = time.time()
    ppo_out = evaluate_policy(model, eval_venv, len(store), args.seed + 1000)
    b1_rho = args.b1_rho
    if b1_rho is None:
        gate3 = repo / "results" / "gate3"
        found = sorted(gate3.glob("*/gate3.json"), key=lambda p: p.stat().st_mtime)
        b1_rho = (json.loads(found[-1].read_text(encoding="utf-8"))
                  ["b1_tuning"]["best_rho"]) if found else 0.3
    b1_out = evaluate_random(cfg, store, args.seed + 1000, b1_rho)
    print(f"evaluasi    : {time.time() - t0:.1f}s | B1 memakai rho {b1_rho:.2f}")

    print(f"\nEvaluasi val ({len(store)} lintasan)")
    print(f"   {'metode':<10s} {'reward/ep':>10s} {'reward/lgkh':>12s} "
          f"{'min rate':>9s} {'SCNR med':>9s} {'deteksi':>8s} {'rho':>6s}")
    for name, out in (("B1 random", b1_out), ("PPO-PO", ppo_out)):
        print(f"   {name:<10s} {out['episode_reward']:10.3f} "
              f"{out['reward_per_step']:12.3f} {out['min_rate']:9.3f} "
              f"{out['scnr_median_db']:9.1f} {out['detection_rate']:8.3f} "
              f"{out['rho_mean']:6.3f}")

    # Episode berbeda panjang antar-lintasan, jadi reward PER LANGKAH yang
    # dibandingkan: reward per episode akan mengunggulkan metode yang kebetulan
    # bertahan lebih lama, padahal panjang episode ditentukan lintasan.
    beats = ppo_out["reward_per_step"] > b1_out["reward_per_step"]
    print(f"\nGate 4 (uji asap)\n-----------------")
    print(f"  [{'PASS' if beats else 'FAIL'}] ppo_beats_random: "
          f"{ppo_out['reward_per_step']:.3f} lawan {b1_out['reward_per_step']:.3f}")
    print(f"\nUJI ASAP: {'LOLOS' if beats else 'GAGAL'}")

    (out_dir / "gate4_smoke.json").write_text(json.dumps(
        {"config_hash": config_hash(cfg), "steps": int(args.steps),
         "train_seconds": train_time, "b1_rho": float(b1_rho),
         "ppo": ppo_out, "b1": b1_out, "passed": bool(beats)},
        indent=2, default=str), encoding="utf-8")
    model.save(out_dir / "ppo_smoke")
    src.save(str(out_dir / "vecnormalize_smoke.pkl"))
    train_venv.close()
    eval_venv.close()
    print(f"\nHasil: {out_dir}")
    return 0 if beats else 1


if __name__ == "__main__":
    raise SystemExit(main())
