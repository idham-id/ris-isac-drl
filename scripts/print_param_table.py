"""Tabel parameter LaTeX dari config (docs/TASKS.md Fase 7).

    python scripts/print_param_table.py --config base
    python scripts/print_param_table.py --out results/paper/T4_parameters.tex

Dicetak langsung dari ``configs/*.yaml`` supaya tabel parameter paper tidak
bisa menyimpang dari yang benar-benar dijalankan. Tiap baris memetakan satu
simbol di dokumen desain ke satu jalur di config; baris yang jalurnya tidak
ada di config dilewati dan dilaporkan, bukan diisi angka tebakan.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from risisac.config import config_hash, load_config          # noqa: E402
from risisac.eval.tables import PARAM_ROWS, _dig, parameter_table  # noqa: E402


def missing_rows(cfg: dict) -> list[str]:
    out = []
    for label, path, _ in PARAM_ROWS:
        try:
            _dig(cfg, path)
        except (KeyError, TypeError):
            out.append(f"{label} ({'.'.join(path)})")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", default="base")
    ap.add_argument("--out", default=None,
                    help="tulis ke berkas; tanpa ini dicetak ke stdout")
    args = ap.parse_args()

    cfg = load_config(args.config)
    text = parameter_table(cfg)
    gaps = missing_rows(cfg)

    if args.out:
        path = Path(args.out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        print(f"{path}  ({args.config}, config_hash {config_hash(cfg)})")
    else:
        print(text)
    for gap in gaps:
        print(f"  [!] baris dilewati, jalur tidak ada di config: {gap}",
              file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
