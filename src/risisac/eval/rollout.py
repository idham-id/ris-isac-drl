"""Menjalankan satu kebijakan pada satu split dan meringkasnya.

Semua metode -- agen SB3, B1, B2, dan nanti B3/B4 -- dijalankan lewat fungsi
di modul ini supaya angkanya benar-benar sebanding: lintasan yang sama, seed
yang sama, agregasi yang sama. Agen berjalan melalui tumpukan ``VecNormalize``
+ ``VecFrameStack`` (ia membutuhkan statistik observasi dan tumpukan frame),
baseline berjalan pada env mentah (ia tidak membaca observasi sama sekali);
keduanya menghasilkan rekaman per langkah dengan bentuk yang sama.

**Reward per LANGKAH yang dibandingkan, bukan per episode.** Episode berakhir
saat target meninggalkan ROI, jadi panjangnya berbeda antar-lintasan: pada set
test 18 sampai 50 langkah (rata-rata 36,9). Panjang itu ditentukan lintasan, bukan keputusan, sehingga
semua metode berjalan pada langkah yang sama persis. Yang tetap bermasalah
adalah **rata-rata reward per episode**: ia memberi bobot sama kepada episode
11 langkah dan episode 50 langkah, sehingga nilainya ikut bergeser bila
komposisi panjang lintasan berubah. Reward per langkah tidak punya masalah itu
dan menjawab pertanyaan yang dimaksud: seberapa baik satu keputusan.
"""

from __future__ import annotations

import numpy as np

#: Kunci ``info`` yang direkam tiap langkah.
STEP_FIELDS = ("min_rate", "scnr_db", "detected", "tracker_error_m", "rho",
               "total_power", "p_max_watt")


def summarise(episodes: list[dict]) -> dict:
    """Ringkas daftar episode menjadi metrik yang dilaporkan paper (§7 E3)."""
    rewards = np.array([float(np.sum(ep["reward"])) for ep in episodes])
    steps = np.array([len(ep["reward"]) for ep in episodes], dtype=float)
    flat = {k: np.concatenate([np.asarray(ep[k], dtype=float)
                               for ep in episodes]) for k in STEP_FIELDS}
    return {
        "episodes": int(len(episodes)),
        "episode_reward": float(np.mean(rewards)),
        "reward_per_step": float(np.sum(rewards) / np.sum(steps)),
        "episode_steps": float(np.mean(steps)),
        "min_rate": float(np.mean(flat["min_rate"])),
        "min_rate_p10": float(np.percentile(flat["min_rate"], 10)),
        "scnr_median_db": float(np.median(flat["scnr_db"])),
        "scnr_p10_db": float(np.percentile(flat["scnr_db"], 10)),
        # Pemenuhan SCNR = fraksi LANGKAH dengan SCNR >= Gamma (§7 E3).
        "detection_rate": float(np.mean(flat["detected"])),
        "tracker_error_m": float(np.mean(flat["tracker_error_m"])),
        "tracker_error_p90_m": float(np.percentile(flat["tracker_error_m"], 90)),
        "rho_mean": float(np.mean(flat["rho"])),
        "max_power_excess": float(np.max(flat["total_power"]
                                         - flat["p_max_watt"])),
    }


def _record(info: dict, reward: float, store: dict) -> None:
    store["reward"].append(float(reward))
    for key in STEP_FIELDS:
        store[key].append(float(info[key]))


def _empty() -> dict:
    return {"reward": [], **{k: [] for k in STEP_FIELDS}}


def rollout_baseline(env, policy, indices, seed: int) -> list[dict]:
    """Jalankan B1/B2 pada env mentah, satu episode per indeks lintasan."""
    episodes = []
    for index in indices:
        env.reset(seed=int(seed) + int(index),
                  options={"trajectory_index": int(index)})
        policy.reset(env)
        ep = _empty()
        while True:
            _, reward, terminated, truncated, info = env.step(policy.act(env))
            _record(info, reward, ep)
            if terminated or truncated:
                break
        ep["trajectory_index"] = int(index)
        episodes.append(ep)
    return episodes


def rollout_agent(model, venv, indices, seed: int,
                  deterministic: bool = True) -> list[dict]:
    """Jalankan agen SB3 pada ``venv`` berjumlah SATU env (``num_envs == 1``).

    ``venv`` harus sudah memuat statistik ``VecNormalize`` yang dipakai saat
    pelatihan dan berada pada ``training=False``; kalau tidak, observasi
    dinormalisasi dengan statistik yang salah dan angkanya tidak bermakna.
    """
    episodes = []
    for index in indices:
        venv.seed(int(seed) + int(index))
        venv.set_options([{"trajectory_index": int(index)}])
        obs = venv.reset()
        ep = _empty()
        while True:
            action, _ = model.predict(obs, deterministic=deterministic)
            obs, reward, done, infos = venv.step(action)
            _record(infos[0], float(reward[0]), ep)
            if bool(done[0]):
                break
        ep["trajectory_index"] = int(index)
        episodes.append(ep)
    return episodes
