"""Buat ULANG seluruh gambar dan tabel paper dengan satu perintah (Fase 7).

    python scripts/make_figures.py --config base

Gate 7 menuntut satu perintah yang membuat ulang semuanya dari `results/`.
Skrip ini **tidak menghitung ulang apa pun**: tidak ada ray tracing, tidak ada
pelatihan, tidak ada rollout. Ia membaca file hasil yang sudah ada, menggambar
ulang, dan menulis PNG + PDF vektor + tabel LaTeX ke satu direktori, beserta
`manifest.json` yang mencatat dari direktori mana tiap artefak berasal.

**Mencari direktori hasil yang benar.** `config_hash` dihitung dari SELURUH
config, jadi menambah satu kunci yang tidak relevan -- misalnya tiga kunci
`ray_tracing` yang ditambahkan belakangan, atau `reward.lambda` yang dinaikkan
di Fase 3 -- mengubah hash dan membuat hasil yang secara fisik masih sah
tampak "hilang". Skrip ini karena itu:

1. mencoba `results/<eksperimen>/<config_hash>` apa adanya;
2. kalau tidak ada, membaca `config_used.json` tiap kandidat dan menerima yang
   selisihnya terhadap config sekarang **seluruhnya** berada di daftar kunci
   yang dinyatakan tidak relevan untuk eksperimen itu;
3. kalau tidak ada yang lolos, berhenti dan mencetak selisihnya -- tidak
   pernah diam-diam memakai hasil basi.

Arahnya sengaja aman: kunci baru yang belum diklasifikasikan membuat kandidat
DITOLAK, bukan diterima.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from risisac.config import (channel_config_hash, config_hash,     # noqa: E402
                            git_commit, load_config)
from risisac.eval import tables                                   # noqa: E402
from risisac.eval.plots import (plot_f1_layout, plot_f2_coverage,  # noqa: E402
                                plot_f3_e0,
                                plot_f4_training, plot_f5_rate_cdf,
                                plot_f6_episode, plot_f7_pmax_speed,
                                plot_f8_tradeoff)
from risisac.scene.placement import Placement                     # noqa: E402
from risisac.scene.synthetic_l import SyntheticLSpec              # noqa: E402

#: Kunci config yang TIDAK memengaruhi isi tiap eksperimen. Apa pun di luar
#: daftar ini dianggap relevan, sehingga kandidat yang berbeda padanya ditolak.
IRRELEVANT = {
    "e0": ("reward", "training", "action", "observation", "evaluation",
           "baselines", "gate1", "gate3", "experiment", "experiments",
           "paths", "sensing", "mobility", "tracking"),
    "e1": ("reward", "training", "action", "observation", "evaluation",
           "baselines", "gate3", "experiment", "experiments", "paths",
           "tracking"),
}


# ------------------------------------------------------------------ resolver
def flatten(node, prefix: str = "") -> dict:
    out = {}
    for key, value in (node or {}).items():
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            out.update(flatten(value, path))
        else:
            out[path] = value
    return out


def config_delta(stored: dict, current: dict) -> dict:
    """Kunci yang berbeda antara config tersimpan dan config sekarang."""
    a, b = flatten(stored), flatten(current)
    return {k: (a.get(k), b.get(k)) for k in sorted(set(a) | set(b))
            if a.get(k) != b.get(k)}


def resolve(root: Path, cfg: dict, irrelevant) -> tuple[Path, dict]:
    """Direktori hasil untuk config ini, beserta selisih config yang diterima."""
    exact = root / config_hash(cfg)
    if (exact / "config_used.json").exists() or exact.is_dir():
        return exact, {}
    if not root.is_dir():
        raise SystemExit(f"[!] {root} tidak ada. Jalankan eksperimennya dulu.")

    rejected = {}
    for candidate in sorted(root.iterdir()):
        stored_path = candidate / "config_used.json"
        if not stored_path.exists():
            continue
        delta = config_delta(
            json.loads(stored_path.read_text(encoding="utf-8")), cfg)
        stray = [k for k in delta
                 if not any(k == p or k.startswith(p + ".")
                            for p in irrelevant)]
        if not stray:
            return candidate, delta
        rejected[candidate.name] = stray[:6]

    lines = [f"[!] tidak ada hasil di {root} yang cocok dengan config ini "
             f"({config_hash(cfg)})."]
    for name, stray in rejected.items():
        lines.append(f"    {name}: berbeda pada {', '.join(stray)}")
    lines.append("    Jalankan ulang eksperimennya, atau tambahkan kuncinya ke "
                 "IRRELEVANT bila memang tidak berpengaruh.")
    raise SystemExit("\n".join(lines))


# -------------------------------------------------------------------- utilitas
def both(out_dir: Path, stem: str, draw) -> list[str]:
    """Gambar sekali sebagai PNG dan sekali sebagai PDF vektor.

    ``draw`` menerima jalur keluaran. Dipakai closure, bukan ``*args`` dengan
    jalur ditempel di belakang: posisi ``out_path`` BERBEDA antar fungsi plot
    (F6 dan F7 menaruhnya di argumen kedua), jadi menebak posisinya diam-diam
    meneruskan ``Path`` ke parameter lain.
    """
    made = []
    for suffix in (".png", ".pdf"):
        draw(out_dir / f"{stem}{suffix}")
        made.append(f"{stem}{suffix}")
    return made


def write(out_dir: Path, name: str, text: str) -> str:
    (out_dir / name).write_text(text, encoding="utf-8")
    return name


def main() -> int:
    import pandas as pd

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", default="base")
    ap.add_argument("--out", default=None)
    ap.add_argument("--skip", nargs="*", default=[],
                    help="lewati artefak tertentu, mis. F7 F8")
    args = ap.parse_args()

    cfg = load_config(args.config)
    chash = config_hash(cfg)
    out_dir = Path(args.out) if args.out else REPO / "results" / "paper" / chash
    out_dir.mkdir(parents=True, exist_ok=True)
    gamma = float(cfg["sensing"]["scnr_threshold_db"])
    p_max = float(cfg["radio"]["p_max_dbm"])
    skip = {s.upper() for s in args.skip}
    made, sources = [], {}

    print(f"config      : {args.config} ({chash})")
    print(f"kanal       : {channel_config_hash(cfg)}")
    print(f"keluaran    : {out_dir}")

    # ------------------------------------------------------------- F1, F2, F2b
    if not {"F1", "F2"} <= skip:
        e1_dir, delta = resolve(REPO / "results" / "e1", cfg, IRRELEVANT["e1"])
        sources["e1"] = {"dir": str(e1_dir), "config_delta": list(delta)}
        print(f"E1          : {e1_dir.name}"
              + (f"  (beda tak relevan: {', '.join(delta)})" if delta else ""))
        data = np.load(e1_dir / "e1_coverage.npz")
        grid = data["grid"]
        if "F1" not in skip:
            spec = SyntheticLSpec.from_config(cfg)
            place = Placement.from_config(cfg)
            share = float(data["los_ris_roi"].mean())
            made += both(out_dir, "F1_layout", lambda p: plot_f1_layout(
                spec, place, p, los_ris_fraction=share))
        if "F2" not in skip:
            p_values = list(data["p_max_dbm_values"])
            which = p_values.index(p_max) if p_max in p_values else 0
            m_elements = int(data["G"].shape[0])
            p_dbm = float(p_values[which])
            missing = [k for k in ("ris_gain_db", "scnr_ris_mrt_db",
                                   "scnr_direct_mrt_db") if k not in data]
            if missing:
                raise SystemExit(
                    f"[!] {e1_dir}/e1_coverage.npz tidak memuat "
                    f"{', '.join(missing)}. Itu hasil E1 sebelum Fase 8; "
                    "jalankan ulang scripts/run_e1_coverage.py.")
            made += both(out_dir, "F2_coverage", lambda p: plot_f2_coverage(
                grid[:, :2], data["ris_gain_db"],
                data["scnr_ris_mrt_db"][which],
                data["scnr_direct_mrt_db"][which], p,
                m_elements=m_elements, p_max_dbm=p_dbm,
                gain_threshold_db=float(cfg["gate1"]["ris_gain_threshold_db"]),
                gamma_db=gamma))

    # ------------------------------------------------------------- F3, T1 (E0)
    if "F3" not in skip or "T1" not in skip:
        e0_dir, delta = resolve(REPO / "results" / "e0", cfg, IRRELEVANT["e0"])
        sources["e0"] = {"dir": str(e0_dir), "config_delta": list(delta)}
        print(f"E0          : {e0_dir.name}"
              + (f"  (beda tak relevan: {', '.join(delta)})" if delta else ""))
        t1 = json.loads((e0_dir / "T1_e0.json").read_text(encoding="utf-8"))
        if "F3" not in skip:
            loaded = dict(t1)
            loaded["_synthetic_delta_db"] = np.load(
                e0_dir / "e0_synthetic_delta_db.npy")
            made += both(out_dir, "F3_e0", lambda p: plot_f3_e0(
                loaded, p, tolerance_db=float(t1["tolerance_db"])))
        if "T1" not in skip:
            made.append(write(out_dir, "T1_channel_validation.tex",
                              tables.t1_channel_validation(t1)))

    # --------------------------------------------------------------- F4 (gate5)
    if "F4" not in skip:
        gate5 = REPO / "results" / "gate5" / chash / "gate5.json"
        if not gate5.exists():
            raise SystemExit(f"[!] {gate5} belum ada "
                             "(python scripts/run_gate5_check.py --config "
                             f"{args.config})")
        g5 = json.loads(gate5.read_text(encoding="utf-8"))
        sources["gate5"] = {"dir": str(gate5.parent)}
        bases = {k: v["reward_per_step"] for k, v in g5["baselines"].items()}
        made += both(out_dir, "F4_training", lambda p: plot_f4_training(
            g5["curves"], p, baselines=bases))
        print(f"Gate 5      : {gate5.parent.name}")

    # --------------------------------------------------- F5..F8, T2, T3 (eval)
    eval_dir = REPO / "results" / "eval" / chash
    if not (eval_dir / "steps.parquet").exists():
        raise SystemExit(f"[!] {eval_dir}/steps.parquet belum ada "
                         f"(python -m risisac.eval.evaluate --config "
                         f"{args.config})")
    sources["eval"] = {"dir": str(eval_dir)}
    steps = pd.read_parquet(eval_dir / "steps.parquet")
    episodes = pd.read_parquet(eval_dir / "episodes.parquet")
    print(f"Evaluasi    : {eval_dir.name} "
          f"({len(steps)} langkah, {len(episodes)} episode)")

    if "F5" not in skip:
        made += both(out_dir, "F5_rate_cdf", lambda p: plot_f5_rate_cdf(
            steps, p, scnr_threshold_db=gamma))
    if "F6" not in skip:
        lengths = episodes.groupby("trajectory_index")["steps"].max()
        index = int(lengths.idxmax())
        made += both(out_dir, "F6_episode", lambda p: plot_f6_episode(
            steps, p, index, scnr_threshold_db=gamma,
            sigma_max_m=float(cfg["observation"]["target_pos_max_std_m"]),
            dt_s=float(cfg["mobility"]["dt_s"])))
    if "F7" not in skip and (eval_dir / "E4a.csv").exists():
        bins = [list(map(float, b))
                for b in cfg["mobility"]["speed_eval_bins_mps"]]
        e4a = pd.read_csv(eval_dir / "E4a.csv")
        made += both(out_dir, "F7_pmax_speed", lambda p: plot_f7_pmax_speed(
            e4a, p, bins))
    elif "F7" not in skip:
        print("  [!] E4a.csv belum ada; F7 dilewati "
              "(python scripts/run_e4a.py)")
    if "F8" not in skip and (eval_dir / "F8_points.json").exists():
        points = json.loads((eval_dir / "F8_points.json")
                            .read_text(encoding="utf-8"))
        made += both(out_dir, "F8_tradeoff",
                     lambda p: plot_f8_tradeoff(points, p))
    elif "F8" not in skip:
        print("  [!] F8_points.json belum ada; F8 dilewati "
              "(python scripts/run_gate6_check.py)")

    if "T2" not in skip:
        t2 = pd.read_csv(eval_dir / "T2.csv", index_col=0)
        made.append(write(out_dir, "T2_main_results.tex",
                          tables.t2_main_results(t2, gamma, p_max)))
    if "T3" not in skip:
        e5_path = eval_dir / "T3_e5_ablation.csv"
        cost_path = eval_dir / "T3_e6_cost.json"
        if e5_path.exists() and cost_path.exists():
            made.append(write(
                out_dir, "T3_ablation_cost.tex",
                tables.t3_ablation_cost(
                    pd.read_csv(e5_path),
                    json.loads(cost_path.read_text(encoding="utf-8")))))
        else:
            print("  [!] T3 dilewati (python scripts/run_e5_e6.py)")
    if "T4" not in skip:
        made.append(write(out_dir, "T4_parameters.tex",
                          tables.parameter_table(cfg)))

    (out_dir / "manifest.json").write_text(json.dumps({
        "config": args.config, "config_hash": chash,
        "channel_config_hash": channel_config_hash(cfg),
        "git_commit": git_commit(), "artifacts": sorted(made),
        "sources": sources, "skipped": sorted(skip),
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
    }, indent=2, default=str), encoding="utf-8")

    figures = sorted({m.rsplit(".", 1)[0] for m in made if m.endswith(".png")})
    latex = sorted(m for m in made if m.endswith(".tex"))
    print(f"\n{len(figures)} gambar (PNG + PDF): {', '.join(figures)}")
    print(f"{len(latex)} tabel LaTeX: {', '.join(latex)}")
    print(f"\nHasil: {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
