"""Sifat fisik basis data kanal yang sudah diprakomputasi (Fase 2).

Berkas ini membaca `data/channels/...` dan **dilewati** bila prakomputasi
belum dijalankan, supaya `pytest -q` tetap hijau di mesin yang bersih. Yang
diuji adalah premis proyek di data yang benar-benar akan dipakai environment
RL -- bukan di grid E1 yang terpisah.
"""

import sys
from pathlib import Path

import numpy as np
import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from risisac.channels.database import (completed_trajectories,        # noqa: E402
                                       database_path, read_static,
                                       read_trajectory)
from risisac.config import config_hash, load_config                   # noqa: E402
from risisac.system.signal_model import (cascaded_coefficient,        # noqa: E402
                                         focus_phases, to_db)


@pytest.fixture(scope="module")
def db():
    cfg = load_config("base")
    path = database_path(cfg, config_hash(cfg), root=REPO / cfg["paths"]["channel_db"])
    if not path.exists():
        pytest.skip(f"basis data kanal belum ada: {path} "
                    "(jalankan scripts/precompute_channels.py)")
    return cfg, path


def test_statis_bentuk_dan_hingga(db):
    cfg, path = db
    G, H, Hc, meta = read_static(path)
    m = int(cfg["radio"]["ris"]["num_rows"]) * int(cfg["radio"]["ris"]["num_cols"])
    nt, nr = int(cfg["radio"]["bs"]["num_tx"]), int(cfg["radio"]["bs"]["num_rx"])
    assert G.shape == (m, nt) and H.shape == (nr, m) and Hc.shape == (nr, nt)
    assert all(np.all(np.isfinite(x)) for x in (G, H, Hc))
    assert np.all(np.abs(G) > 0) and np.all(np.abs(H) > 0)


def test_clutter_tidak_nol_di_scene_utama(db):
    """Di scene bergedung **H**_c harus ada; nol berarti jalur ikut terbuang."""
    _, path = db
    _, _, Hc, _ = read_static(path)
    assert np.max(np.abs(Hc)) > 0.0


def test_semua_split_lengkap(db):
    cfg, path = db
    for split, expected in cfg["mobility"]["num_trajectories"].items():
        done = completed_trajectories(path, split)
        if not done:
            pytest.skip(f"split '{split}' belum diprakomputasi")
        assert done == set(range(int(expected))), \
            f"split '{split}': {len(done)} dari {expected} lintasan"


def test_jalur_ris_terfokus_jauh_mengungguli_jalur_langsung(db):
    """Premis proyek, diuji di data lintasan (§2.1, Gate 1 kriteria 5).

    Dibandingkan pada precoder yang SAMA (vektor singular kanan utama G),
    sehingga yang diukur betul-betul selisih jalur, bukan selisih beamforming.
    """
    cfg, path = db
    G, _, _, _ = read_static(path)
    _, _, vh = np.linalg.svd(G, full_matrices=False)
    a_bar = np.conj(vh[0])
    a_bar /= np.linalg.norm(a_bar)
    u = G @ a_bar

    margins = []
    for traj_id in sorted(completed_trajectories(path, "val"))[:5]:
        tr = read_trajectory(path, "val", traj_id)
        for g, hd in ((tr.user_g, tr.user_hd), (tr.target_g, tr.target_hd_tx)):
            g2 = g.reshape(-1, g.shape[-1])
            hd2 = hd.reshape(-1, hd.shape[-1])
            phi = focus_phases(u[None, :], g2)
            cascade = np.abs(cascaded_coefficient(u[None, :], g2, phi)) ** 2
            direct = np.abs(hd2 @ a_bar) ** 2
            margins.append(np.median(to_db(cascade) - to_db(direct)))
    assert min(margins) > 10.0, f"margin terkecil {min(margins):.1f} dB"


def test_tidak_ada_nan_di_lintasan(db):
    _, path = db
    for split in ("val", "test"):
        done = sorted(completed_trajectories(path, split))
        if not done:
            continue
        tr = read_trajectory(path, split, done[0])
        for name in ("user_g", "user_hd", "target_g", "target_hd_tx",
                     "target_hd_rx", "user_pos", "target_pos", "target_vel"):
            arr = getattr(tr, name)
            assert np.all(np.isfinite(arr)), name
        assert np.all(np.abs(tr.user_g) > 0)


def test_in_roi_konsisten_dengan_posisi(db):
    """Data yang dibaca environment harus cocok dengan geometri ROI config."""
    cfg, path = db
    poly = np.asarray(cfg["scene"]["roi"]["polygon"], float)
    xmin, xmax = poly[:, 0].min(), poly[:, 0].max()
    ymin, ymax = poly[:, 1].min(), poly[:, 1].max()
    for traj_id in sorted(completed_trajectories(path, "val"))[:5]:
        tr = read_trajectory(path, "val", traj_id)
        p = tr.target_pos
        assert np.all(p[..., 0] >= xmin - 1e-3) and np.all(p[..., 0] <= xmax + 1e-3)
        assert np.all(p[..., 1] >= ymin - 1e-3) and np.all(p[..., 1] <= ymax + 1e-3)
        assert bool(tr.target_in_roi[0, 0])
