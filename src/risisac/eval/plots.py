"""Gambar untuk paper. Selalu dibuat ulang dari file hasil, bukan dari memori
proses (CLAUDE.md).

Pilihan warna:

* **F2 adalah peta magnitudo relatif terhadap ambang**, jadi skalanya *diverging*
  dengan titik tengah netral tepat di 0 dB — pembaca langsung melihat di mana
  SNR lewat RIS menyeberangi ambang Gate 1. Bukan pelangi, bukan jet.
* **F1 adalah peta identitas**, jadi warnanya *kategorikal* dengan urutan tetap.
  Dipakai palet Okabe-Ito, yang memang dirancang dan diuji aman untuk buta warna.
  Validator palet dari skill dataviz tidak bisa dijalankan di mesin ini (Node.js
  tidak terpasang), jadi dipilih palet yang validasinya sudah dipublikasikan
  ketimbang meracik sendiri tanpa alat uji.
* Gedung dan jalan memakai abu-abu netral: itu latar, bukan seri data.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.colors import TwoSlopeNorm  # noqa: E402
from matplotlib.patches import Polygon as MplPolygon  # noqa: E402

# Okabe-Ito, urutan tetap. Jangan dirotasi.
OKABE_ITO = {
    "orange": "#E69F00",
    "sky": "#56B4E9",
    "green": "#009E73",
    "yellow": "#F0E442",
    "blue": "#0072B2",
    "vermillion": "#D55E00",
    "purple": "#CC79A7",
    "black": "#000000",
}
BUILDING_FILL = "#D9D9D9"
BUILDING_EDGE = "#9E9E9E"
GRID_INK = "#BDBDBD"
TEXT_MUTED = "#555555"


def _style_axes(ax) -> None:
    ax.set_axisbelow(True)
    ax.grid(True, color=GRID_INK, linewidth=0.5, alpha=0.6)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    for spine in ("left", "bottom"):
        ax.spines[spine].set_color(GRID_INK)
    ax.tick_params(colors=TEXT_MUTED, labelsize=9)


def plot_f1_layout(spec, placement, out_path: str | Path,
                   los_ris_fraction: float | None = None) -> Path:
    """F1 — tampak atas scene: BS, RIS, ROI, lajur, trotoar."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots(figsize=(7.0, 6.4), dpi=200)
    e = spec.extent

    for name, (xmin, xmax, ymin, ymax) in spec.blocks().items():
        ax.add_patch(MplPolygon(
            [(xmin, ymin), (xmax, ymin), (xmax, ymax), (xmin, ymax)],
            closed=True, facecolor=BUILDING_FILL, edgecolor=BUILDING_EDGE,
            linewidth=0.8, zorder=1))
        ax.text((xmin + xmax) / 2, (ymin + ymax) / 2, name.replace("block_", "").upper(),
                ha="center", va="center", color=TEXT_MUTED, fontsize=9, zorder=2)

    # ROI
    ax.add_patch(MplPolygon(placement.roi_polygon, closed=True, facecolor="none",
                            edgecolor=OKABE_ITO["blue"], linewidth=2.0,
                            label="ROI (area NLoS)", zorder=4))

    for i, sw in enumerate(placement.sidewalks):
        ax.add_patch(MplPolygon(sw, closed=True, facecolor=OKABE_ITO["sky"],
                                alpha=0.35, edgecolor="none", zorder=3,
                                label="Trotoar" if i == 0 else None))
    for i, lane in enumerate(placement.target_lanes):
        ax.plot(lane[:, 0], lane[:, 1], color=OKABE_ITO["orange"], linewidth=2.0,
                linestyle="--", zorder=5, label="Lajur target" if i == 0 else None)

    ax.plot(*placement.bs_tx[:2], marker="^", markersize=11,
            color=OKABE_ITO["vermillion"], linestyle="none", zorder=6, label="BS")
    ax.plot(*placement.ris_position[:2], marker="s", markersize=10,
            color=OKABE_ITO["green"], linestyle="none", zorder=6, label="RIS")

    # Normal RIS
    n = placement.ris_normal
    ax.annotate("", xy=(placement.ris_position[0] + 18 * n[0],
                        placement.ris_position[1] + 18 * n[1]),
                xytext=placement.ris_position[:2],
                arrowprops=dict(arrowstyle="->", color=OKABE_ITO["green"], lw=2.0),
                zorder=6)

    ax.plot([placement.bs_tx[0], placement.ris_position[0]],
            [placement.bs_tx[1], placement.ris_position[1]],
            color=OKABE_ITO["vermillion"], linewidth=1.2, linestyle=":",
            alpha=0.9, zorder=4, label="LoS BS-RIS")

    ax.annotate("Jalan A", (-e * 0.72, 0), color=TEXT_MUTED, fontsize=10,
                ha="center", va="center", zorder=4)
    # va="top" membuat teks tumbuh ke bawah dari titik ini, sehingga tidak
    # pernah terpotong tepi atas sumbu berapa pun panjang labelnya.
    ax.annotate("Jalan B", (0, e * 0.94), color=TEXT_MUTED, fontsize=10,
                ha="center", va="top", rotation=90, zorder=4)

    ax.set_xlim(-e, e)
    ax.set_ylim(-e, e)
    ax.set_aspect("equal")
    ax.set_xlabel("x [m]", color=TEXT_MUTED)
    ax.set_ylabel("y [m]", color=TEXT_MUTED)
    title = "F1 — Tata letak scene sintetis berbentuk L"
    if los_ris_fraction is not None:
        title += f"\nLoS RIS→ROI: {100 * los_ris_fraction:.0f}% titik grid"
    ax.set_title(title, fontsize=11)
    _style_axes(ax)
    ax.legend(loc="lower left", fontsize=8, framealpha=0.95)

    fig.tight_layout()
    fig.savefig(out_path, bbox_inches="tight")
    plt.close(fig)
    return out_path


def plot_f2_coverage(grid_xy, snr_direct_db, snr_ris_db, out_path: str | Path,
                     m_elements: int, p_max_dbm: float,
                     threshold_db: float = 0.0) -> Path:
    """F2 — peta cakupan: BS langsung vs lewat RIS, pada ambang ``threshold_db``."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    x, y = grid_xy[:, 0], grid_xy[:, 1]
    xs, ys = np.unique(x), np.unique(y)

    def to_grid(values):
        g = np.full((len(ys), len(xs)), np.nan)
        xi = np.searchsorted(xs, x)
        yi = np.searchsorted(ys, y)
        g[yi, xi] = values
        return g

    maps = [("BS langsung (precoder sama)", to_grid(snr_direct_db)),
            (f"Lewat RIS (M = {m_elements}, precoder sama)",
             to_grid(snr_ris_db))]

    finite = np.concatenate([m[np.isfinite(m)] for _, m in maps])
    lo, hi = float(np.percentile(finite, 1)), float(np.percentile(finite, 99))
    lo = min(lo, threshold_db - 1.0)
    hi = max(hi, threshold_db + 1.0)
    norm = TwoSlopeNorm(vmin=lo, vcenter=threshold_db, vmax=hi)

    fig, axes = plt.subplots(1, 2, figsize=(10.5, 5.2), dpi=200, sharey=True)
    extent = [xs.min(), xs.max(), ys.min(), ys.max()]

    for ax, (label, grid) in zip(axes, maps):
        im = ax.imshow(grid, origin="lower", extent=extent, aspect="auto",
                       cmap="RdBu_r", norm=norm, interpolation="nearest")
        above = np.isfinite(grid) & (grid >= threshold_db)
        frac = above.sum() / max(np.isfinite(grid).sum(), 1)
        ax.contour(xs, ys, np.nan_to_num(grid, nan=lo), levels=[threshold_db],
                   colors="#000000", linewidths=1.2)
        ax.set_title(f"{label}\n{100 * frac:.1f}% titik ≥ {threshold_db:.0f} dB",
                     fontsize=10)
        ax.set_xlabel("x [m]", color=TEXT_MUTED)
        _style_axes(ax)

    axes[0].set_ylabel("y [m]", color=TEXT_MUTED)
    cbar = fig.colorbar(im, ax=axes, fraction=0.046, pad=0.03)
    cbar.set_label(f"SNR [dB]  (hitam = ambang {threshold_db:.0f} dB)",
                   color=TEXT_MUTED, fontsize=9)
    cbar.ax.tick_params(colors=TEXT_MUTED, labelsize=9)
    fig.suptitle(f"F2 — Peta cakupan di ROI, P_max = {p_max_dbm:.0f} dBm",
                 fontsize=12)
    fig.savefig(out_path, bbox_inches="tight")
    plt.close(fig)
    return out_path


def plot_f2_radar(grid_xy, scnr_db, out_path: str | Path,
                  threshold_db: float, p_max_dbm: float,
                  m_elements: int) -> Path:
    """F2b — peta SNR radar ideal di ROI (E7, rho = 1, tanpa clutter).

    Titik tengah skala diverging diletakkan tepat di ``threshold_db`` sehingga
    batas Gate 1 terbaca langsung dari warnanya.
    """
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    x, y = grid_xy[:, 0], grid_xy[:, 1]
    xs, ys = np.unique(x), np.unique(y)
    g = np.full((len(ys), len(xs)), np.nan)
    g[np.searchsorted(ys, y), np.searchsorted(xs, x)] = scnr_db

    finite = g[np.isfinite(g)]
    span = max(abs(float(np.percentile(finite, 1)) - threshold_db),
               abs(float(np.percentile(finite, 99)) - threshold_db), 1.0)

    fig, ax = plt.subplots(figsize=(5.2, 4.4), constrained_layout=True)
    im = ax.pcolormesh(xs, ys, g, cmap="RdBu_r", shading="nearest",
                       vmin=threshold_db - span, vmax=threshold_db + span)
    ax.contour(xs, ys, g, levels=[threshold_db], colors="k", linewidths=1.2)
    _style_axes(ax)
    ax.set_aspect("equal")
    ax.set_xlabel("x (m)")
    ax.set_ylabel("y (m)")
    ax.set_title(f"SNR radar ideal, M = {m_elements}, "
                 rf"$P_{{\max}}$ = {p_max_dbm:.0f} dBm")
    cb = fig.colorbar(im, ax=ax)
    cb.set_label("SCNR (dB)")
    cb.ax.axhline(threshold_db, color="k", linewidth=1.2)
    fig.savefig(out_path, dpi=200)
    plt.close(fig)
    return out_path


def plot_f3_e0(table: dict, out_path, tolerance_db: float = 0.1):
    """F3 - validasi E0 (docs/EXPERIMENT_DESIGN.md Sec 4.5).

    Dibuat dari ``T1_e0.json`` yang sudah ditulis, bukan dari variabel dalam
    memori, sesuai konvensi "gambar dibuat dari file hasil" (CLAUDE.md).
    """
    import matplotlib.pyplot as plt

    rows = table["calibration_rows"]
    cascade = table["cascade"]
    syn = table["synthetic_array"]

    fig, axes = plt.subplots(1, 3, figsize=(13.5, 4.2), constrained_layout=True)

    d2 = [r["d2_m"] for r in rows]
    axes[0].plot(d2, [r["hybrid_db"] for r in rows], "o-",
                 label="hibrida (Sionna RT)")
    axes[0].plot(d2, [r["tang2021_db"] for r in rows], "s--",
                 label="Tang dkk. (2021), Pers. 6")
    axes[0].set_xlabel("d(RIS-titik) (m)")
    axes[0].set_ylabel("penguatan kaskade (dB)")
    axes[0].set_title("E0-2: kalibrasi fisika\n"
                      f"calibration_db = {table['calibration_db']:+.2f} dB")
    axes[0].legend()

    names = list(cascade)
    axes[1].bar(range(len(names)), [cascade[n]["max_abs_db"] for n in names],
                color="tab:blue")
    axes[1].axhline(tolerance_db, color="crimson", ls="--",
                    label=f"ambang {tolerance_db} dB")
    axes[1].set_xticks(range(len(names)))
    axes[1].set_xticklabels(names, rotation=20, ha="right")
    axes[1].set_ylabel("|selisih| maks (dB)")
    axes[1].set_yscale("log")
    axes[1].set_title("E0-1: uji implementasi\nRT lawan Friis analitik")
    axes[1].legend()

    axes[2].hist(table["_synthetic_delta_db"], bins=30, color="tab:green",
                 alpha=0.85)
    axes[2].axvline(syn["median_db"], color="k", ls="--",
                    label=f"median {syn['median_db']:+.2f} dB")
    axes[2].set_xlabel("synthetic - per elemen (dB)")
    axes[2].set_ylabel("jumlah titik")
    axes[2].set_title(f"E0-3: synthetic array\n"
                      f"p95 |selisih| = {syn['p95_abs_db']:.2f} dB")
    axes[2].legend()

    for ax in axes:
        _style_axes(ax)
    fig.savefig(out_path, dpi=200)
    plt.close(fig)
    return out_path
