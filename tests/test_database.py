"""Basis data kanal HDF5 (docs/EXPERIMENT_DESIGN.md §4.4).

Yang diuji di sini adalah sifat yang membuat prakomputasi aman dijalankan
ulang: bisa dilanjutkan, lintasan separuh tertulis tidak terbaca sebagai sah,
dan bentuk/dtype yang dipakai environment RL tidak berubah diam-diam.
"""

import sys
from pathlib import Path

import numpy as np
import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from risisac.channels.database import (CHANNEL_DTYPE,                 # noqa: E402
                                       COMPLETE_ATTR, LAYOUT_VERSION,
                                       TrajectoryChannels,
                                       completed_trajectories,
                                       database_path,
                                       missing_trajectories,
                                       read_static, read_trajectory,
                                       write_static, write_trajectory)

K, Q, T, M, NT, NR = 2, 1, 5, 8, 4, 4


def make_channels(traj_id: int = 0, rng=None) -> TrajectoryChannels:
    rng = rng or np.random.default_rng(traj_id)

    def c(*shape):
        return (rng.normal(size=shape) + 1j * rng.normal(size=shape)).astype(complex)

    return TrajectoryChannels(
        traj_id=traj_id,
        user_pos=rng.normal(size=(K, T, 3)),
        user_g=c(K, T, M), user_hd=c(K, T, NT),
        target_pos=rng.normal(size=(Q, T, 3)),
        target_vel=rng.normal(size=(Q, T, 3)),
        target_in_roi=np.ones((Q, T), dtype=bool),
        target_g=c(Q, T, M), target_hd_tx=c(Q, T, NT), target_hd_rx=c(Q, T, NR),
        target_speed_mps=np.array([5.0]),
    )


@pytest.fixture
def db(tmp_path):
    return tmp_path / "chan.h5"


def test_tulis_baca_statis(db):
    G = np.ones((M, NT), dtype=complex)
    H = np.ones((NR, M), dtype=complex) * 2.0
    Hc = np.eye(NR, NT, dtype=complex)
    write_static(db, G, H, Hc, {"config_hash": "abc", "carrier_frequency_hz": 3.5e9})
    g, h, hc, meta = read_static(db)
    assert g.shape == (M, NT) and h.shape == (NR, M) and hc.shape == (NR, NT)
    assert g.dtype == CHANNEL_DTYPE
    assert meta["config_hash"] == "abc"
    assert int(meta["layout_version"]) == LAYOUT_VERSION


def test_tulis_baca_lintasan(db):
    ch = make_channels(3)
    write_trajectory(db, "val", ch)
    got = read_trajectory(db, "val", 3)
    assert got.traj_id == 3
    for name in ("user_g", "user_hd", "target_g", "target_hd_tx", "target_hd_rx"):
        assert getattr(got, name).shape == getattr(ch, name).shape
        assert np.allclose(getattr(got, name), getattr(ch, name), atol=1e-6)
    assert np.allclose(got.target_pos, ch.target_pos, atol=1e-5)
    assert got.target_speed_mps == pytest.approx(ch.target_speed_mps)


def test_bisa_dilanjutkan(db):
    for i in (0, 1, 4):
        write_trajectory(db, "train", make_channels(i))
    assert completed_trajectories(db, "train") == {0, 1, 4}
    assert missing_trajectories(db, "train", 6) == [2, 3, 5]
    assert missing_trajectories(db, "val", 3) == [0, 1, 2]


def test_file_belum_ada_berarti_semua_hilang(tmp_path):
    assert missing_trajectories(tmp_path / "tidak_ada.h5", "train", 4) == [0, 1, 2, 3]


def test_lintasan_separuh_tertulis_dianggap_hilang(db):
    """Proses yang mati di tengah tidak boleh meninggalkan data yang terbaca sah."""
    import h5py

    write_trajectory(db, "val", make_channels(0))
    with h5py.File(db, "a") as fh:
        fh["/traj/val/00000"].attrs[COMPLETE_ATTR] = False
    assert completed_trajectories(db, "val") == set()
    assert missing_trajectories(db, "val", 1) == [0]
    with pytest.raises(KeyError):
        read_trajectory(db, "val", 0)


def test_tulis_ulang_mengganti_bukan_menggandakan(db):
    write_trajectory(db, "val", make_channels(0, np.random.default_rng(1)))
    second = make_channels(0, np.random.default_rng(2))
    write_trajectory(db, "val", second)
    assert np.allclose(read_trajectory(db, "val", 0).user_g, second.user_g, atol=1e-6)


def test_layout_version_lama_ditolak(db):
    import h5py

    write_static(db, np.ones((M, NT), complex), np.ones((NR, M), complex),
                 np.ones((NR, NT), complex), {})
    with h5py.File(db, "a") as fh:
        fh["meta"].attrs["layout_version"] = LAYOUT_VERSION + 1
    with pytest.raises(ValueError, match="layout_version"):
        read_static(db)


def test_validate_menolak_nan(db):
    ch = make_channels(0)
    ch.user_g[0, 0, 0] = np.nan
    with pytest.raises(ValueError, match="NaN"):
        write_trajectory(db, "val", ch)


def test_validate_menolak_bentuk_tidak_cocok():
    ch = make_channels(0)
    bad = TrajectoryChannels(**{**ch.__dict__, "target_vel": np.zeros((Q, T + 1, 3))})
    with pytest.raises(ValueError, match="target_vel"):
        bad.validate()


def test_database_path_mengikuti_desain():
    cfg = {"paths": {"channel_db": "data/channels"}, "scene": {"id": "synthetic_l"}}
    p = database_path(cfg, "deadbeef")
    assert p.parts[-3:] == ("data", "synthetic_l", "deadbeef.h5") or \
        p.as_posix().endswith("data/channels/synthetic_l/deadbeef.h5")
