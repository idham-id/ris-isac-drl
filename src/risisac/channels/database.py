"""Basis data kanal HDF5 (docs/EXPERIMENT_DESIGN.md §4.4).

Tata letak::

    data/channels/<scene_id>/<config_hash>.h5
      /static/G, /static/H, /static/Hc
      /meta/   (f_c, posisi dan orientasi BS/RIS, parameter RT, versi Sionna,
                hash config)
      /traj/<split>/<traj_id>/user_k/{pos, g, hd}
      /traj/<split>/<traj_id>/target_q/{pos, vel, g, hd_tx, hd_rx}

Environment RL **hanya membaca** file ini dan tidak mengimpor Sionna
(CLAUDE.md). Karena itu seluruh besaran yang dibutuhkan environment ikut
disimpan, termasuk ``in_roi`` dan kecepatan target.

Penulisan bersifat **bisa dilanjutkan**: tiap lintasan ditulis sebagai satu
grup yang baru ditandai ``complete`` setelah seluruh dataset-nya masuk, dan
``missing_trajectories`` melaporkan grup yang belum lengkap. Prakomputasi yang
terputus karena OOM atau listrik padam tinggal dijalankan ulang.

Kanal disimpan ``complex64`` (desain §3.1 "Kanal complex64"); posisi
``float32`` sudah lebih dari cukup untuk jarak meteran.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

CHANNEL_DTYPE = np.complex64
POSITION_DTYPE = np.float32

#: Ditandai pada grup lintasan yang seluruh dataset-nya sudah ditulis.
COMPLETE_ATTR = "complete"
#: Versi tata letak file; dinaikkan bila skema berubah agar file lama tertolak.
LAYOUT_VERSION = 1


def database_path(cfg: dict, config_hash: str, root: Path | str | None = None) -> Path:
    """``<paths.channel_db>/<scene_id>/<config_hash>.h5`` (§4.4)."""
    base = Path(root) if root is not None else Path(cfg["paths"]["channel_db"])
    return base / str(cfg["scene"]["id"]) / f"{config_hash}.h5"


def _traj_group_name(split: str, traj_id: int) -> str:
    return f"/traj/{split}/{int(traj_id):05d}"


@dataclass(frozen=True)
class TrajectoryChannels:
    """Kanal satu lintasan, siap ditulis atau baru dibaca.

    Bentuk array (T = jumlah langkah, M = elemen RIS, Nt/Nr = antena BS):

    =================  ===============  =================================
    medan              bentuk           arti
    =================  ===============  =================================
    ``user_pos``       (K, T, 3)        posisi pengguna
    ``user_g``         (K, T, M)        g_k : RIS -> pengguna k
    ``user_hd``        (K, T, Nt)       h_d,k : BS-tx -> pengguna k
    ``target_pos``     (Q, T, 3)        posisi target
    ``target_vel``     (Q, T, 3)        kecepatan target [m/s]
    ``target_in_roi``  (Q, T)           bool; episode terpotong saat False
    ``target_g``       (Q, T, M)        g_t : RIS <-> target (resiprokal)
    ``target_hd_tx``   (Q, T, Nt)       h_d,t : BS-tx -> target
    ``target_hd_rx``   (Q, T, Nr)       h^(r)_d,t : target -> BS-rx
    =================  ===============  =================================
    """

    traj_id: int
    user_pos: np.ndarray
    user_g: np.ndarray
    user_hd: np.ndarray
    target_pos: np.ndarray
    target_vel: np.ndarray
    target_in_roi: np.ndarray
    target_g: np.ndarray
    target_hd_tx: np.ndarray
    target_hd_rx: np.ndarray
    target_speed_mps: np.ndarray

    def validate(self) -> None:
        """Periksa bentuk yang saling konsisten dan ketiadaan NaN/Inf."""
        k, t = self.user_pos.shape[0], self.user_pos.shape[1]
        q = self.target_pos.shape[0]
        expect = {
            "user_pos": (k, t, 3), "user_g": (k, t, self.user_g.shape[-1]),
            "user_hd": (k, t, self.user_hd.shape[-1]),
            "target_pos": (q, t, 3), "target_vel": (q, t, 3),
            "target_in_roi": (q, t),
            "target_g": (q, t, self.user_g.shape[-1]),
            "target_hd_tx": (q, t, self.user_hd.shape[-1]),
            "target_hd_rx": (q, t, self.target_hd_rx.shape[-1]),
        }
        for name, shape in expect.items():
            got = getattr(self, name).shape
            if got != shape:
                raise ValueError(f"{name}: bentuk {got}, diharapkan {shape}")
        for name in ("user_g", "user_hd", "target_g", "target_hd_tx",
                     "target_hd_rx", "user_pos", "target_pos", "target_vel"):
            arr = getattr(self, name)
            if not np.all(np.isfinite(arr)):
                raise ValueError(f"{name}: mengandung NaN atau Inf")


def write_static(path: Path | str, G: np.ndarray, H: np.ndarray,
                 Hc: np.ndarray, meta: dict) -> None:
    """Tulis kanal statis dan metadata; membuat file bila belum ada."""
    import h5py

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with h5py.File(path, "a") as fh:
        grp = fh.require_group("static")
        for name, arr in (("G", G), ("H", H), ("Hc", Hc)):
            if name in grp:
                del grp[name]
            grp.create_dataset(name, data=np.asarray(arr, dtype=CHANNEL_DTYPE))
        mgrp = fh.require_group("meta")
        mgrp.attrs["layout_version"] = LAYOUT_VERSION
        for key, value in meta.items():
            mgrp.attrs[key] = (json.dumps(value, default=str)
                               if isinstance(value, (dict, list, tuple))
                               else value)


def read_static(path: Path | str) -> tuple[np.ndarray, np.ndarray, np.ndarray, dict]:
    import h5py

    with h5py.File(path, "r") as fh:
        version = int(fh["meta"].attrs.get("layout_version", 0))
        if version != LAYOUT_VERSION:
            raise ValueError(
                f"{path}: layout_version {version}, kode ini menulis "
                f"{LAYOUT_VERSION}. Hapus file dan prakomputasi ulang.")
        g = np.asarray(fh["static/G"])
        h = np.asarray(fh["static/H"])
        hc = np.asarray(fh["static/Hc"])
        meta = dict(fh["meta"].attrs)
    return g, h, hc, meta


def write_trajectory(path: Path | str, split: str,
                     channels: TrajectoryChannels) -> None:
    """Tulis satu lintasan secara atomik dari sudut pandang pembaca.

    Atribut ``complete`` baru ditulis setelah seluruh dataset masuk, sehingga
    lintasan yang separuh tertulis (misalnya karena proses dimatikan) terbaca
    sebagai hilang dan akan dihitung ulang, bukan terbaca sebagai data sah.
    """
    import h5py

    channels.validate()
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    name = _traj_group_name(split, channels.traj_id)
    with h5py.File(path, "a") as fh:
        if name in fh:
            del fh[name]
        grp = fh.create_group(name)
        grp.attrs[COMPLETE_ATTR] = False
        grp.attrs["traj_id"] = int(channels.traj_id)

        for k in range(channels.user_pos.shape[0]):
            sub = grp.create_group(f"user_{k}")
            sub.create_dataset("pos", data=channels.user_pos[k].astype(POSITION_DTYPE))
            sub.create_dataset("g", data=channels.user_g[k].astype(CHANNEL_DTYPE))
            sub.create_dataset("hd", data=channels.user_hd[k].astype(CHANNEL_DTYPE))

        for q in range(channels.target_pos.shape[0]):
            sub = grp.create_group(f"target_{q}")
            sub.create_dataset("pos", data=channels.target_pos[q].astype(POSITION_DTYPE))
            sub.create_dataset("vel", data=channels.target_vel[q].astype(POSITION_DTYPE))
            sub.create_dataset("in_roi", data=channels.target_in_roi[q].astype(bool))
            sub.create_dataset("g", data=channels.target_g[q].astype(CHANNEL_DTYPE))
            sub.create_dataset("hd_tx", data=channels.target_hd_tx[q].astype(CHANNEL_DTYPE))
            sub.create_dataset("hd_rx", data=channels.target_hd_rx[q].astype(CHANNEL_DTYPE))
            sub.attrs["speed_mps"] = float(channels.target_speed_mps[q])

        grp.attrs[COMPLETE_ATTR] = True


def read_trajectory(path: Path | str, split: str, traj_id: int) -> TrajectoryChannels:
    import h5py

    name = _traj_group_name(split, traj_id)
    with h5py.File(path, "r") as fh:
        if name not in fh or not bool(fh[name].attrs.get(COMPLETE_ATTR, False)):
            raise KeyError(f"{path}: lintasan {split}/{traj_id} belum lengkap.")
        grp = fh[name]
        users = sorted(k for k in grp if k.startswith("user_"))
        targets = sorted(k for k in grp if k.startswith("target_"))
        return TrajectoryChannels(
            traj_id=int(traj_id),
            user_pos=np.stack([np.asarray(grp[f"{u}/pos"]) for u in users]),
            user_g=np.stack([np.asarray(grp[f"{u}/g"]) for u in users]),
            user_hd=np.stack([np.asarray(grp[f"{u}/hd"]) for u in users]),
            target_pos=np.stack([np.asarray(grp[f"{t}/pos"]) for t in targets]),
            target_vel=np.stack([np.asarray(grp[f"{t}/vel"]) for t in targets]),
            target_in_roi=np.stack([np.asarray(grp[f"{t}/in_roi"]) for t in targets]),
            target_g=np.stack([np.asarray(grp[f"{t}/g"]) for t in targets]),
            target_hd_tx=np.stack([np.asarray(grp[f"{t}/hd_tx"]) for t in targets]),
            target_hd_rx=np.stack([np.asarray(grp[f"{t}/hd_rx"]) for t in targets]),
            target_speed_mps=np.asarray(
                [float(grp[t].attrs["speed_mps"]) for t in targets]),
        )


def completed_trajectories(path: Path | str, split: str) -> set[int]:
    """Id lintasan yang sudah lengkap di file (kosong bila file belum ada)."""
    import h5py

    path = Path(path)
    if not path.exists():
        return set()
    out: set[int] = set()
    with h5py.File(path, "r") as fh:
        grp = fh.get(f"/traj/{split}")
        if grp is None:
            return out
        for key in grp:
            if bool(grp[key].attrs.get(COMPLETE_ATTR, False)):
                out.add(int(grp[key].attrs["traj_id"]))
    return out


def missing_trajectories(path: Path | str, split: str, total: int) -> list[int]:
    """Lintasan yang masih harus dihitung, berurutan."""
    done = completed_trajectories(path, split)
    return [i for i in range(int(total)) if i not in done]
