"""Pemuatan konfigurasi.

Satu sumber kebenaran untuk semua angka parameter adalah ``configs/*.yaml``
(lihat CLAUDE.md). Override eksperimen ditulis sebagai file kecil berisi
``defaults: [base]`` lalu hanya kunci yang perlu diubah.

Catatan YAML: PyYAML memakai resolver YAML 1.1, yang hanya mengenali notasi
eksponen sebagai float bila tandanya eksplisit (``3.5e+9``, bukan ``3.5e9``).
``load_config`` memeriksa ini dan menolak config yang melanggar, supaya
kesalahan ketik tidak baru meledak beberapa fase kemudian.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

import yaml

_NUMERIC_STR = re.compile(r"^[-+]?(\d+\.?\d*|\.\d+)([eE][-+]?\d+)?$")

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = REPO_ROOT / "configs"


def _deep_merge(base: dict, override: dict) -> dict:
    """Gabung ``override`` di atas ``base``. Dict digabung rekursif; tipe lain
    diganti utuh (termasuk list, supaya mengganti daftar tidak setengah-setengah)."""
    out = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def _find_numeric_strings(node: Any, path: str = "") -> list[tuple[str, str]]:
    """Nilai yang terlihat seperti angka tetapi ter-parse sebagai str."""
    bad: list[tuple[str, str]] = []
    if isinstance(node, dict):
        for k, v in node.items():
            bad += _find_numeric_strings(v, f"{path}.{k}" if path else str(k))
    elif isinstance(node, list):
        for i, v in enumerate(node):
            bad += _find_numeric_strings(v, f"{path}[{i}]")
    elif isinstance(node, str) and _NUMERIC_STR.match(node):
        bad.append((path, node))
    return bad


def load_config(name_or_path: str | Path, _seen: set[str] | None = None) -> dict:
    """Muat satu config beserta rantai ``defaults``.

    ``name_or_path`` boleh nama ("base") atau path ke file YAML.
    """
    path = Path(name_or_path)
    if not path.suffix:
        path = CONFIG_DIR / f"{path}.yaml"
    path = path.resolve()

    _seen = _seen or set()
    if str(path) in _seen:
        raise ValueError(f"Lingkaran pada 'defaults' config: {path}")
    _seen.add(str(path))

    with open(path, "r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}

    defaults = raw.pop("defaults", []) or []
    if isinstance(defaults, str):
        defaults = [defaults]

    merged: dict = {}
    for parent in defaults:
        merged = _deep_merge(merged, load_config(parent, _seen))
    merged = _deep_merge(merged, raw)

    bad = _find_numeric_strings(merged)
    if bad:
        lines = "\n".join(f"  {p} = {v!r}" for p, v in bad)
        raise ValueError(
            f"Config {path.name}: nilai berikut ter-parse sebagai string, bukan "
            f"angka.\n{lines}\n"
            "Penyebab paling umum: notasi eksponen tanpa tanda. Tulis 3.5e+9, "
            "bukan 3.5e9 (resolver YAML 1.1)."
        )
    return merged


def config_hash(cfg: dict, length: int = 12) -> str:
    """Hash stabil untuk satu config, dipakai di nama direktori hasil."""
    blob = json.dumps(cfg, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:length]


def noise_power_watt(cfg: dict) -> float:
    """Daya derau per antena terima [W].

    sigma_n^2 = -174 dBm/Hz + 10 log10(B) + NF   (desain §8)
    """
    radio = cfg["radio"]
    n_dbm = (-174.0
             + 10.0 * __import__("math").log10(radio["bandwidth_hz"])
             + radio["noise_figure_db"])
    return 10.0 ** ((n_dbm - 30.0) / 10.0)
