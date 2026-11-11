"""Pembungkus vektor untuk pelatihan (docs/TASKS.md Fase 4).

    SubprocVecEnv(8)  ->  VecNormalize(observasi saja)  ->  VecFrameStack(4)

Tiga keputusan yang disengaja:

* **Reward TIDAK dinormalisasi.** Desain menyebutkannya eksplisit: reward (E9)
  bersatuan bit/s/Hz dikurangi hukuman hinge, sehingga bisa ditafsirkan
  langsung dan dibandingkan dengan baseline. Menormalkannya akan membuat
  kurva pelatihan tidak sebanding dengan tabel hasil.
* **Normalisasi sebelum penumpukan frame.** VecNormalize kemudian menghitung
  statistik atas 174 fitur satu frame, bukan atas 696 salinan yang berkorelasi;
  statistik yang disimpan pun tetap berukuran satu frame.
* **Store dimuat di dalam proses pekerja.** ``TrajectoryStore`` memuat seluruh
  lintasan ke memori; membuatnya di proses induk lalu mem-pickle-nya ke 8
  pekerja akan menyalin data itu delapan kali lewat pipe.
"""

from __future__ import annotations

from pathlib import Path

from .ris_isac_env import EnvConfig, RisIsacEnv, TrajectoryStore


def make_env_fn(db_path: str | Path, split: str, cfg: dict,
                observation_mode: str | None = None, train: bool = True,
                seed: int = 0, rank: int = 0):
    """Pabrik env untuk satu pekerja; store dimuat di dalam pekerja."""
    db_path, split = str(db_path), str(split)

    def _init():
        store = TrajectoryStore(db_path, split)
        env_cfg = EnvConfig.from_config(cfg, observation_mode)
        return RisIsacEnv(store, env_cfg, train=train, seed=seed + rank)

    return _init


def make_vec_env(db_path: str | Path, split: str, cfg: dict,
                 observation_mode: str | None = None, train: bool = True,
                 seed: int = 0, num_envs: int | None = None,
                 frame_stack: int | None = None, subprocess: bool = True,
                 normalize: bool = True):
    """VecEnv siap latih sesuai §6.1.

    :param subprocess: ``False`` memakai ``DummyVecEnv`` (satu proses), yang
        jauh lebih cepat untuk tes dan evaluasi kecil karena tidak membayar
        ongkos pembuatan proses.
    :param normalize: ``False`` melewati ``VecNormalize``; dipakai saat
        mengevaluasi baseline yang tidak membutuhkan statistik observasi.
    """
    from stable_baselines3.common.vec_env import (DummyVecEnv, SubprocVecEnv,
                                                  VecFrameStack, VecNormalize)

    n = int(num_envs if num_envs is not None else cfg["training"]["n_envs"])
    stack = int(frame_stack if frame_stack is not None
                else cfg["observation"]["frame_stack"])
    fns = [make_env_fn(db_path, split, cfg, observation_mode, train, seed, i)
           for i in range(n)]
    venv = SubprocVecEnv(fns) if (subprocess and n > 1) else DummyVecEnv(fns)
    if normalize:
        venv = VecNormalize(venv, norm_obs=True, norm_reward=False,
                            clip_obs=10.0)
    if stack > 1:
        venv = VecFrameStack(venv, n_stack=stack)
    return venv
