"""Gate 7 -- semua gambar dan tabel dibuat ulang dengan satu perintah (Fase 7).

    python scripts/run_gate7_check.py

Tiga pemeriksaan, dan ketiganya harus lolos:

1. **Cek silang persamaan** (`check_equations.py`): tiap persamaan (E0)--(E9)
   punya implementasi, dan tiap fungsi rumus punya tes unit.
2. **Satu perintah membuat ulang semuanya** (`make_figures.py`): dijalankan di
   direktori sementara yang kosong, lalu daftar artefaknya dicocokkan dengan
   yang diharapkan paper (§11). Direktori terpisah penting: menulis ke
   direktori lama akan lolos walau sebuah gambar diam-diam berhenti dibuat,
   karena berkas lamanya masih di sana.
3. **Pohon git bersih**: Gate 7 berbunyi "dari repo bersih". Perubahan yang
   belum di-commit berarti artefaknya berasal dari kode yang tidak tercatat di
   mana pun, sehingga tidak bisa direproduksi oleh orang lain.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from risisac.config import config_hash, git_commit, load_config  # noqa: E402

#: Artefak yang dituntut §11 (gambar) dan Fase 7 (tabel LaTeX).
EXPECTED_FIGURES = ("F1_layout", "F2_coverage", "F2b_radar", "F3_e0",
                    "F4_training", "F5_rate_cdf", "F6_episode",
                    "F7_pmax_speed", "F8_tradeoff")
EXPECTED_TABLES = ("T1_channel_validation.tex", "T2_main_results.tex",
                   "T3_ablation_cost.tex", "T4_parameters.tex")


def run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, *cmd], cwd=REPO, text=True,
                          capture_output=True, **kwargs)


def git_dirty() -> list[str]:
    """Berkas yang belum di-commit, mengabaikan yang memang diabaikan git."""
    for candidate in ("git", r"C:\Program Files\Git\cmd\git.exe"):
        try:
            out = subprocess.run([candidate, "status", "--porcelain"],
                                 cwd=REPO, text=True, capture_output=True)
        except (FileNotFoundError, OSError):
            continue
        if out.returncode == 0:
            return [line for line in out.stdout.splitlines() if line.strip()]
    return ["(git tidak tersedia -- pemeriksaan dilewati)"]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", default="base")
    ap.add_argument("--allow-dirty", action="store_true",
                    help="jangan gagalkan gate karena perubahan belum "
                         "di-commit (untuk dipakai saat masih menyunting)")
    args = ap.parse_args()

    cfg = load_config(args.config)
    checks: dict[str, bool] = {}

    print("1) Cek silang persamaan")
    eq = run(["scripts/check_equations.py"])
    checks["persamaan"] = eq.returncode == 0
    print("   " + (eq.stdout.strip().splitlines() or ["(tanpa keluaran)"])[-1])

    print("\n2) Satu perintah membuat ulang semuanya (direktori kosong)")
    with tempfile.TemporaryDirectory(prefix="gate7_") as tmp:
        made = run(["scripts/make_figures.py", "--config", args.config,
                    "--out", tmp])
        if made.returncode != 0:
            print(made.stdout[-2000:])
            print(made.stderr[-2000:])
            checks["gambar"] = checks["tabel"] = False
        else:
            names = {p.name for p in Path(tmp).iterdir()}
            missing_fig = [f for f in EXPECTED_FIGURES
                           if f"{f}.png" not in names or f"{f}.pdf" not in names]
            missing_tab = [t for t in EXPECTED_TABLES if t not in names]
            checks["gambar"] = not missing_fig
            checks["tabel"] = not missing_tab
            print(f"   {len(EXPECTED_FIGURES) - len(missing_fig)}/"
                  f"{len(EXPECTED_FIGURES)} gambar (PNG + PDF), "
                  f"{len(EXPECTED_TABLES) - len(missing_tab)}/"
                  f"{len(EXPECTED_TABLES)} tabel LaTeX")
            for name in missing_fig:
                print(f"   [!] gambar hilang: {name}")
            for name in missing_tab:
                print(f"   [!] tabel hilang: {name}")
            manifest = json.loads(
                (Path(tmp) / "manifest.json").read_text(encoding="utf-8"))
            for key, info in manifest["sources"].items():
                delta = info.get("config_delta") or []
                note = f" (beda tak relevan: {', '.join(delta)})" if delta else ""
                print(f"   sumber {key}: {Path(info['dir']).name}{note}")

    print("\n3) Pohon git bersih")
    dirty = git_dirty()
    checks["git_bersih"] = not dirty or args.allow_dirty
    if dirty:
        for line in dirty[:8]:
            print(f"   {line}")
        if len(dirty) > 8:
            print(f"   ... dan {len(dirty) - 8} lagi")
        if args.allow_dirty:
            print("   (--allow-dirty: tidak menggagalkan gate)")
    else:
        print(f"   bersih pada commit {git_commit()[:12]}")

    print("\nGate 7\n------")
    for name, ok in checks.items():
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}")
    passed = all(checks.values())
    print(f"\nGATE 7: {'LOLOS' if passed else 'GAGAL'}  "
          f"(config {args.config}, hash {config_hash(cfg)})")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
