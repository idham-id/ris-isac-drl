"""Pelatihan PPO untuk M1/M2/A1 (docs/EXPERIMENT_DESIGN.md §6.1).

    python -m risisac.train.train --config base --method ppo_po --seed 0

Tiga metode hanya berbeda pada dua tombol, dan keduanya ditangani di sini
supaya satu file config tetap melayani ketiganya:

| ID | ``--method``       | observasi | fasa        |
|----|--------------------|-----------|-------------|
| M1 | ``ppo_po``         | parsial   | inkremental |
| M2 | ``ppo_full``       | penuh     | inkremental |
| A1 | ``ppo_po_absolute``| parsial   | absolut     |

Metode TIDAK diubah lewat dict config, melainkan lewat ``env_overrides``
(lihat ``env.vec.make_env_fn``). Alasannya praktis: kalau metode mengubah
config, ``config_hash`` ikut berubah dan hasil tiga metode dari satu config
akan tersebar ke tiga direktori yang tampak tidak berhubungan.

Setiap run menulis ke::

    results/train/<config_hash>/<method>/seed<k>/
        config.yaml           salinan config hasil resolusi
        meta.json             commit git, versi, waktu, hiperparameter efektif
        progress.csv, tb/     log SB3 (CSV + TensorBoard)
        eval_val.csv          evaluasi val tiap `training.eval_every_steps`
        checkpoints/          checkpoint + VecNormalize berkala
        model.zip, vecnormalize.pkl           kebijakan AKHIR
        model_best.zip, vecnormalize_best.pkl kebijakan terbaik di val
        done.json             penanda selesai; run yang sudah ada dilewati

Evaluasi val memakai env TERPISAH pada ``train=False`` (P_max tetap 30 dBm,
§8) dan kebijakan deterministik, dengan statistik ``VecNormalize`` disalin
dari env pelatihan. Tanpa penyalinan itu observasi val akan dinormalisasi
dengan statistik yang salah dan kurva pelatihan menjadi tidak bermakna.
"""

from __future__ import annotations

import argparse
import copy
import json
import shutil
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from ..channels.database import database_path
from ..config import (REPO_ROOT, channel_config_hash, config_hash, git_commit,
                      load_config)
from ..env import TrajectoryStore
from ..env.vec import make_vec_env
from ..eval.rollout import rollout_agent, summarise

#: ``--method`` -> (mode observasi, override EnvConfig). Kunci adalah ID paper.
METHODS: dict[str, dict] = {
    "ppo_po": {"paper_id": "M1", "observation_mode": "partial",
               "env_overrides": {"phase_update": "incremental"}},
    "ppo_full": {"paper_id": "M2", "observation_mode": "full",
                 "env_overrides": {"phase_update": "incremental"}},
    "ppo_po_absolute": {"paper_id": "A1", "observation_mode": "partial",
                        "env_overrides": {"phase_update": "absolute"}},
}


@dataclass
class RunSpec:
    """Satu run pelatihan."""

    config: str = "base"
    method: str = "ppo_po"
    seed: int = 0
    total_timesteps: int | None = None
    eval_every: int | None = None
    torch_threads: int = 1
    overwrite: bool = False
    extra: dict = field(default_factory=dict)


def run_dir(cfg: dict, method: str, seed: int, root: Path | None = None) -> Path:
    """``results/train/<config_hash>/<method>/seed<k>/``."""
    root = Path(root) if root is not None else REPO_ROOT / cfg["paths"]["results"]
    return root / "train" / config_hash(cfg) / str(method) / f"seed{int(seed)}"


# ---------------------------------------------------------------- evaluasi val
class ValEvaluator:
    """Evaluasi deterministik pada seluruh lintasan val.

    Env val dibuat sekali dan dipakai ulang: membangun ``TrajectoryStore``
    memuat seluruh split ke memori, dan melakukannya tiap 50 ribu langkah akan
    menambah biaya yang tidak perlu.
    """

    def __init__(self, db_path, cfg: dict, method: dict, seed: int):
        self.cfg = cfg
        self.store_size = len(TrajectoryStore(db_path, "val"))
        self.venv = make_vec_env(db_path, "val", cfg,
                                 observation_mode=method["observation_mode"],
                                 train=False, seed=seed + 1000, num_envs=1,
                                 subprocess=False,
                                 env_overrides=method["env_overrides"])
        self.vecnorm = _find_vecnormalize(self.venv)
        self.vecnorm.training = False
        self.vecnorm.norm_reward = False
        self.seed = int(seed) + 1000
        self.indices = list(range(self.store_size))

    def __call__(self, model, train_venv) -> dict:
        src = _find_vecnormalize(train_venv)
        # Salinan, bukan referensi: VecNormalize pelatihan terus berubah, dan
        # evaluasi harus memakai statistik pada saat evaluasi itu.
        self.vecnorm.obs_rms = copy.deepcopy(src.obs_rms)
        episodes = rollout_agent(model, self.venv, self.indices, self.seed)
        return summarise(episodes)

    def close(self) -> None:
        self.venv.close()


def _find_vecnormalize(venv):
    from stable_baselines3.common.vec_env import VecNormalize
    while venv is not None:
        if isinstance(venv, VecNormalize):
            return venv
        venv = getattr(venv, "venv", None)
    raise RuntimeError("VecNormalize tidak ditemukan di tumpukan pembungkus.")


def _make_callback(evaluator: "ValEvaluator", every: int, csv_path: Path,
                   train_venv, log_prefix: str = ""):
    from stable_baselines3.common.callbacks import BaseCallback

    class _ValEvalCallback(BaseCallback):
        """Evaluasi val tiap ``every`` langkah lingkungan, ditulis ke CSV."""

        def __init__(self):
            super().__init__()
            self.rows: list[dict] = []
            self._next = 0

        def _write(self, row: dict) -> None:
            # Evaluasi terakhir jatuh pada jumlah langkah yang sama dengan
            # evaluasi berkala terakhir, tetapi SESUDAH pembaruan kebijakan
            # terakhir PPO. Yang disimpan adalah yang sesudah: itulah model
            # yang ikut tersimpan ke model.zip.
            if self.rows and self.rows[-1]["timesteps"] == row["timesteps"]:
                self.rows[-1] = row
            else:
                self.rows.append(row)
            header = list(row)
            lines = [",".join(header)]
            lines += [",".join(f"{r[k]:.6g}" if isinstance(r[k], float)
                               else str(r[k]) for k in header)
                      for r in self.rows]
            csv_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

        def evaluate_now(self) -> dict:
            t0 = time.time()
            out = evaluator(self.model, train_venv)
            row = {"timesteps": int(self.num_timesteps), **out,
                   "eval_seconds": time.time() - t0}
            self._write(row)
            for key, value in out.items():
                if isinstance(value, float):
                    self.logger.record(f"val/{key}", value)
            print(f"{log_prefix}{self.num_timesteps:>9d} langkah | "
                  f"reward/langkah {out['reward_per_step']:+7.3f} | "
                  f"rate {out['min_rate']:6.3f} | "
                  f"deteksi {out['detection_rate']:5.3f} | "
                  f"galat tracker {out['tracker_error_m']:4.2f} m",
                  flush=True)
            return row

        def _on_training_start(self) -> None:
            # Titik awal (langkah 0) ikut direkam: tanpa itu kurva kehilangan
            # garis dasar kebijakan acak, yang justru pembanding termurahnya.
            self.evaluate_now()
            self._next = int(every)

        def _on_step(self) -> bool:
            if self.num_timesteps >= self._next:
                self.evaluate_now()
                self._next += int(every)
            return True

    return _ValEvalCallback()


# -------------------------------------------------------------------- training
def train_one(spec: RunSpec, cfg: dict | None = None,
              results_root: Path | None = None) -> dict:
    """Jalankan satu run; kembalikan ringkasannya."""
    import torch
    from stable_baselines3 import PPO
    from stable_baselines3.common.callbacks import CheckpointCallback
    from stable_baselines3.common.logger import configure

    if spec.method not in METHODS:
        raise ValueError(f"metode tidak dikenal: {spec.method!r} "
                         f"({', '.join(METHODS)})")
    method = METHODS[spec.method]
    cfg = cfg if cfg is not None else load_config(spec.config)
    out_dir = run_dir(cfg, spec.method, spec.seed, results_root)
    done_file = out_dir / "done.json"
    if done_file.exists() and not spec.overwrite:
        print(f"[lewati] {out_dir} sudah selesai.")
        return json.loads(done_file.read_text(encoding="utf-8"))

    torch.set_num_threads(int(spec.torch_threads))
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "config.yaml").write_text(
        yaml.safe_dump(cfg, sort_keys=False, allow_unicode=True),
        encoding="utf-8")

    db = database_path(cfg, channel_config_hash(cfg),
                       root=REPO_ROOT / cfg["paths"]["channel_db"])
    training, ppo_cfg = cfg["training"], cfg["training"]["ppo"]
    total = int(spec.total_timesteps or float(training["total_timesteps"]))
    every = int(spec.eval_every or training["eval_every_steps"])
    n_envs = int(training["n_envs"])

    train_venv = make_vec_env(db, "train", cfg,
                              observation_mode=method["observation_mode"],
                              train=True, seed=spec.seed,
                              env_overrides=method["env_overrides"])
    evaluator = ValEvaluator(db, cfg, method, spec.seed)

    prefix = f"[{method['paper_id']} {spec.method} seed {spec.seed}] "
    print(f"{prefix}config {config_hash(cfg)} | {total} langkah | "
          f"{n_envs} env | obs {train_venv.observation_space.shape[0]} | "
          f"aksi {train_venv.action_space.shape[0]} | "
          f"fasa {method['env_overrides']['phase_update']}", flush=True)

    model = PPO("MlpPolicy", train_venv, device=str(training["device"]),
                learning_rate=float(ppo_cfg["learning_rate"]),
                n_steps=int(ppo_cfg["n_steps"]),
                batch_size=int(ppo_cfg["batch_size"]),
                n_epochs=int(ppo_cfg["n_epochs"]),
                gamma=float(training["gamma"]),
                gae_lambda=float(ppo_cfg["gae_lambda"]),
                clip_range=float(ppo_cfg["clip_range"]),
                ent_coef=float(ppo_cfg["ent_coef"]),
                # target_kl menghentikan loop epoch PPO lebih awal begitu KL
                # perkiraan melewati ambang, yaitu membatasi BESAR langkah
                # kebijakan per pembaruan. Tidak ada di config base, sehingga
                # absennya berarti None dan perilaku base tidak berubah sama
                # sekali; hanya config yang menyebutkannya yang terpengaruh.
                target_kl=(float(ppo_cfg["target_kl"])
                           if ppo_cfg.get("target_kl") is not None else None),
                policy_kwargs={"net_arch": list(ppo_cfg["net_arch"])},
                seed=int(spec.seed), verbose=0)
    model.set_logger(configure(str(out_dir), ["csv", "tensorboard"]))

    eval_cb = _make_callback(evaluator, every, out_dir / "eval_val.csv",
                             train_venv, prefix)
    # save_vecnormalize: statistik observasi ikut disimpan tiap checkpoint.
    # Tanpa itu checkpoint tidak bisa dipakai ulang dengan benar -- obs_rms
    # terus berubah selama pelatihan, dan memuat kebijakan lama dengan
    # statistik akhir terukur memangkas reward val A1 dari +8,220 ke +7,180
    # (docs/LOG.md 2026-11-11 (k)).
    ckpt_cb = CheckpointCallback(save_freq=max(every // n_envs, 1),
                                 save_path=str(out_dir / "checkpoints"),
                                 name_prefix="ppo", save_vecnormalize=True,
                                 verbose=0)

    t0 = time.time()
    model.learn(total_timesteps=total, callback=[eval_cb, ckpt_cb],
                progress_bar=False)
    train_seconds = time.time() - t0
    final = eval_cb.evaluate_now()      # evaluasi pada langkah terakhir

    model.save(out_dir / "model")
    _find_vecnormalize(train_venv).save(str(out_dir / "vecnormalize.pkl"))
    best = select_best(eval_cb.rows, out_dir, total)
    print(f"{prefix}model terbaik di val: {best['reward_per_step']:+.3f} "
          f"pada {best['timesteps']} langkah "
          f"(akhir {final['reward_per_step']:+.3f})", flush=True)

    summary = {
        "method": spec.method, "paper_id": method["paper_id"],
        "seed": int(spec.seed), "config": str(spec.config),
        "config_hash": config_hash(cfg),
        "channel_config_hash": channel_config_hash(cfg),
        "git_commit": git_commit(),
        "total_timesteps": total, "eval_every_steps": every,
        "n_envs": n_envs, "device": str(training["device"]),
        "torch_threads": int(spec.torch_threads),
        "train_seconds": train_seconds,
        "steps_per_second": total / train_seconds,
        "observation_mode": method["observation_mode"],
        "phase_update": method["env_overrides"]["phase_update"],
        "observation_dim": int(train_venv.observation_space.shape[0]),
        "action_dim": int(train_venv.action_space.shape[0]),
        "final_val": final,
        "best_val": best,
        "best_timesteps": int(best["timesteps"]),
        "python": sys.version.split()[0],
        "torch": torch.__version__,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    (out_dir / "meta.json").write_text(json.dumps(summary, indent=2, default=str),
                                       encoding="utf-8")
    done_file.write_text(json.dumps(summary, indent=2, default=str),
                         encoding="utf-8")

    evaluator.close()
    train_venv.close()
    print(f"{prefix}selesai dalam {train_seconds / 60:.1f} menit "
          f"({total / train_seconds:.0f} langkah/detik) -> {out_dir}", flush=True)
    return summary


def select_best(rows: list[dict], out_dir: Path, total: int) -> dict:
    """Salin checkpoint dengan reward val terbaik ke ``model_best.zip``.

    Pemilihan model pada split val adalah praktik baku dan §6.1 memang
    menyediakan val untuk itu ("tuning ringan hanya di val, lalu dibekukan").
    Di sini ia bukan kemewahan: ketiga seed A1 mencapai puncaknya di 350-450
    ribu langkah lalu **ambruk** -- deteksi 0,95 -> 0,55 tanpa kehilangan rate
    sedikit pun, jadi kebijakan akhir memang lebih buruk, bukan hasil
    tukar-tambah (docs/LOG.md 2026-11-11 (k)).

    Baris pada ``timesteps == total`` adalah evaluasi SESUDAH pembaruan
    terakhir PPO, yang modelnya ada di ``model.zip`` -- bukan checkpoint
    bernama sama, yang disimpan sebelum pembaruan itu. Baris langkah 0
    dikecualikan: ia garis dasar kebijakan acak dan tidak punya checkpoint.
    """
    usable = [r for r in rows if r["timesteps"] > 0]
    best = max(usable, key=lambda r: r["reward_per_step"])
    steps = int(best["timesteps"])
    if steps >= int(total):
        src_model = out_dir / "model.zip"
        src_norm = out_dir / "vecnormalize.pkl"
    else:
        ckpt = out_dir / "checkpoints"
        src_model = ckpt / f"ppo_{steps}_steps.zip"
        src_norm = ckpt / f"ppo_vecnormalize_{steps}_steps.pkl"
    if not src_model.exists() or not src_norm.exists():
        raise FileNotFoundError(
            f"checkpoint {steps} tidak lengkap: {src_model}, {src_norm}")
    shutil.copy2(src_model, out_dir / "model_best.zip")
    shutil.copy2(src_norm, out_dir / "vecnormalize_best.pkl")
    return best


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", default="base")
    ap.add_argument("--method", default="ppo_po", choices=sorted(METHODS))
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--steps", type=int, default=None,
                    help="default: training.total_timesteps dari config")
    ap.add_argument("--eval-every", type=int, default=None)
    ap.add_argument("--torch-threads", type=int, default=1,
                    help="1 supaya beberapa run paralel tidak berebut core")
    ap.add_argument("--overwrite", action="store_true",
                    help="latih ulang walau done.json sudah ada")
    args = ap.parse_args(argv)

    spec = RunSpec(config=args.config, method=args.method, seed=args.seed,
                   total_timesteps=args.steps, eval_every=args.eval_every,
                   torch_threads=args.torch_threads, overwrite=args.overwrite)
    summary = train_one(spec)
    print(json.dumps({k: v for k, v in summary.items()
                      if k != "final_val"}, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
