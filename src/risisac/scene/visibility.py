"""Pemeriksaan visibilitas garis pandang (LoS).

docs/TASKS.md Fase 1: "Fungsi cek visibilitas LoS (jalur kedalaman 0)".

Implementasinya memakai uji oklusi Mitsuba (``ray_test``) dan bukan
``PathSolver(max_depth=0)``. Keduanya menjawab pertanyaan yang sama — adakah
geometri yang menghalangi segmen antara dua titik — tetapi ``ray_test`` bersifat
deterministik (tidak bergantung jumlah sampel) dan ribuan kali lebih murah,
sehingga grid ROI puluhan ribu titik bisa diuji seketika.

``verify_against_path_solver`` membandingkan keduanya pada subhimpunan titik,
sehingga klaim kesetaraan itu diuji, bukan diasumsikan.
"""

from __future__ import annotations

import numpy as np


def los_mask(scene, origin, targets, eps: float = 1e-3) -> np.ndarray:
    """True untuk tiap target yang punya LoS dari ``origin``.

    :param scene: ``sionna.rt.Scene``
    :param origin: (3,) titik asal
    :param targets: (N, 3) titik tujuan
    :param eps: mundur sedikit dari kedua ujung agar permukaan tempat
        perangkat menempel tidak terhitung sebagai penghalang
    """
    import mitsuba as mi

    o = np.asarray(origin, dtype=np.float64).reshape(3)
    t = np.asarray(targets, dtype=np.float64).reshape(-1, 3)
    if len(t) == 0:
        return np.zeros(0, dtype=bool)

    d = t - o[None, :]
    dist = np.linalg.norm(d, axis=1)
    safe = np.maximum(dist, 1e-12)
    dn = d / safe[:, None]
    n = len(t)

    ray = mi.Ray3f(
        o=mi.Point3f(np.full(n, o[0]), np.full(n, o[1]), np.full(n, o[2])),
        d=mi.Vector3f(dn[:, 0], dn[:, 1], dn[:, 2]),
    )
    ray.o = ray.o + ray.d * eps
    ray.maxt = mi.Float(np.maximum(dist - 2.0 * eps, 0.0))
    blocked = np.array(scene.mi_scene.ray_test(ray))
    # Titik yang berimpit dengan origin dianggap terlihat.
    return (~blocked) | (dist <= 2.0 * eps)


def los_fraction(scene, origin, targets, eps: float = 1e-3) -> float:
    """Fraksi target yang punya LoS dari ``origin`` (0..1)."""
    mask = los_mask(scene, origin, targets, eps=eps)
    return float(mask.mean()) if len(mask) else float("nan")


def verify_against_path_solver(scene, origin, targets,
                               samples_per_src: int = int(1e6)) -> dict:
    """Bandingkan ``los_mask`` dengan ``PathSolver(max_depth=0)``.

    Mengubah daftar penerima pada ``scene`` yang diberikan, jadi pakailah scene
    sekali pakai. Mengembalikan dict berisi kedua mask dan jumlah ketidakcocokan.
    """
    import sionna.rt as rt

    targets = np.asarray(targets, dtype=float).reshape(-1, 3)
    mask = los_mask(scene, origin, targets)

    for name in list(scene.receivers.keys()):
        scene.remove(name)
    for name in list(scene.transmitters.keys()):
        scene.remove(name)
    scene.add(rt.Transmitter("los_probe_tx", position=[float(v) for v in origin]))
    for i, p in enumerate(targets):
        scene.add(rt.Receiver(f"los_probe_rx{i}", position=[float(v) for v in p]))

    a, _ = rt.PathSolver()(scene, max_depth=0,
                           samples_per_src=samples_per_src).cir(out_type="numpy")
    # a: (num_rx, num_rx_ant, num_tx, num_tx_ant, num_paths, num_time_steps)
    power = np.sum(np.abs(a) ** 2, axis=tuple(range(1, a.ndim)))
    solver_mask = power > 0.0

    return {
        "ray_test": mask,
        "path_solver": solver_mask,
        "num_mismatch": int(np.sum(mask != solver_mask)),
        "num_points": int(len(targets)),
    }
