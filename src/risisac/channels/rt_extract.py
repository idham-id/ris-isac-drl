"""Ekstraksi koefisien kanal pita sempit dari Sionna RT.

docs/EXPERIMENT_DESIGN.md §4.2. Di Fase 1 modul ini baru menyediakan primitif
yang dipakai peta cakupan E1; Fase 2 memperluasnya ke lintasan dan basis data
HDF5.

Semua kanal adalah koefisien baseband pita sempit pada f_c, yaitu penjumlahan
koefisien seluruh jalur dari CIR Sionna (desain §3.1).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class RayTracingSettings:
    """Setelan solver, seluruhnya dari ``cfg['ray_tracing']``."""

    max_depth: int
    samples_per_src: int
    max_num_paths_per_src: int
    specular_reflection: bool
    diffuse_reflection: bool
    diffraction: bool
    synthetic_array: bool
    rx_batch_size: int

    @classmethod
    def from_config(cls, cfg: dict) -> "RayTracingSettings":
        r = cfg["ray_tracing"]
        return cls(
            max_depth=int(r["max_depth"]),
            samples_per_src=int(r["samples_per_src"]),
            # Default Sionna 1e6. Nilai terlalu rendah MEMOTONG jalur dan
            # membiaskan koefisien tanpa error apa pun (docs/LOG.md 2026-11-11).
            max_num_paths_per_src=int(r.get("max_num_paths_per_src", 1_000_000)),
            specular_reflection=bool(r["specular_reflection"]),
            diffuse_reflection=bool(r["diffuse_reflection"]),
            diffraction=bool(r["diffraction"]),
            synthetic_array=not bool(r["ris_per_element"]),
            rx_batch_size=int(r["rx_batch_size"]),
        )

    def for_array_size(self, num_tx_ant: int) -> "RayTracingSettings":
        """Perkecil batch dan anggaran jalur untuk array besar.

        Dengan array per-elemen jumlah sumber ray tracing sama dengan jumlah
        antena pancar, sehingga memori tumbuh linear terhadapnya. Nilai di sini
        berasal dari pengukuran di GPU 12 GB (docs/LOG.md 2026-11-10 butir 2).
        """
        if self.synthetic_array or num_tx_ant <= 144:
            return self
        return RayTracingSettings(
            **{**self.__dict__,
               "max_num_paths_per_src": min(self.max_num_paths_per_src, 50_000),
               "rx_batch_size": min(self.rx_batch_size, 128)},
        )


def release_gpu_memory() -> None:
    """Lepas cache alokasi Dr.Jit di antara pemanggilan ray tracing.

    Buffer image-method berukuran max_num_paths_per_src * jumlah_sumber * 16 B
    (M = 64 dengan 1e6 jalur = tepat 1 GiB) dan TIDAK mengecil bila
    rx_batch_size diturunkan. Tanpa pelepasan ini, sisa cache dari pemanggilan
    sebelumnya membuat alokasi berikutnya gagal meski VRAM total mencukupi.
    """
    try:
        import drjit as dr
        dr.flush_malloc_cache()
    except Exception:       # backend CPU / versi lama: tidak ada yang dilepas
        pass


def _clear_devices(scene) -> None:
    for name in list(scene.transmitters.keys()):
        scene.remove(name)
    for name in list(scene.receivers.keys()):
        scene.remove(name)


def narrowband_coefficients(scene, tx_array, rx_array, tx_position, rx_positions,
                            settings: RayTracingSettings,
                            tx_look_at=None, rx_look_at=None,
                            progress: bool = False) -> np.ndarray:
    """Koefisien kanal pita sempit dari satu pemancar ke banyak penerima.

    :returns: (N_rx, num_rx_ant, num_tx_ant) complex128
    """
    import sionna.rt as rt

    rx_positions = np.asarray(rx_positions, dtype=float).reshape(-1, 3)
    scene.tx_array = tx_array
    scene.rx_array = rx_array

    out: list[np.ndarray] = []
    batch = max(1, settings.rx_batch_size)
    n_batches = (len(rx_positions) + batch - 1) // batch

    for b in range(n_batches):
        chunk = rx_positions[b * batch:(b + 1) * batch]
        _clear_devices(scene)
        scene.add(rt.Transmitter(
            "tx", position=[float(v) for v in tx_position],
            **({"look_at": [float(v) for v in tx_look_at]} if tx_look_at is not None else {})))
        for i, p in enumerate(chunk):
            scene.add(rt.Receiver(
                f"rx{i}", position=[float(v) for v in p],
                **({"look_at": [float(v) for v in rx_look_at]} if rx_look_at is not None else {})))

        a, _ = rt.PathSolver()(
            scene,
            max_depth=settings.max_depth,
            samples_per_src=settings.samples_per_src,
            max_num_paths_per_src=settings.max_num_paths_per_src,
            synthetic_array=settings.synthetic_array,
            specular_reflection=settings.specular_reflection,
            diffuse_reflection=settings.diffuse_reflection,
            diffraction=settings.diffraction,
        ).cir(out_type="numpy")

        # a: (num_rx, num_rx_ant, num_tx, num_tx_ant, num_paths, num_time_steps)
        coeff = a[:, :, 0, :, :, 0].sum(axis=-1)      # (n_chunk, num_rx_ant, num_tx_ant)
        out.append(np.asarray(coeff, dtype=np.complex128))
        if progress:
            print(f"    batch {b + 1}/{n_batches} ({len(chunk)} rx)", flush=True)

    _clear_devices(scene)
    return np.concatenate(out, axis=0)
