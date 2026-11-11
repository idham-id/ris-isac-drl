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
    max_paths_total: int
    specular_reflection: bool
    diffuse_reflection: bool
    diffraction: bool
    refraction: bool
    synthetic_array: bool
    rx_batch_size: int
    deterministic: bool = True
    seed: int = 42

    @classmethod
    def from_config(cls, cfg: dict) -> "RayTracingSettings":
        r = cfg["ray_tracing"]
        return cls(
            max_depth=int(r["max_depth"]),
            samples_per_src=int(r["samples_per_src"]),
            # Default Sionna 1e6. Nilai terlalu rendah MEMOTONG jalur dan
            # membiaskan koefisien tanpa error apa pun (docs/LOG.md 2026-11-11).
            max_num_paths_per_src=int(r.get("max_num_paths_per_src", 1_000_000)),
            max_paths_total=int(r.get("max_paths_total", 0)),
            specular_reflection=bool(r["specular_reflection"]),
            diffuse_reflection=bool(r["diffuse_reflection"]),
            diffraction=bool(r["diffraction"]),
            refraction=bool(r.get("refraction", False)),
            synthetic_array=not bool(r["ris_per_element"]),
            rx_batch_size=int(r["rx_batch_size"]),
            deterministic=bool(r.get("deterministic", True)),
            seed=int(r.get("seed", 42)),
        )

    def paths_budget(self, num_sources: int) -> int:
        """Anggaran jalur per sumber yang masih muat di VRAM.

        Buffer image-method berukuran ``max_num_paths_per_src * num_sources
        * 16 B`` dan TIDAK mengecil bila ``rx_batch_size`` diturunkan
        (docs/LOG.md 2026-11-11). Yang terbatas karena itu adalah HASIL KALI,
        bukan nilai per sumber -- sehingga satu nilai tetap di config akan
        selalu salah untuk salah satu sisi: cukup longgar bagi kanal langsung
        (8 sumber) berarti OOM bagi kanal RIS per-elemen (64 sumber), dan yang
        muat bagi 64 sumber MEMOTONG kanal langsung sampai 50 dB tanpa error
        apa pun (konvergensi diukur, docs/LOG.md 2026-11-11 (f)).

        ``max_paths_total`` karena itu menetapkan anggaran total; nilai per
        sumber diturunkan darinya. ``max_paths_total = 0`` mematikan mekanisme
        ini dan memakai nilai per sumber apa adanya.
        """
        if self.max_paths_total <= 0:
            return self.max_num_paths_per_src
        return max(1, min(self.max_num_paths_per_src,
                          self.max_paths_total // max(1, int(num_sources))))


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

    # Jumlah sumber ray tracing: satu per antena pancar bila array per-elemen.
    num_sources = 1 if settings.synthetic_array else int(tx_array.num_ant)
    paths_per_src = settings.paths_budget(num_sources)

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

        a, _ = rt.PathSolver(deterministic=settings.deterministic)(
            scene,
            max_depth=settings.max_depth,
            samples_per_src=settings.samples_per_src,
            max_num_paths_per_src=paths_per_src,
            synthetic_array=settings.synthetic_array,
            specular_reflection=settings.specular_reflection,
            diffuse_reflection=settings.diffuse_reflection,
            diffraction=settings.diffraction,
            refraction=settings.refraction,
            seed=settings.seed,
            # WAJIB False. Default Sionna adalah True, yang menggeser tundaan
            # tiap PASANGAN PERANGKAT sehingga jalur pertamanya tiba di t = 0 --
            # dan ikut MENGHAPUS fasa propagasi dari koefisien: untuk link LoS
            # fasanya menjadi tepat nol. Fasa relatif antar-elemen dalam satu
            # pemanggilan tetap benar (offset-nya sama untuk semua elemen),
            # sehingga profil fokus tetap bekerja dan kesalahan ini TIDAK
            # terlihat pada peta cakupan. Yang rusak adalah fasa relatif
            # ANTAR-pemanggilan, yaitu persis yang dibutuhkan penjumlahan
            # koheren h_e = h_d + g^T Theta G (E2) dan c = h_d,t + g_t^T Theta G
            # (E5). Ditemukan oleh uji fasa E0 (docs/LOG.md 2026-11-11 (g)).
            ).cir(out_type="numpy", normalize_delays=False)

        # a: (num_rx, num_rx_ant, num_tx, num_tx_ant, num_paths, num_time_steps)
        coeff = a[:, :, 0, :, :, 0].sum(axis=-1)      # (n_chunk, num_rx_ant, num_tx_ant)
        out.append(np.asarray(coeff, dtype=np.complex128))
        if progress:
            print(f"    batch {b + 1}/{n_batches} ({len(chunk)} rx)", flush=True)

    _clear_devices(scene)
    return np.concatenate(out, axis=0)


def clutter_channel(scene, tx_array, rx_array, tx_position, rx_position,
                    settings: RayTracingSettings,
                    tx_look_at=None, rx_look_at=None) -> np.ndarray:
    """Kanal clutter monostatik **H**_c, jalur LoS tx-rx dibuang (§3.5).

    Ray tracing BS-tx -> lingkungan -> BS-rx. Jalur LoS antara kedua panel BS
    harus dibuang karena itu bukan clutter melainkan kebocoran tx->rx, dan
    desain §3.7 butir 2 menyatakan isolasi tx/rx dianggap cukup sehingga
    self-interference tidak dimodelkan. Panel hanya terpisah 0,5 m, jadi jalur
    itu puluhan dB lebih kuat daripada seluruh clutter dan akan mendominasi
    **R**_cn bila ikut terjumlah.

    Pembuangannya memakai ``Paths.interactions``, bukan ambang tundaan: jalur
    LoS adalah satu-satunya jalur yang seluruh kedalamannya bertipe
    ``InteractionType.NONE``. Memakai tundaan akan rapuh terhadap
    ``normalize_delays`` dan terhadap geometri yang kebetulan berdekatan.

    :returns: (num_rx_ant, num_tx_ant) complex128
    """
    import sionna.rt as rt
    from sionna.rt.constants import InteractionType

    scene.tx_array = tx_array
    scene.rx_array = rx_array
    num_sources = 1 if settings.synthetic_array else int(tx_array.num_ant)

    _clear_devices(scene)
    scene.add(rt.Transmitter(
        "tx", position=[float(v) for v in np.asarray(tx_position, float).reshape(3)],
        **({"look_at": [float(v) for v in tx_look_at]} if tx_look_at is not None else {})))
    scene.add(rt.Receiver(
        "rx", position=[float(v) for v in np.asarray(rx_position, float).reshape(3)],
        **({"look_at": [float(v) for v in rx_look_at]} if rx_look_at is not None else {})))

    paths = rt.PathSolver(deterministic=settings.deterministic)(
        scene,
        max_depth=settings.max_depth,
        samples_per_src=settings.samples_per_src,
        max_num_paths_per_src=settings.paths_budget(num_sources),
        synthetic_array=settings.synthetic_array,
        specular_reflection=settings.specular_reflection,
        diffuse_reflection=settings.diffuse_reflection,
        diffraction=settings.diffraction,
        refraction=settings.refraction,
        seed=settings.seed,
    )
    a, _ = paths.cir(out_type="numpy", normalize_delays=False)
    # Bentuk ``interactions`` BERGANTUNG mode array (docstring Sionna 2.2):
    #   per elemen  : (max_depth, num_rx, num_rx_ant, num_tx, num_tx_ant, num_paths)
    #   synthetic   : (max_depth, num_rx, num_tx, num_paths)
    # Pada mode per elemen himpunan jalur bisa berbeda antar pasangan antena,
    # jadi mask LoS tidak boleh diambil dari satu pasangan lalu dipakai ulang.
    inter = np.asarray(paths.interactions)
    none_all = np.all(inter == int(InteractionType.NONE), axis=0)
    if none_all.ndim == 5:
        is_los = none_all[0, :, 0, :, :]              # (Nr, Nt, num_paths)
    elif none_all.ndim == 3:
        is_los = none_all[0, 0][None, None, :]        # (1, 1, num_paths)
    else:
        raise RuntimeError(
            f"clutter_channel: bentuk interactions tak dikenal {inter.shape}")
    _clear_devices(scene)

    # a: (num_rx, num_rx_ant, num_tx, num_tx_ant, num_paths, num_time_steps)
    coeff = a[0, :, 0, :, :, 0]                       # (Nr, Nt, num_paths)
    if is_los.shape[-1] != coeff.shape[-1]:
        raise RuntimeError(
            f"clutter_channel: jumlah jalur tidak cocok antara interactions "
            f"({is_los.shape[-1]}) dan cir ({coeff.shape[-1]}).")
    return np.asarray(np.where(is_los, 0.0, coeff).sum(axis=-1),
                      dtype=np.complex128)
