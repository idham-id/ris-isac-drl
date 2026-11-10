"""Tes scene sintetis, penempatan, dan oracle LoS (docs/TASKS.md Fase 1)."""

from __future__ import annotations

import numpy as np
import pytest

from risisac.config import load_config
from risisac.scene.placement import Placement, roi_grid
from risisac.scene.synthetic_l import SyntheticLSpec, build_xml

sionna_rt = pytest.importorskip("sionna.rt")


@pytest.fixture(scope="module")
def cfg():
    return load_config("base")


@pytest.fixture(scope="module")
def spec(cfg):
    return SyntheticLSpec.from_config(cfg)


@pytest.fixture(scope="module")
def placement(cfg):
    return Placement.from_config(cfg)


@pytest.fixture(scope="module")
def scene(cfg, spec):
    from risisac.scene.synthetic_l import load_synthetic_l
    sc = load_synthetic_l(spec)
    sc.frequency = float(cfg["radio"]["carrier_frequency_hz"])
    return sc


def test_xml_has_four_blocks_and_ground(spec):
    xml = build_xml(spec)
    for name in ("block_nw", "block_ne", "block_sw", "block_se", "ground"):
        assert f'id="mesh-{name}"' in xml
    assert xml.count("itu-radio-material") >= 1


def test_scene_loads_with_expected_objects(scene):
    names = set(scene.objects.keys())
    # merge_shapes menggabungkan bentuk yang berbagi material, jadi yang diuji
    # adalah scene termuat dan punya geometri, bukan jumlah objeknya.
    assert len(names) >= 1


def test_blocks_do_not_overlap_streets(spec):
    w = spec.half_width
    for _, (xmin, xmax, ymin, ymax) in spec.blocks().items():
        # Tidak ada blok yang masuk ke koridor jalan.
        assert xmax <= -w + 1e-9 or xmin >= w - 1e-9
        assert ymax <= -w + 1e-9 or ymin >= w - 1e-9


def test_roi_grid_inside_polygon_and_spacing(placement):
    grid = placement.roi_grid()
    xmin, xmax, ymin, ymax = placement.roi_bounds
    assert len(grid) > 0
    assert np.all(grid[:, 0] > xmin) and np.all(grid[:, 0] < xmax)
    assert np.all(grid[:, 1] > ymin) and np.all(grid[:, 1] < ymax)
    assert np.allclose(grid[:, 2], placement.roi_height)
    xs = np.unique(grid[:, 0])
    assert np.allclose(np.diff(xs), placement.roi_grid_spacing)


def test_roi_grid_respects_non_rectangular_polygon():
    tri = np.array([[0.0, 0.0], [10.0, 0.0], [0.0, 10.0]])
    pts = roi_grid(tri, height=1.5, spacing=1.0)
    assert len(pts) > 0
    # Semua titik harus di bawah garis x + y = 10.
    assert np.all(pts[:, 0] + pts[:, 1] < 10.0 + 1e-9)


def test_gate1_los_geometry(scene, placement):
    """Kriteria Gate 1 nomor 1 dan 2, diuji langsung sebagai tes unit."""
    from risisac.scene.visibility import los_mask

    assert bool(los_mask(scene, placement.bs_tx, placement.ris_position[None, :])[0]), \
        "BS->RIS harus LoS"

    grid = placement.roi_grid()
    assert los_mask(scene, placement.bs_tx, grid).mean() == 0.0, \
        "BS->ROI harus NLoS di 100% titik"


def test_los_oracle_agrees_with_path_solver(cfg, spec, placement):
    """ray_test dipakai sebagai pengganti PathSolver(max_depth=0); buktikan setara."""
    from risisac.scene.synthetic_l import load_synthetic_l
    from risisac.scene.visibility import verify_against_path_solver

    sc = load_synthetic_l(spec)
    sc.frequency = float(cfg["radio"]["carrier_frequency_hz"])
    sc.tx_array = sionna_rt.PlanarArray(num_rows=1, num_cols=1, pattern="iso",
                                        polarization="V")
    sc.rx_array = sionna_rt.PlanarArray(num_rows=1, num_cols=1, pattern="iso",
                                        polarization="V")

    grid = placement.roi_grid()
    rng = np.random.default_rng(0)
    # Campur titik ROI (semuanya NLoS) dengan titik di jalan A (sebagian LoS),
    # supaya tesnya tidak lolos hanya karena semuanya terhalang.
    street_a = np.stack([rng.uniform(-70, -15, 24), rng.uniform(-8, 8, 24),
                         np.full(24, 1.5)], axis=1)
    pts = np.concatenate([grid[rng.choice(len(grid), 24, replace=False)], street_a])

    res = verify_against_path_solver(sc, placement.bs_tx, pts)
    assert res["ray_test"].sum() > 0, "subhimpunan uji tidak punya titik LoS sama sekali"
    assert res["num_mismatch"] == 0, (
        f"{res['num_mismatch']}/{res['num_points']} titik tidak cocok")


def test_cosine_pattern_registers_once():
    from risisac.channels.patterns import register_cosine_pattern
    from sionna.rt.antenna_pattern import antenna_pattern_registry

    register_cosine_pattern()
    register_cosine_pattern()
    assert "cosine" in antenna_pattern_registry.list()
    arr = sionna_rt.PlanarArray(num_rows=2, num_cols=2, pattern="cosine",
                                polarization="V")
    assert arr.num_ant == 4
