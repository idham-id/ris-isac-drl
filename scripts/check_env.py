"""Pemeriksaan environment untuk Gate 0 (docs/TASKS.md Fase 0).

Skrip ini sengaja dibuat agar bisa dijalankan di KEDUA environment dan
mendeteksi sendiri mana yang sedang aktif:

  * environment utama    -> sionna 2.x (Dr.Jit/Mitsuba, PyTorch)
  * environment validasi -> sionna 0.19.x (TensorFlow), hanya untuk E0

    python scripts/check_env.py

Keluar dengan kode 0 bila semua pemeriksaan wajib lolos, 1 bila ada yang gagal.
Peringatan (WARN) tidak menggagalkan gate tetapi harus dicatat di docs/LOG.md.

Catatan desain: versi paket dibaca dari metadata distribusi, BUKAN dengan
mengimpor paketnya. Mengimpor sionna 0.19 bisa gagal karena alasan lingkungan
(lihat bootstrap LLVM di bawah); kalau deteksi versi ikut gagal, skrip akan
salah memilih cabang API dan melaporkan error yang menyesatkan.
"""

from __future__ import annotations

import argparse
import importlib
import importlib.metadata as md
import os
import platform
import sys
import time

# --------------------------------------------------------------------------
# Bootstrap LLVM (harus sebelum impor drjit/mitsuba/sionna mana pun)
# --------------------------------------------------------------------------
# Sionna 0.19 memilih varian Mitsuba dari tf.config.list_physical_devices('GPU').
# TensorFlow tidak punya dukungan GPU native di Windows sejak 2.11, jadi daftar
# itu selalu kosong dan Sionna selalu memilih 'llvm_ad_rgb', yang butuh
# LLVM-C.dll. `conda env config vars set` hanya berlaku saat `conda activate`,
# sehingga memanggil python.exe lewat path langsung akan melewatkannya.
# Di sini kita cari sendiri DLL-nya di dalam prefix environment.
def _bootstrap_llvm() -> str | None:
    if sys.platform != "win32":
        return None
    existing = os.environ.get("DRJIT_LIBLLVM_PATH")
    if existing and os.path.isfile(existing):
        return existing
    candidate = os.path.join(sys.prefix, "Library", "bin", "LLVM-C.dll")
    if os.path.isfile(candidate):
        os.environ["DRJIT_LIBLLVM_PATH"] = candidate
        return candidate
    return None


_LLVM_PATH = _bootstrap_llvm()

PASS, WARN, FAIL = "PASS", "WARN", "FAIL"
_results: list[tuple[str, str, str]] = []

# nama modul -> nama distribusi di metadata
_PACKAGES = [
    ("sionna", "sionna"),
    ("sionna.rt", "sionna-rt"),
    ("torch", "torch"),
    ("tensorflow", "tensorflow"),
    ("drjit", "drjit"),
    ("mitsuba", "mitsuba"),
    ("numpy", "numpy"),
    ("scipy", "scipy"),
    ("h5py", "h5py"),
    ("yaml", "PyYAML"),
    ("gymnasium", "gymnasium"),
    ("stable_baselines3", "stable-baselines3"),
    ("sb3_contrib", "sb3-contrib"),
    ("pandas", "pandas"),
    ("pyarrow", "pyarrow"),
    ("matplotlib", "matplotlib"),
]


def record(status: str, name: str, detail: str = "") -> None:
    _results.append((status, name, detail))
    print(f"  [{status}] {name}" + (f" — {detail}" if detail else ""), flush=True)


def dist_version(dist_name: str) -> str | None:
    """Versi dari metadata distribusi. Tidak mengeksekusi paketnya."""
    try:
        return md.version(dist_name)
    except md.PackageNotFoundError:
        return None
    except Exception:
        return None


def section(title: str) -> None:
    print(f"\n{title}\n{'-' * len(title)}", flush=True)


def _vt(version: str | None) -> tuple[int, ...]:
    """('2.2.0' -> (2, 2, 0)); bagian non-numerik dipotong."""
    if not version:
        return ()
    parts: list[int] = []
    for chunk in version.split("+")[0].split("."):
        if chunk.isdigit():
            parts.append(int(chunk))
        else:
            break
    return tuple(parts)


# --------------------------------------------------------------------------
# 1. Interpreter
# --------------------------------------------------------------------------
def check_python() -> None:
    section("1. Interpreter")
    print(f"  python     : {sys.version.split()[0]}  ({sys.executable})")
    print(f"  platform   : {platform.platform()}")
    if sys.version_info[:2] in {(3, 11), (3, 12)}:
        record(PASS, "Versi Python",
               f"{sys.version_info.major}.{sys.version_info.minor} sesuai pyproject (>=3.11,<3.13)")
    else:
        record(WARN, "Versi Python",
               f"{sys.version_info.major}.{sys.version_info.minor} di luar 3.11/3.12 yang diuji")


# --------------------------------------------------------------------------
# 2. Versi paket
# --------------------------------------------------------------------------
def check_versions() -> dict[str, str | None]:
    section("2. Versi paket")
    found: dict[str, str | None] = {}
    for mod_name, dist_name in _PACKAGES:
        v = dist_version(dist_name)
        found[mod_name] = v
        if v is not None:
            print(f"  {dist_name:20s}: {v}")
    missing = [d for m, d in _PACKAGES if found[m] is None]
    if missing:
        print(f"  (tidak terpasang: {', '.join(missing)})")

    if found.get("sionna") is None:
        record(FAIL, "Sionna terpasang", "distribusi 'sionna' tidak ditemukan")
    else:
        record(PASS, "Sionna terpasang", found["sionna"] or "")
    return found


def is_legacy(found: dict[str, str | None]) -> bool:
    return _vt(found.get("sionna"))[:2] == (0, 19)


# --------------------------------------------------------------------------
# 3. Deteksi akselerator
# --------------------------------------------------------------------------
def check_gpu(found: dict[str, str | None]) -> None:
    section("3. Akselerator")
    legacy = is_legacy(found)

    if found.get("torch"):
        import torch
        if torch.cuda.is_available():
            record(PASS, "PyTorch CUDA",
                   f"{torch.__version__} (cuda {torch.version.cuda}) -> "
                   f"{torch.cuda.get_device_name(0)}, "
                   f"{torch.cuda.get_device_properties(0).total_memory / 1024**3:.1f} GB")
        else:
            record(FAIL, "PyTorch CUDA",
                   f"torch {torch.__version__} tidak melihat GPU "
                   f"(cuda build = {torch.version.cuda}). Build '+cpu' dari PyPI "
                   "adalah penyebab paling umum; pasang ulang dari index cu130 "
                   "(lihat envs/requirements-main.txt)")

    if found.get("tensorflow"):
        import tensorflow as tf
        gpus = tf.config.list_physical_devices("GPU")
        if gpus:
            record(PASS, "TensorFlow GPU", str(gpus))
        else:
            record(WARN, "TensorFlow GPU",
                   "TF tidak melihat GPU. Di Windows ini NORMAL dan diterima: "
                   "tidak ada dukungan GPU native sejak TF 2.11. E0 berjalan di "
                   "CPU; biayanya didominasi num_samples, bukan resolusi grid")

    # Dr.Jit: API has_backend() baru ada di drjit 1.x. Di 0.4.x (environment
    # validasi) memanggilnya justru melempar, jadi jangan dicoba.
    if found.get("drjit") and _vt(found["drjit"]) >= (1,):
        import drjit as dr
        try:
            has_cuda = bool(dr.has_backend(dr.JitBackend.CUDA))
            has_llvm = bool(dr.has_backend(dr.JitBackend.LLVM))
            record(PASS if has_cuda else FAIL, "Dr.Jit backend",
                   f"CUDA={has_cuda}, LLVM={has_llvm}"
                   + ("" if has_cuda else " — ray tracing akan sangat lambat"))
        except Exception as e:
            record(WARN, "Dr.Jit backend", f"tidak bisa diperiksa: {e}")
    elif found.get("drjit"):
        record(PASS, "Dr.Jit backend",
               f"drjit {found['drjit']} (0.4.x: dicek lewat varian Mitsuba di bagian 4)")

    if sys.platform == "win32" and legacy:
        if _LLVM_PATH:
            record(PASS, "LLVM-C.dll", _LLVM_PATH)
        else:
            record(FAIL, "LLVM-C.dll",
                   "tidak ditemukan di DRJIT_LIBLLVM_PATH maupun "
                   f"{os.path.join(sys.prefix, 'Library', 'bin')}. Sionna 0.19 "
                   "selalu memilih varian 'llvm_ad_rgb' di Windows dan import-nya "
                   "gagal total tanpa DLL ini. Lihat envs/requirements-v019.txt")


# --------------------------------------------------------------------------
# 4. Muat scene + hitung satu link Tx-Rx
# --------------------------------------------------------------------------
def check_ray_tracing(found: dict[str, str | None]) -> None:
    section("4. Ray tracing (muat scene + satu link Tx-Rx)")
    try:
        rt = importlib.import_module("sionna.rt")
    except Exception as e:
        record(FAIL, "Impor sionna.rt", f"{type(e).__name__}: {str(e)[:200]}")
        return

    import mitsuba as mi
    try:
        record(PASS, "Varian Mitsuba", mi.variant())
    except Exception as e:
        record(WARN, "Varian Mitsuba", str(e))

    scenes = [s for s in ("munich", "etoile", "florence", "san_francisco",
                          "simple_street_canyon") if hasattr(rt.scene, s)]
    record(PASS if scenes else FAIL, "Scene bawaan tersedia", ", ".join(scenes))
    if not scenes:
        return

    fc = 3.5e9  # hanya untuk uji asap; angka eksperimen ada di configs/base.yaml
    if is_legacy(found):
        _rt_legacy(rt, fc)
    else:
        _rt_modern(rt, fc)


def _rt_modern(rt, fc: float) -> None:
    """Sionna 2.x: PathSolver."""
    try:
        scene = rt.load_scene(rt.scene.munich, merge_shapes=True)
        scene.frequency = fc
        scene.tx_array = rt.PlanarArray(num_rows=1, num_cols=1,
                                        pattern="tr38901", polarization="V")
        scene.rx_array = rt.PlanarArray(num_rows=1, num_cols=1,
                                        pattern="dipole", polarization="V")
        scene.add(rt.Transmitter("tx", position=[8.5, 21.0, 27.0]))
        scene.add(rt.Receiver("rx", position=[45.0, 90.0, 1.5]))
        t0 = time.time()
        a, _ = rt.PathSolver()(scene, max_depth=3).cir(out_type="numpy")
        record(PASS, "compute paths (1 Tx-Rx)",
               f"{time.time() - t0:.2f}s, CIR {a.shape}")
    except Exception as e:
        record(FAIL, "compute paths (1 Tx-Rx)", f"{type(e).__name__}: {e}")
        return

    # Probe per-elemen. Inilah yang meledak di Fase 2 bila
    # max_num_paths_per_src dibiarkan default 1e6 (lihat docs/LOG.md).
    try:
        scene.tx_array = rt.PlanarArray(num_rows=12, num_cols=12,
                                        vertical_spacing=0.5,
                                        horizontal_spacing=0.5,
                                        pattern="iso", polarization="V")
        t0 = time.time()
        a, _ = rt.PathSolver()(scene, max_depth=3, samples_per_src=int(1e5),
                               max_num_paths_per_src=int(1e5),
                               synthetic_array=False).cir(out_type="numpy")
        record(PASS, "RIS per-elemen M=144",
               f"{time.time() - t0:.2f}s dengan max_num_paths_per_src=1e5, CIR {a.shape}")
    except Exception as e:
        record(FAIL, "RIS per-elemen M=144",
               f"{type(e).__name__}: {str(e)[:140]} | bebaskan VRAM atau turunkan "
               "max_num_paths_per_src / rx_batch_size")


def _rt_legacy(rt, fc: float) -> None:
    """Sionna 0.19.x: scene.compute_paths, plus cek model RIS bawaan."""
    try:
        scene = rt.load_scene(rt.scene.munich)
        scene.frequency = fc
        scene.synthetic_array = True
        for which in ("tx_array", "rx_array"):
            setattr(scene, which,
                    rt.PlanarArray(num_rows=1, num_cols=1, vertical_spacing=0.5,
                                   horizontal_spacing=0.5, pattern="iso",
                                   polarization="V"))
        scene.add(rt.Transmitter("tx", position=[8.5, 21.0, 27.0]))
        scene.add(rt.Receiver("rx", position=[45.0, 90.0, 1.5]))
        t0 = time.time()
        a, _ = scene.compute_paths(max_depth=3, num_samples=int(1e6),
                                   check_scene=False).cir()
        record(PASS, "compute paths (1 Tx-Rx)",
               f"{time.time() - t0:.2f}s, CIR {tuple(a.shape)}")
    except Exception as e:
        record(FAIL, "compute paths (1 Tx-Rx)", f"{type(e).__name__}: {e}")
        return

    # Satu-satunya alasan environment ini ada: model RIS bawaan untuk E0.
    if not hasattr(rt, "RIS"):
        record(FAIL, "RIS bawaan 0.19", "sionna.rt.RIS tidak ada")
        return
    try:
        ris = rt.RIS(name="ris", position=[30.0, 60.0, 6.0], num_rows=12,
                     num_cols=12, num_modes=1, look_at=[45.0, 90.0, 1.5])
        scene.add(ris)
        ris.focusing_lens([8.5, 21.0, 27.0], [45.0, 90.0, 1.5])
        size = [float(x) for x in ris.size.numpy()]
        record(PASS, "RIS bawaan 0.19",
               f"{int(ris.num_cells)} sel, {size[0]:.3f} x {size[1]:.3f} m")
    except Exception as e:
        record(FAIL, "RIS bawaan 0.19", f"{type(e).__name__}: {e}")


# --------------------------------------------------------------------------
# 5. Stack RL (hanya environment utama)
# --------------------------------------------------------------------------
def check_rl(found: dict[str, str | None]) -> None:
    if not found.get("gymnasium"):
        return
    section("5. Stack RL")
    try:
        import gymnasium  # noqa: F401
        import sb3_contrib  # noqa: F401
        import stable_baselines3 as sb3
        record(PASS, "Gymnasium + SB3 + sb3-contrib", f"sb3 {sb3.__version__}")
    except Exception as e:
        record(FAIL, "Gymnasium + SB3 + sb3-contrib", f"{type(e).__name__}: {e}")

    if not is_legacy(found):
        try:
            from sionna.phy import config as phy_config
            devices = list(phy_config.available_devices)
            if "cuda:0" in devices:
                phy_config.device = "cuda:0"   # ingat: "cuda" saja ditolak
                record(PASS, "sionna.phy device", f"{phy_config.device} dari {devices}")
            else:
                record(WARN, "sionna.phy device",
                       f"hanya {devices}; PHY akan berjalan di CPU")
        except Exception as e:
            record(WARN, "sionna.phy device", f"{type(e).__name__}: {e}")


# --------------------------------------------------------------------------
def main() -> int:
    argparse.ArgumentParser(description="Gate 0 environment check").parse_args()

    print("=" * 72)
    print("check_env.py — Gate 0 (docs/TASKS.md Fase 0)")
    print("=" * 72)

    check_python()
    found = check_versions()
    check_gpu(found)
    check_ray_tracing(found)
    check_rl(found)

    section("Ringkasan")
    n_fail = sum(1 for s, _, _ in _results if s == FAIL)
    n_warn = sum(1 for s, _, _ in _results if s == WARN)
    n_pass = sum(1 for s, _, _ in _results if s == PASS)
    print(f"  {n_pass} PASS, {n_warn} WARN, {n_fail} FAIL")
    for status, name, detail in _results:
        if status != PASS:
            print(f"  [{status}] {name} — {detail}")
    if n_fail:
        print("\nGATE 0: GAGAL")
        return 1
    print("\nGATE 0: LOLOS"
          + (" (dengan peringatan — catat di docs/LOG.md)" if n_warn else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
