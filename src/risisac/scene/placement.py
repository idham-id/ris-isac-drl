"""Penempatan BS, RIS, ROI, lajur target, dan trotoar — semuanya dari config.

docs/TASKS.md Fase 1, docs/EXPERIMENT_DESIGN.md §2.1.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class Placement:
    """Geometri penempatan untuk satu scene, dibaca dari ``cfg['scene']``."""

    bs_tx: np.ndarray            # (3,) posisi panel pancar BS
    bs_rx: np.ndarray            # (3,) posisi panel terima BS
    ris_position: np.ndarray     # (3,)
    ris_normal: np.ndarray       # (3,) unit, menghadap jalan B
    roi_polygon: np.ndarray      # (V, 2) poligon ROI di bidang xy
    roi_height: float
    roi_grid_spacing: float
    target_lanes: list[np.ndarray]   # tiap elemen (P, 2) polyline
    sidewalks: list[np.ndarray]      # tiap elemen (V, 2) poligon

    @classmethod
    def from_config(cls, cfg: dict) -> "Placement":
        s = cfg["scene"]
        missing = [k for k in ("bs_position", "ris_position", "ris_normal")
                   if s.get(k) is None]
        if missing:
            raise ValueError(
                f"scene.{{{', '.join(missing)}}} masih null. Koordinat ditetapkan "
                "di Fase 1 dan disimpan di configs/ (docs/TASKS.md)."
            )
        if s["roi"].get("polygon") is None:
            raise ValueError("scene.roi.polygon masih null (lihat docs/TASKS.md Fase 1).")

        bs_tx = np.asarray(s["bs_position"], dtype=float)
        bs_rx = bs_tx + np.asarray(s["bs_rx_offset"], dtype=float)

        normal = np.asarray(s["ris_normal"], dtype=float)
        norm = np.linalg.norm(normal)
        if norm < 1e-9:
            raise ValueError("scene.ris_normal adalah vektor nol.")
        normal = normal / norm

        return cls(
            bs_tx=bs_tx,
            bs_rx=bs_rx,
            ris_position=np.asarray(s["ris_position"], dtype=float),
            ris_normal=normal,
            roi_polygon=np.asarray(s["roi"]["polygon"], dtype=float),
            roi_height=float(s["roi"]["height"]),
            roi_grid_spacing=float(s["roi"]["grid_spacing_m"]),
            target_lanes=[np.asarray(p, dtype=float) for p in (s.get("target_lanes") or [])],
            sidewalks=[np.asarray(p, dtype=float) for p in (s.get("sidewalks") or [])],
        )

    @property
    def roi_bounds(self) -> tuple[float, float, float, float]:
        """(xmin, xmax, ymin, ymax) dari poligon ROI."""
        p = self.roi_polygon
        return float(p[:, 0].min()), float(p[:, 0].max()), \
            float(p[:, 1].min()), float(p[:, 1].max())

    def roi_grid(self, spacing: float | None = None) -> np.ndarray:
        """Titik grid di dalam ROI, bentuk (N, 3)."""
        return roi_grid(self.roi_polygon, self.roi_height,
                        spacing if spacing is not None else self.roi_grid_spacing)

    def roi_grid_shape(self, spacing: float | None = None) -> tuple[int, int]:
        """(n_y, n_x) grid persegi panjang pembungkus ROI."""
        sp = spacing if spacing is not None else self.roi_grid_spacing
        xmin, xmax, ymin, ymax = self.roi_bounds
        return (len(np.arange(ymin + sp / 2, ymax, sp)),
                len(np.arange(xmin + sp / 2, xmax, sp)))

    def ris_look_at(self, distance: float = 1.0) -> np.ndarray:
        """Titik bidik untuk ``sionna.rt`` yang setara dengan ``ris_normal``."""
        return self.ris_position + distance * self.ris_normal


def _points_in_polygon(points_xy: np.ndarray, polygon: np.ndarray) -> np.ndarray:
    """Uji titik-dalam-poligon dengan ray casting. Bentuk (N,2) dan (V,2)."""
    x, y = points_xy[:, 0], points_xy[:, 1]
    inside = np.zeros(len(points_xy), dtype=bool)
    n = len(polygon)
    for i in range(n):
        x1, y1 = polygon[i]
        x2, y2 = polygon[(i + 1) % n]
        # Apakah sisi ini memotong garis horizontal pada ketinggian y?
        crosses = (y1 > y) != (y2 > y)
        with np.errstate(divide="ignore", invalid="ignore"):
            x_at_y = x1 + (y - y1) * (x2 - x1) / (y2 - y1)
        inside ^= crosses & (x < x_at_y)
    return inside


def roi_grid(polygon: np.ndarray, height: float, spacing: float) -> np.ndarray:
    """Grid titik berjarak ``spacing`` di dalam ``polygon``, bentuk (N, 3).

    Titik ditempatkan di pusat sel supaya tidak jatuh persis di tepi poligon.
    """
    polygon = np.asarray(polygon, dtype=float)
    xmin, xmax = polygon[:, 0].min(), polygon[:, 0].max()
    ymin, ymax = polygon[:, 1].min(), polygon[:, 1].max()
    xs = np.arange(xmin + spacing / 2, xmax, spacing)
    ys = np.arange(ymin + spacing / 2, ymax, spacing)
    gx, gy = np.meshgrid(xs, ys, indexing="xy")
    flat = np.stack([gx.ravel(), gy.ravel()], axis=1)
    keep = _points_in_polygon(flat, polygon)
    flat = flat[keep]
    return np.concatenate([flat, np.full((len(flat), 1), height)], axis=1)
