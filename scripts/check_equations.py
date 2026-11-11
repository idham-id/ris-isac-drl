"""Cek silang persamaan paper <-> fungsi kode <-> tes unit (Fase 7).

    python scripts/check_equations.py

CLAUDE.md: "Fungsi yang mengimplementasikan rumus mencantumkan nomor persamaan
di docstring dan punya tes unit." Skrip ini menegakkan aturan itu secara
mekanis, bukan lewat pembacaan manual sekali jalan:

1. kumpulkan label ``(E0)``..``(E9)`` yang **didefinisikan** di
   ``docs/EXPERIMENT_DESIGN.md``;
2. telusuri ``src/risisac`` dengan ``ast`` dan catat tiap fungsi yang
   docstring-nya menyebut salah satu label;
3. telusuri ``tests/`` dan catat nama fungsi apa saja yang benar-benar
   dirujuk di sana;
4. laporkan persamaan tanpa implementasi, dan implementasi tanpa tes.

Yang dicari ``ast``, bukan regex atas seluruh berkas: regex ikut menangkap
sebutan ``(E9)`` di komentar atau di string biasa, lalu melaporkan "ada
implementasinya" untuk berkas yang hanya kebetulan menyebutnya -- persis
jenis kesalahan yang pemeriksaan ini seharusnya tangkap.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
EQ = re.compile(r"\(E(\d)\)")
#: Satu pola saja: konvensi CLAUDE.md menuntut nomor persamaan ditulis (E#)
#: di docstring, jadi pola longgar tanpa kurung tidak diperlukan -- ia justru
#: ikut menangkap kata lain dan menyembunyikan docstring yang belum patuh.

#: Paket tempat RUMUS diimplementasikan. Sebutan persamaan di luar paket ini
#: -- misalnya docstring pembuat tabel yang menulis "ablasi ... (E5)" --
#: adalah rujukan provenans, bukan implementasi, dan tidak menuntut tes unit.
#: Dilaporkan terpisah, tidak disembunyikan.
FORMULA_PACKAGES = ("system", "channels", "baselines", "env", "tracking",
                    "mobility", "scene")

#: Persamaan yang memang tidak punya satu fungsi tunggal, beserta alasannya.
#: Dinyatakan di sini supaya pengecualiannya terlihat, bukan tersembunyi
#: sebagai "kebetulan tidak ketemu".
EXEMPT = {
    "E8": "kendala keras masalah optimasi (§3.6); dilonggarkan menjadi (E9), "
          "yang diuji. Tidak ada fungsi yang menghitungnya sendiri.",
}


def defined_equations(doc: Path) -> list[str]:
    """Label persamaan yang muncul di dokumen desain, terurut."""
    text = doc.read_text(encoding="utf-8")
    return sorted({f"E{m.group(1)}" for m in EQ.finditer(text)})


def functions_with_equations(root: Path):
    """Pisahkan dua hal yang mudah tertukar.

    * **fungsi** -- docstring sebuah fungsi/kelas menyebut ``(E#)``. Inilah
      implementasinya, dan inilah yang wajib punya tes unit.
    * **modul** -- docstring modul menyebut persamaannya. Itu menandai
      *di mana* persamaan itu tinggal, bukan satu fungsi yang menghitungnya.
      E0 contohnya: ia prosedur validasi (§4.5), bukan rumus tunggal.

    Menggabungkan keduanya membuat tiap modul yang menyebut (E9) di
    pengantarnya tampak sebagai implementasi tak-teruji.
    """
    by_function: dict[str, list[tuple[str, str]]] = {}
    by_module: dict[str, list[str]] = {}
    for path in sorted(root.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), str(path))
        module = str(path.relative_to(REPO)).replace("\\", "/")

        head = ast.get_docstring(tree) or ""
        for label in {f"E{m.group(1)}" for m in EQ.finditer(head)}:
            by_module.setdefault(label, []).append(module)

        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                                     ast.ClassDef)):
                continue
            doc = ast.get_docstring(node) or ""
            for label in {f"E{m.group(1)}" for m in EQ.finditer(doc)}:
                by_function.setdefault(label, []).append((module, node.name))
    return by_function, by_module


def names_used_in_tests(root: Path) -> set[str]:
    """Semua nama yang dirujuk di berkas tes (panggilan, impor, atribut)."""
    used: set[str] = set()
    for path in sorted(root.glob("test_*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                used.add(node.id)
            elif isinstance(node, ast.Attribute):
                used.add(node.attr)
            elif isinstance(node, ast.ImportFrom):
                used.update(a.name for a in node.names)
    return used


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", default=None, help="tulis laporan ke berkas")
    args = ap.parse_args()

    equations = defined_equations(REPO / "docs" / "EXPERIMENT_DESIGN.md")
    impls, modules = functions_with_equations(REPO / "src" / "risisac")
    tested = names_used_in_tests(REPO / "tests")

    print(f"{'pers.':6s} {'fungsi':38s} {'modul':44s} tes")
    rows, missing_impl, missing_test = [], [], []
    for label in equations:
        found = impls.get(label, [])
        if not found:
            if label in EXEMPT:
                print(f"{label:6s} {'(dikecualikan)':38s} "
                      f"{EXEMPT[label][:44]:44s} --")
            elif modules.get(label):
                print(f"{label:6s} {'(tingkat modul)':38s} "
                      f"{', '.join(modules[label])[:44]:44s} --")
            else:
                print(f"{label:6s} {'TIDAK ADA IMPLEMENTASI':38s}")
                missing_impl.append(label)
            continue
        for module, name in found:
            package = module.split("/")[2] if module.count("/") > 2 else ""
            formula = package in FORMULA_PACKAGES
            ok = name in tested
            rows.append({"equation": label, "module": module,
                         "function": name, "tested": ok,
                         "kind": "implementasi" if formula else "rujukan"})
            mark = ("ya" if ok else "TIDAK") if formula else "(rujukan)"
            print(f"{label:6s} {name:38s} {module:44s} {mark}")
            if formula and not ok:
                missing_test.append(f"{label} {module}:{name}")

    print()
    print(f"persamaan di dokumen      : {len(equations)} "
          f"({', '.join(equations)})")
    print(f"fungsi yang mengacu rumus : {len(rows)}")
    print(f"tanpa implementasi        : "
          f"{', '.join(missing_impl) if missing_impl else 'tidak ada'}")
    print(f"tanpa tes                 : "
          f"{', '.join(missing_test) if missing_test else 'tidak ada'}")

    if args.json:
        Path(args.json).write_text(json.dumps(
            {"equations": equations, "rows": rows,
             "modules": modules, "exempt": EXEMPT,
             "missing_impl": missing_impl,
             "missing_test": missing_test}, indent=2), encoding="utf-8")

    passed = not missing_impl and not missing_test
    print(f"\nCEK SILANG: {'LOLOS' if passed else 'GAGAL'}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
