"""Pembangunan scene dan penempatan perangkat (docs/TASKS.md Fase 1)."""

from .placement import Placement, roi_grid
from .synthetic_l import SyntheticLSpec, build_xml, load_synthetic_l, write_xml
from .visibility import los_fraction, los_mask

__all__ = [
    "Placement",
    "SyntheticLSpec",
    "build_xml",
    "load_synthetic_l",
    "los_fraction",
    "los_mask",
    "roi_grid",
    "write_xml",
]
