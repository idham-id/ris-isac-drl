"""Metrik set test dan protokol statistik (docs/EXPERIMENT_DESIGN.md §7 E3, §9).

Masukan modul ini selalu berbentuk **tabel per langkah** (satu baris = satu
langkah satu episode) dengan kolom ``train_seed``, ``noise_seed``,
``trajectory_index``, ``step``, dan besaran per langkah. Semua agregasi
dilakukan di sini dan hanya di sini, supaya angka tabel, gambar, dan uji
statistik tidak pernah dihitung dua kali dengan cara berbeda.

Dua definisi dibuat eksplisit di sini karena §7 menyebut namanya tanpa
rumusnya:

**Pemenuhan SCNR** = fraksi LANGKAH dengan SCNR >= Gamma, bukan fraksi
episode. Episode punya panjang berbeda (18-50 langkah di set test), jadi
fraksi episode akan memberi bobot berlebih kepada episode pendek.

**Durasi track** = waktu sampai track hilang, yaitu jumlah langkah BERURUTAN
sejak awal episode dengan galat tracker <= sigma_max, dikali Delta t. Ambang
sigma_max (5 m) adalah ``observation.target_pos_max_std_m`` di config, yang
sudah dipakai §5.2 sebagai batas atas simpangan pengukuran: di atas itu
pengukuran dianggap tidak informatif, jadi memakainya juga sebagai batas
"track masih hidup" tidak memasukkan angka baru ke dalam kode. Episode yang
tidak pernah melewati ambang mendapat durasi penuh, sehingga metrik ini
**tersensor di atas** oleh panjang episode -- dilaporkan apa adanya, bersama
fraksi episode yang tersensor.
"""

from __future__ import annotations

import numpy as np

#: Kolom per langkah yang wajib ada di tabel hasil.
REQUIRED = ("method", "train_seed", "noise_seed", "trajectory_index", "step",
            "reward", "min_rate", "scnr_db", "detected", "tracker_error_m",
            "rho", "total_power", "p_max_watt")

#: Kunci episode: satu episode = satu (seed latih, seed derau, lintasan).
EPISODE_KEYS = ["train_seed", "noise_seed", "trajectory_index"]


def track_duration(error_m, dt_s: float, sigma_max_m: float) -> tuple[float, bool]:
    """Durasi track satu episode dan apakah ia tersensor (tidak pernah hilang).

    :param error_m: galat posisi tracker per langkah, urut waktu.
    :returns: ``(durasi_detik, tersensor)``.
    """
    err = np.asarray(error_m, dtype=float)
    lost = np.flatnonzero(err > float(sigma_max_m))
    if lost.size == 0:
        return float(len(err)) * float(dt_s), True
    return float(lost[0]) * float(dt_s), False


def episode_table(steps, dt_s: float, sigma_max_m: float,
                  scnr_threshold_db: float):
    """Ringkas tabel per langkah menjadi satu baris per episode."""
    import pandas as pd

    rows = []
    for key, g in steps.groupby(["method"] + EPISODE_KEYS, sort=True):
        g = g.sort_values("step")
        duration, censored = track_duration(g["tracker_error_m"], dt_s,
                                            sigma_max_m)
        rows.append({
            "method": key[0], "train_seed": key[1], "noise_seed": key[2],
            "trajectory_index": key[3],
            "steps": int(len(g)),
            "reward_sum": float(g["reward"].sum()),
            "reward_per_step": float(g["reward"].mean()),
            "min_rate": float(g["min_rate"].mean()),
            "min_rate_worst": float(g["min_rate"].min()),
            "scnr_compliance": float((g["scnr_db"]
                                      >= scnr_threshold_db).mean()),
            "scnr_median_db": float(g["scnr_db"].median()),
            "track_duration_s": duration,
            "track_censored": bool(censored),
            "tracker_error_m": float(g["tracker_error_m"].mean()),
            "rho": float(g["rho"].mean()),
        })
    return pd.DataFrame(rows)


# ------------------------------------------------------------------ bootstrap
def cluster_bootstrap(values, seeds, statistic=np.mean, n_boot: int = 10000,
                      alpha: float = 0.05, seed: int = 0) -> dict:
    """Rata-rata dan CI 95% dengan bootstrap episode **dikelompokkan per seed**.

    §9 meminta "bootstrap atas episode, dikelompokkan per seed". Episode dalam
    satu seed latih tidak saling bebas -- semuanya keluaran satu kebijakan --
    jadi mengacak seluruh episode sebagai satu kolam akan membuat CI terlalu
    sempit. Di sini tiap ulangan mengambil ulang episode **di dalam** tiap
    seed, menghitung statistik per seed, lalu merata-ratakan antar-seed.
    """
    values = np.asarray(values, dtype=float)
    seeds = np.asarray(seeds)
    groups = [values[seeds == s] for s in np.unique(seeds)]
    rng = np.random.default_rng(int(seed))
    draws = np.empty(int(n_boot), dtype=float)
    for b in range(int(n_boot)):
        per_seed = [statistic(g[rng.integers(0, len(g), len(g))])
                    for g in groups if len(g)]
        draws[b] = float(np.mean(per_seed))
    lo, hi = np.quantile(draws, [alpha / 2.0, 1.0 - alpha / 2.0])
    point = float(np.mean([statistic(g) for g in groups if len(g)]))
    return {"mean": point, "ci_low": float(lo), "ci_high": float(hi),
            "n_seeds": int(len(groups)), "n_episodes": int(len(values))}


def welch_ttest(a, b) -> dict:
    """Welch t-test dua sampel plus Cohen's d atas **rata-rata per seed** (§9).

    Masukannya rata-rata per seed (n = 3), bukan episode: episode dalam satu
    seed tidak saling bebas. Dengan n = 3 daya ujinya kecil; itu dinyatakan di
    paper, bukan disembunyikan.
    """
    from scipy import stats

    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    res = stats.ttest_ind(a, b, equal_var=False)
    pooled = np.sqrt((np.var(a, ddof=1) + np.var(b, ddof=1)) / 2.0) \
        if len(a) > 1 and len(b) > 1 else np.nan
    d = (np.mean(a) - np.mean(b)) / pooled if pooled and np.isfinite(pooled) \
        and pooled > 0 else np.nan
    return {"mean_a": float(np.mean(a)), "mean_b": float(np.mean(b)),
            "diff": float(np.mean(a) - np.mean(b)),
            "t": float(res.statistic), "p": float(res.pvalue),
            "df": float(getattr(res, "df", np.nan)),
            "cohen_d": float(d), "n_a": int(len(a)), "n_b": int(len(b))}


# ----------------------------------------------------------------- tabel T2
#: Kolom T2 dan arah "lebih baik": +1 besar lebih baik, -1 kecil lebih baik.
T2_COLUMNS = {
    "reward_per_step": +1,
    "min_rate": +1,
    "scnr_compliance": +1,
    "track_duration_s": +1,
    "tracker_error_m": -1,
}


def summary_table(episodes, n_boot: int = 10000, seed: int = 0):
    """T2 -- rata-rata dan CI 95% tiap metrik untuk tiap metode."""
    import pandas as pd

    rows = []
    for method, g in episodes.groupby("method", sort=True):
        row = {"method": method, "episodes": int(len(g)),
               "seeds": int(g["train_seed"].nunique()),
               "track_censored": float(g["track_censored"].mean())}
        for column in T2_COLUMNS:
            out = cluster_bootstrap(g[column].to_numpy(),
                                    g["train_seed"].to_numpy(),
                                    n_boot=n_boot, seed=seed)
            row[column] = out["mean"]
            row[f"{column}_lo"] = out["ci_low"]
            row[f"{column}_hi"] = out["ci_high"]
        rows.append(row)
    return pd.DataFrame(rows).set_index("method")


# --------------------------------------------------------------- tabel T5
#: Kolom T5 dan arah "lebih baik": +1 besar lebih baik, -1 kecil lebih baik.
#: Dipakai hanya untuk dokumentasi dan pemeriksaan, bukan untuk mewarnai.
T5_COLUMNS = {
    "rho_mean": 0, "rho_p95": 0,
    "scnr_median_db": +1, "scnr_p5_db": +1,
    "min_rate_p5": +1, "min_rate_p10": +1, "min_rate_p50": +1,
    "violation_fraction": -1, "mean_shortfall_db": -1,
}


def behaviour_table(steps, scnr_threshold_db: float, order=None):
    """T5 -- perilaku per LANGKAH tiap metode (Fase 10).

    Semuanya dihitung dari ``steps.parquet`` yang sudah ada; tidak ada rollout
    baru. Dipakai persentil langkah, bukan rata-rata episode, dengan alasan
    yang sama seperti F5: yang membedakan metode di sini justru ekornya.

    * ``rho_mean``/``rho_p95`` -- pangsa daya sensing yang benar-benar dipakai.
    * ``scnr_median_db``/``scnr_p5_db`` -- pusat dan ekor bawah SCNR.
    * ``min_rate_p5``/``p10``/``p50`` -- ekor bawah rate minimum.
    * ``violation_fraction`` -- fraksi langkah dengan SCNR < Gamma, yaitu
      1 - pemenuhan SCNR di T2, dihitung ulang di sini supaya T5 bisa dibaca
      sendiri.
    * ``mean_shortfall_db`` -- rata-rata ``Gamma - SCNR`` HANYA atas langkah
      yang melanggar. Ia menjawab pertanyaan yang tidak dijawab fraksinya:
      seberapa dalam pelanggarannya ketika terjadi. Metode yang tidak pernah
      melanggar mendapat NaN, bukan 0 -- nol akan terbaca sebagai "melanggar
      tepat di ambang".
    """
    import pandas as pd

    gamma = float(scnr_threshold_db)
    rows = []
    for method, g in steps.groupby("method", sort=True):
        violating = g["scnr_db"].to_numpy() < gamma
        shortfall = gamma - g["scnr_db"].to_numpy()[violating]
        rows.append({
            "method": method,
            "steps": int(len(g)),
            "rho_mean": float(g["rho"].mean()),
            "rho_p95": float(np.percentile(g["rho"], 95)),
            "scnr_median_db": float(np.median(g["scnr_db"])),
            "scnr_p5_db": float(np.percentile(g["scnr_db"], 5)),
            "min_rate_p5": float(np.percentile(g["min_rate"], 5)),
            "min_rate_p10": float(np.percentile(g["min_rate"], 10)),
            "min_rate_p50": float(np.percentile(g["min_rate"], 50)),
            "violation_fraction": float(violating.mean()),
            "mean_shortfall_db": (float(shortfall.mean()) if violating.any()
                                  else float("nan")),
        })
    table = pd.DataFrame(rows).set_index("method")
    if order:
        keep = [m for m in order if m in table.index]
        table = table.loc[keep + sorted(set(table.index) - set(keep))]
    return table


#: Pasangan tambahan yang diuji di Fase 10, melengkapi ``evaluate.py``:
#: A1 lawan baseline terapan (B2), lawan ablasi parameterisasi fasa (M1), dan
#: lawan acuan atas (B3). A1-B2 memang sudah ada di ``meta.json``; ia dihitung
#: ulang di sini supaya T5 bisa dibaca tanpa membuka file lain, dan nilainya
#: harus sama -- masukannya sama persis.
T5_TEST_PAIRS = (("A1", "B2"), ("A1", "M1"), ("A1", "B3"))
T5_TEST_COLUMNS = ("reward_per_step", "min_rate", "scnr_compliance")


def pairwise_tests(episodes, pairs=T5_TEST_PAIRS,
                   columns=T5_TEST_COLUMNS) -> dict:
    """Welch t-test atas rata-rata per seed untuk tiap pasangan dan kolom.

    Kunci keluarannya memakai konvensi yang sama dengan ``meta.json`` yang
    ditulis ``evaluate.py`` (``"{kolom}|{a}_vs_{b}"``), supaya kedua file bisa
    dibandingkan baris per baris tanpa penerjemahan.
    """
    out = {}
    for column in columns:
        means = seed_means(episodes, column)
        for a, b in pairs:
            if a in means and b in means:
                out[f"{column}|{a}_vs_{b}"] = welch_ttest(means[a], means[b])
    return out


def seed_means(episodes, column: str) -> dict:
    """Rata-rata ``column`` per seed latih, per metode -- masukan Welch t-test."""
    out = {}
    for method, g in episodes.groupby("method", sort=True):
        by_seed = g.groupby("train_seed")[column].mean()
        out[method] = by_seed.to_numpy()
    return out


def episode_length_stats(episodes) -> dict:
    """Panjang episode di set test: rata-rata, minimum, maksimum (Fase 10).

    Panjangnya TIDAK bergantung pada metode maupun seed: episode berakhir saat
    target meninggalkan ROI, dan itu sifat lintasannya, bukan sifat kebijakan
    (``ris_isac_env.py``: ``truncated = t >= T or not in_roi``). Jumlah
    lintasan yang berbeda karena itu dilaporkan juga -- kalau suatu saat angka
    itu bukan 1 per lintasan lagi, asumsinya sudah tidak berlaku.
    """
    lengths = episodes["steps"].to_numpy(dtype=float)
    per_traj = episodes.groupby("trajectory_index")["steps"]
    return {"mean": float(lengths.mean()), "min": int(lengths.min()),
            "max": int(lengths.max()), "median": float(np.median(lengths)),
            "n_episodes": int(len(lengths)),
            "n_trajectories": int(per_traj.ngroups),
            "varies_within_trajectory": int((per_traj.nunique() > 1).sum()),
            "fraction_truncated_early": float(
                (lengths < lengths.max()).mean())}


def ecdf(values):
    """CDF empiris untuk F5: ``(x terurut, F(x))`` dengan F dari 1/n sampai 1."""
    x = np.sort(np.asarray(values, dtype=float))
    return x, np.arange(1, len(x) + 1, dtype=float) / float(len(x))
