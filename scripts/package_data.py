"""Kemas data rilis publik (Fase 11): kanal, hasil, dan checkpoint terbaik.

    python scripts/package_data.py

Menulis `dist/ris-isac-drl-data-v1.0.zip` yang diekstrak di ROOT repo, berisi
tepat apa yang dibutuhkan untuk membuat ulang setiap gambar dan tabel naskah
dengan `python scripts/make_figures.py --config base`, tanpa GPU dan tanpa
melatih ulang apa pun.

Yang IKUT masuk:
  * basis data kanal `data/channels/synthetic_l/<channel_hash>.h5`;
  * `results/{e0,e1,eval,gate3,gate5,paper}/<config_hash>/` untuk tiap config
    yang dipakai naskah (base + sapuan Gamma + sapuan kappa);
  * untuk tiap run pelatihan: HANYA checkpoint validasi terbaik
    (`model_best.zip`), statistik VecNormalize yang menyertainya, `done.json`,
    `meta.json`, salinan config, dan log CSV (`eval_val.csv`, `progress.csv`).

Yang TIDAK ikut: `checkpoints/` periodik, `model.zip` akhir (bukan yang
dilaporkan: pemilihan model memakai validasi, lihat docs/LOG.md Fase 7),
`vecnormalize.pkl` akhir, dan file TensorBoard. Itu yang membuat 6,5 GB
hasil pelatihan menyusut menjadi ratusan MB.

Daftar config DITURUNKAN dari `configs/*.yaml` lewat `config_hash`, bukan
ditulis sebagai hash harfiah, supaya tidak bisa basi diam-diam.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from risisac.config import (channel_config_hash, config_hash,  # noqa: E402
                            git_commit, load_config)

#: Config yang hasilnya dikutip naskah. base = run utama; sisanya sapuan.
PAPER_CONFIGS = ("base", "gamma10", "gamma16", "kappa025", "kappa050")

#: Direktori hasil yang ikut, selain pelatihan.
RESULT_KINDS = ("e0", "e1", "gate3", "gate5", "eval", "paper")

#: File yang disimpan dari tiap direktori seed pelatihan. Checkpoint periodik,
#: model akhir, dan TensorBoard sengaja TIDAK ada di sini.
TRAIN_KEEP = ("model_best.zip", "vecnormalize_best.pkl", "done.json",
              "meta.json", "config.yaml", "eval_val.csv", "progress.csv")

#: File teks yang disaring dari path absolut mesin pengembang sebelum dikemas.
TEXT_SUFFIXES = (".json", ".yaml", ".yml", ".csv", ".md", ".txt", ".xml")

#: Pola akar repo di mesin mana pun. Pemisahnya boleh maju atau mundur, dan
#: boleh GANDA: di dalam JSON tiap `\` ditulis `\\`, sehingga pola berpemisah
#: tunggal tidak akan cocok dengan `manifest.json` sama sekali.
_ROOT = "".join(c if c.isalnum() else ("[/\\\\]{1,2}" if c in "/\\"
                                       else re.escape(c))
                for c in str(REPO))

#: Akar BESERTA ekornya, supaya pemisah di ekor ikut dinormalkan.
_REPO_PATH = re.compile(_ROOT + r"((?:[/\\]{1,2}[\w.\-]+)*)", re.IGNORECASE)

_SEP = re.compile(r"[/\\]{1,2}")


def sanitise(text: str) -> tuple[str, int]:
    """Ganti path absolut repo dengan path relatif berpemisah maju.

    `manifest.json` mencatat direktori sumber tiap artefak sebagai path
    absolut mesin pengembang. Itu tidak boleh ikut ke rilis publik. Ekornya
    ikut ditulis ulang: pemisah mundur benar di Windows tetapi tidak terbaca
    di tempat lain, dan arsip ini justru dibaca di tempat lain.
    """
    count = 0

    def repl(m: "re.Match[str]") -> str:
        nonlocal count
        count += 1
        return "." + _SEP.sub("/", m.group(1))

    return _REPO_PATH.sub(repl, text), count


def collect(verbose: bool = True) -> tuple[list[tuple[Path, str]], dict]:
    """Kumpulkan (sumber, path di dalam zip) dan ringkasan isinya."""
    items: list[tuple[Path, str]] = []
    missing: list[str] = []
    summary: dict = {"configs": {}, "channel": None, "runs": 0, "seeds": 0}

    cfgs = {name: load_config(name) for name in PAPER_CONFIGS}

    # 1. Basis data kanal. Semua config berbagi satu channel_config_hash.
    chashes = sorted({channel_config_hash(c) for c in cfgs.values()})
    for ch in chashes:
        src = REPO / "data" / "channels" / "synthetic_l" / f"{ch}.h5"
        if src.exists():
            items.append((src, f"data/channels/synthetic_l/{ch}.h5"))
            summary["channel"] = ch
        else:
            missing.append(str(src.relative_to(REPO)))

    # 2. Hasil per eksperimen, per config.
    for name, cfg in cfgs.items():
        chash = config_hash(cfg)
        summary["configs"][name] = {"config_hash": chash, "kinds": [],
                                    "methods": {}}
        for kind in RESULT_KINDS:
            d = REPO / "results" / kind / chash
            if not d.is_dir():
                continue
            summary["configs"][name]["kinds"].append(kind)
            for f in sorted(d.rglob("*")):
                if f.is_file():
                    items.append((f, str(f.relative_to(REPO)).replace("\\", "/")))

        # 3. Pelatihan: hanya yang terbaik menurut validasi.
        tdir = REPO / "results" / "train" / chash
        if not tdir.is_dir():
            continue
        for method in sorted(p.name for p in tdir.iterdir() if p.is_dir()):
            seeds = sorted(p for p in (tdir / method).iterdir() if p.is_dir())
            summary["configs"][name]["methods"][method] = len(seeds)
            summary["runs"] += 1
            for seed_dir in seeds:
                summary["seeds"] += 1
                for keep in TRAIN_KEEP:
                    f = seed_dir / keep
                    if f.exists():
                        items.append(
                            (f, str(f.relative_to(REPO)).replace("\\", "/")))
                    else:
                        missing.append(str(f.relative_to(REPO)))

    summary["missing"] = missing
    if verbose and missing:
        print(f"[!] {len(missing)} file yang diharapkan tidak ada:")
        for m in missing[:10]:
            print(f"    {m}")
    return items, summary


def readme_data(summary: dict, version: str, zip_name: str) -> str:
    """README_DATA.md: isi, struktur, lisensi, dan cara memakai."""
    lines = [
        f"# RIS-ISAC-DRL data archive v{version}",
        "",
        "Ray-traced channel database, evaluation logs, paper artefacts and",
        "best-validation checkpoints for the paper *Real-Time Deep",
        "Reinforcement Learning Control of RIS-Assisted Integrated Sensing and",
        "Communication under Partial Observations* (Timur, Ashari and Widodo,",
        "Universitas Gadjah Mada).",
        "",
        "Code: <https://github.com/idham-id/ris-isac-drl>",
        f"Produced by commit `{git_commit()}`.",
        "",
        "## How to use it",
        "",
        "```bash",
        "git clone https://github.com/idham-id/ris-isac-drl.git",
        "cd ris-isac-drl",
        f"unzip /path/to/{zip_name} -d .    # extract AT THE REPOSITORY ROOT",
        "sha256sum -c SHA256SUMS",
        "pip install -r envs/requirements.txt && pip install -e .",
        "python scripts/make_figures.py --config base",
        "```",
        "",
        "That last command rebuilds every figure and table in the paper into",
        "`results/paper/<config_hash>/`, in about one minute, on the CPU. It",
        "recomputes no physics and retrains nothing: it reads the files in this",
        "archive, re-aggregates the evaluation logs and redraws.",
        "",
        "## What is inside",
        "",
        "```",
        "data/channels/synthetic_l/<channel_hash>.h5   ray-traced channel database",
        "results/e0/<config_hash>/                     channel-model validation (T1, F3)",
        "results/e1/<config_hash>/                     scene and coverage (F1, F2, Gate 1)",
        "results/gate3/<config_hash>/                  signal-model feasibility check",
        "results/gate5/<config_hash>/                  training curves (F4)",
        "results/eval/<config_hash>/                   test-set logs (T2, T3, T5, T6, F5-F8)",
        "results/paper/<config_hash>/                  the figures and tables themselves",
        "results/train/<config_hash>/<method>/<seed>/  best-validation checkpoint and logs",
        "```",
        "",
        "`<config_hash>` is computed from the whole configuration file, so it",
        "identifies exactly which settings produced a directory. The hashes in",
        "this archive are:",
        "",
        "| Config | `config_hash` | Result directories |",
        "|---|---|---|",
    ]
    for name, info in summary["configs"].items():
        lines.append(f"| `{name}` | `{info['config_hash']}` | "
                     f"{', '.join(info['kinds'])} |")
    lines += [
        "",
        f"The channel database is shared by all of them "
        f"(`channel_config_hash` = `{summary['channel']}`): changing a reward",
        "threshold or a training hyper-parameter must not force the ray",
        "tracing to be repeated.",
        "",
        "## Training runs: what was kept and what was not",
        "",
        "Each `results/train/<config_hash>/<method>/<seed>/` directory holds:",
        "",
        "| File | What it is |",
        "|---|---|",
        "| `model_best.zip` | the checkpoint selected on the validation set |",
        "| `vecnormalize_best.pkl` | the observation statistics that go with it |",
        "| `done.json` | the run record: budget, wall time, final and best validation metrics |",
        "| `meta.json` | configuration hash, git commit, library versions |",
        "| `config.yaml` | the fully resolved configuration actually used |",
        "| `eval_val.csv` | the validation curve (every 50k steps) |",
        "| `progress.csv` | the training curve as logged by the PPO loop |",
        "",
        "The periodic `checkpoints/`, the final `model.zip` and the",
        "TensorBoard event files are **not** included: they are 6.5 GB and",
        "nothing in the paper is computed from them. Model selection is done",
        "on validation, never on the final weights, so `model_best.zip` is",
        "what every reported number comes from.",
        "",
        "## Licence",
        "",
        "This archive is released under **CC-BY-4.0**",
        "(<https://creativecommons.org/licenses/by/4.0/>). The code that",
        "produced it is released separately under Apache-2.0.",
        "",
        "Please cite the paper; see `CITATION.cff` in the code repository.",
        "",
        "## Integrity and provenance",
        "",
        "`SHA256SUMS` lists every file in this archive. Verify with",
        "`sha256sum -c SHA256SUMS` from the repository root after extracting.",
        "",
        "Every result directory carries a `meta.json` or `config_used.json`",
        "naming the git commit that produced it. The commits recorded in the",
        "**training runs** belong to the pre-publication history: the published",
        "history was rewritten once, before the first push, to remove links to",
        "a private development session, which changed every commit hash after",
        "the first without changing a single file. `docs/LOG.md` (entry of",
        "2026-11-12, phase 11) holds the full old-to-new map. The artefacts in",
        "`results/paper/` were regenerated after the rewrite, so their",
        "`manifest.json` names a commit that exists in the public history, and",
        "all eight figures and all seven tables came out byte-identical to the",
        "ones generated before it, apart from the creation date that the PDF",
        "writer embeds.",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--version", default="1.0")
    ap.add_argument("--out-dir", default="dist")
    ap.add_argument("--dry-run", action="store_true",
                    help="hitung isi dan ukuran, jangan tulis zip")
    args = ap.parse_args()

    items, summary = collect()
    raw = sum(src.stat().st_size for src, _ in items)
    print(f"Isi   : {len(items)} file, {raw / 1e6:.1f} MB sebelum kompresi")
    print(f"Kanal : {summary['channel']}")
    for name, info in summary["configs"].items():
        methods = ", ".join(f"{m}x{n}" for m, n in info["methods"].items())
        print(f"  {name:9s} {info['config_hash']}  "
              f"[{', '.join(info['kinds'])}]  {methods or '-'}")
    print(f"Run   : {summary['runs']} metode-config, {summary['seeds']} seed")
    if args.dry_run:
        return 1 if summary["missing"] else 0

    out_dir = REPO / args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    zip_name = f"ris-isac-drl-data-v{args.version}.zip"
    zip_path = out_dir / zip_name

    # Dua lintasan: pertama siapkan isi file (dengan penyaringan path), hitung
    # SHA256 atas isi YANG AKAN ditulis, baru kemudian tulis zip -- supaya
    # SHA256SUMS cocok dengan isi zip, bukan dengan file asli di disk.
    payload: list[tuple[str, bytes]] = []
    sanitised = 0
    for src, arc in items:
        data = src.read_bytes()
        if src.suffix.lower() in TEXT_SUFFIXES:
            try:
                text, n = sanitise(data.decode("utf-8"))
            except UnicodeDecodeError:
                n = 0
            else:
                if n:
                    sanitised += n
                    data = text.encode("utf-8")
        payload.append((arc, data))

    readme = readme_data(summary, args.version, zip_name)
    payload.append(("README_DATA.md", readme.encode("utf-8")))

    # Jaring pengaman: tidak satu pun file boleh membawa path pribadi ke
    # rilis publik, termasuk file biner yang tidak ikut disaring.
    needles = (str(REPO.parents[1]).encode("utf-8"),
               str(REPO.parents[1]).replace("\\", "\\\\").encode("utf-8"),
               str(REPO.parents[1]).replace("\\", "/").encode("utf-8"))
    leaks = [a for a, d in payload if any(n.lower() in d.lower()
                                          for n in needles)]
    if leaks:
        print(f"[!] {len(leaks)} file masih memuat path pribadi; "
              f"batal menulis zip:")
        for a in leaks[:10]:
            print(f"    {a}")
        return 2

    sums = "\n".join(f"{hashlib.sha256(d).hexdigest()}  {a}"
                     for a, d in sorted(payload)) + "\n"
    payload.append(("SHA256SUMS", sums.encode("utf-8")))

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED,
                         compresslevel=6) as z:
        for arc, data in payload:
            z.writestr(arc, data)

    size = zip_path.stat().st_size
    print(f"Saring: {sanitised} path absolut diganti '.'")
    print(f"Tulis : {zip_path.relative_to(REPO)}  "
          f"{size / 1e6:.1f} MB  ({len(payload)} entri, "
          f"rasio {size / raw:.2f})")
    (out_dir / "SHA256SUMS").write_text(sums, encoding="utf-8")
    (out_dir / "README_DATA.md").write_text(readme, encoding="utf-8")
    print(f"        {zip_name} sha256 "
          f"{hashlib.sha256(zip_path.read_bytes()).hexdigest()}")
    return 1 if summary["missing"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
