"""Pemeriksaan environment untuk Gate 0 (docs/TASKS.md Fase 0, versi ramping).

    python scripts/check_env.py

Mencetak versi paket, varian Dr.Jit yang aktif (CUDA/LLVM), VRAM bebas,
memuat satu scene bawaan, dan menghitung jalur untuk satu pasang Tx-Rx.

Keluar 0 bila semua pemeriksaan wajib lolos, 1 bila ada yang gagal. WARN tidak
menggagalkan gate tetapi wajib dicatat di docs/LOG.md.

Catatan: versi paket dibaca dari metadata distribusi, BUKAN dengan mengimpor
paketnya, supaya kegagalan impor tidak ikut menggagalkan deteksi versi.
"""

from __future__ import annotations

import argparse
import importlib
import importlib.metadata as md
import platform
import sys
import time

PASS, WARN, FAIL = "PASS", "WARN", "FAIL"
_results: list[tuple[str, str, str]] = []

# nama modul -> nama distribusi di metadata
_PACKAGES = [
    ("sionna", "sionna"),
    ("sionna.rt", "sionna-rt"),
    ("drjit", "drjit"),
    ("mitsuba", "mitsuba"),
    ("torch", "torch"),
    ("numpy", "numpy"),
    ("scipy", "scipy"),
    ("h5py", "h5py"),
    ("yaml", "PyYAML"),
    ("gymnasium", "gymnasium"),
    ("stable_baselines3", "stable-baselines3"),
    ("pandas", "pandas"),
    ("pyarrow", "pyarrow"),
    ("matplotlib", "matplotlib"),
    ("pytest", "pytest"),
]


def record(status: str, name: str, detail: str = "") -> None:
    _results.append((status, name, detail))
    print(f"  [{status}] {name}" + (f": {detail}" if detail else ""))


def check_python() -> None:
    v = sys.version_info
    detail = f"{platform.python_version()} ({platform.system()} {platform.release()})"
    # Desain menargetkan 3.11/3.12.
    if (v.major, v.minor) in ((3, 11), (3, 12)):
        record(PASS, "python", detail)
    else:
        record(WARN, "python", detail + " - desain menargetkan 3.11/3.12")


def check_packages() -> dict[str, str]:
    versions: dict[str, str] = {}
    for module, dist in _PACKAGES:
        try:
            ver = md.version(dist)
            versions[dist] = ver
            record(PASS, f"versi {dist}", ver)
        except md.PackageNotFoundError:
            record(FAIL, f"versi {dist}", "tidak terpasang")
    return versions


def check_torch_cuda() -> None:
    """torch dari PyPI di Windows adalah build CPU dan mematikan GPU diam-diam."""
    try:
        import torch
    except Exception as exc:  # pragma: no cover
        record(FAIL, "impor torch", f"{type(exc).__name__}: {exc}")
        return
    build = torch.__version__
    if not torch.cuda.is_available():
        record(FAIL, "torch.cuda", f"tidak tersedia (build {build}); butuh wheel cu1xx")
        return
    free, total = torch.cuda.mem_get_info()
    record(PASS, "torch.cuda", f"{torch.cuda.get_device_name(0)}, build {build}")
    record(PASS, "VRAM bebas", f"{free / 2**30:.2f} GiB dari {total / 2**30:.2f} GiB")


def check_drjit_variant() -> None:
    """Varian mana yang benar-benar dipakai: CUDA (GPU) atau LLVM (CPU)."""
    try:
        import drjit as dr
    except Exception as exc:
        record(FAIL, "impor drjit", f"{type(exc).__name__}: {exc}")
        return
    backends = []
    for name in ("CUDA", "LLVM"):
        try:
            if dr.has_backend(getattr(dr.JitBackend, name)):
                backends.append(name)
        except Exception as exc:  # drjit < 1.0 tidak punya has_backend
            record(WARN, f"drjit backend {name}", f"{type(exc).__name__}: {exc}")
    if "CUDA" in backends:
        record(PASS, "backend Dr.Jit", ", ".join(backends) + " (ray tracing di GPU)")
    elif backends:
        record(WARN, "backend Dr.Jit", ", ".join(backends) + " - hanya CPU, prakomputasi akan lambat")
    else:
        record(FAIL, "backend Dr.Jit", "tidak ada backend aktif")



def check_scene_and_paths(scene_name: str) -> None:
    """Muat satu scene bawaan dan hitung jalur untuk satu pasang Tx-Rx."""
    try:
        import sionna
        import sionna.rt as rt
    except Exception as exc:
        record(FAIL, "impor sionna.rt", f"{type(exc).__name__}: {exc}")
        return

    # sionna.phy menolak "cuda"; harus "cuda:0".
    try:
        import torch
        if torch.cuda.is_available():
            sionna.phy.config.device = "cuda:0"
            record(PASS, "sionna device", "cuda:0")
    except Exception as exc:
        record(WARN, "sionna device", f"{type(exc).__name__}: {exc}")

    try:
        path = getattr(rt.scene, scene_name)
        t0 = time.time()
        scene = rt.load_scene(path)
        record(PASS, f"muat scene {scene_name}",
               f"{len(scene.objects)} objek, {time.time() - t0:.2f}s")
        # Varian Mitsuba baru ditetapkan saat scene pertama dimuat; menanyakannya
        # lebih awal selalu mengembalikan None.
        import mitsuba as mi
        variant = mi.variant()
        if variant and "cuda" in variant:
            record(PASS, "varian Mitsuba", variant)
        else:
            record(WARN, "varian Mitsuba", f"{variant} - bukan varian CUDA")
    except Exception as exc:
        record(FAIL, f"muat scene {scene_name}", f"{type(exc).__name__}: {exc}")
        return

    try:
        scene.tx_array = rt.PlanarArray(num_rows=1, num_cols=1, pattern="iso",
                                        polarization="V")
        scene.rx_array = rt.PlanarArray(num_rows=1, num_cols=1, pattern="iso",
                                        polarization="V")
        scene.add(rt.Transmitter("tx", position=[8.5, 21.0, 27.0]))
        scene.add(rt.Receiver("rx", position=[45.0, 90.0, 1.5]))
        t0 = time.time()
        paths = rt.PathSolver()(scene, max_depth=3, samples_per_src=int(1e5))
        n = int(paths.a[0].shape[-1]) if hasattr(paths, "a") else -1
        record(PASS, "hitung jalur 1 Tx-Rx", f"{n} jalur, {time.time() - t0:.2f}s")
    except Exception as exc:
        record(FAIL, "hitung jalur 1 Tx-Rx", f"{type(exc).__name__}: {exc}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--scene", default="munich", help="scene bawaan untuk uji muat")
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    print("=" * 70)
    print("Gate 0 - pemeriksaan environment (RIS-ISAC-DRL versi ramping)")
    print("=" * 70)

    print("\n-- Interpreter --")
    check_python()

    print("\n-- Paket --")
    check_packages()

    print("\n-- GPU --")
    check_torch_cuda()

    print("\n-- Dr.Jit / Mitsuba --")
    check_drjit_variant()

    print("\n-- Sionna RT --")
    check_scene_and_paths(args.scene)

    n_pass = sum(1 for s, _, _ in _results if s == PASS)
    n_warn = sum(1 for s, _, _ in _results if s == WARN)
    n_fail = sum(1 for s, _, _ in _results if s == FAIL)
    print("\n" + "=" * 70)
    print(f"GATE 0: {n_pass} PASS, {n_warn} WARN, {n_fail} FAIL")
    if n_fail:
        print("GAGAL - perbaiki FAIL di atas sebelum lanjut ke Fase 1.")
    else:
        print("LOLOS - catat versi dan VRAM di docs/LOG.md.")
    print("=" * 70)
    return 1 if n_fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
