"""Gambar untuk paper. Selalu dibuat ulang dari file hasil, bukan dari memori
proses (CLAUDE.md).

Pilihan warna:

* **F2 adalah peta magnitudo relatif terhadap ambang**, jadi skalanya *diverging*
  dengan titik tengah netral tepat DI ambang kriterianya — 6 dB untuk panel
  penguatan, Γ untuk panel radar — sehingga batas lulus/tidak terbaca dari
  warnanya sendiri. Bukan pelangi, bukan jet.
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


def _to_grid(grid_xy, values):
    """Susun nilai per titik ROI menjadi matriks (ys, xs) untuk peta."""
    x, y = grid_xy[:, 0], grid_xy[:, 1]
    xs, ys = np.unique(x), np.unique(y)
    g = np.full((len(ys), len(xs)), np.nan)
    g[np.searchsorted(ys, y), np.searchsorted(xs, x)] = values
    return xs, ys, g


def _panel(ax, fig, grid_xy, values, threshold_db, cbar_label):
    """Satu peta diverging dengan titik tengah tepat di ambangnya.

    Titik tengah netral diletakkan DI ambang, bukan di nol atau di median,
    supaya batas lulus/tidak terbaca dari warnanya sendiri dan tidak perlu
    dicari lewat kontur. Kontur hitam tetap digambar sebagai jangkar.
    """
    xs, ys, g = _to_grid(grid_xy, values)
    finite = g[np.isfinite(g)]
    span = max(abs(float(np.percentile(finite, 1)) - threshold_db),
               abs(float(np.percentile(finite, 99)) - threshold_db), 1.0)
    im = ax.pcolormesh(xs, ys, g, cmap="RdBu_r", shading="nearest",
                       vmin=threshold_db - span, vmax=threshold_db + span)
    ax.contour(xs, ys, g, levels=[threshold_db], colors="#000000",
               linewidths=1.2)
    ax.set_aspect("equal")
    ax.set_xlabel("x [m]", color=TEXT_MUTED)
    _style_axes(ax)
    cb = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.03)
    cb.set_label(cbar_label, color=TEXT_MUTED, fontsize=9)
    cb.ax.tick_params(colors=TEXT_MUTED, labelsize=9)
    cb.ax.axhline(threshold_db, color="k", linewidth=1.2)
    return float(np.mean(finite >= threshold_db))


def plot_f2_coverage(grid_xy, ris_gain_db, scnr_ris_db, scnr_direct_db,
                     out_path: str | Path, m_elements: int, p_max_dbm: float,
                     gain_threshold_db: float, gamma_db: float) -> Path:
    """F2 — apa yang RIS tambahkan di ROI: dua panel, dua kriteria.

    Panel kiri adalah **penguatan** komunikasi, yaitu MRT pada kanal efektif
    ber-RIS dikurangi MRT pada jalur langsung saja: tiap sistem memakai
    beamformer terbaiknya sendiri. Perbandingan pada precoder yang SAMA
    (``a_bar``) tidak dipakai lagi -- ``a_bar`` dioptimalkan untuk mencapai
    RIS dan melumpuhkan jalur langsung, sehingga melebih-lebihkan peran RIS
    (+8,8 dB lawan +1,4 dB pada geometri lama; docs/LOG.md 2026-11-11 (e)).

    Panel kanan adalah SNR radar ideal (E7, rho = 1) **lewat RIS**, dengan
    kontur Gamma. Fraksi ROI yang memenuhi Gamma tanpa RIS ikut dilaporkan di
    judulnya: di geometri NLoS ini ia praktis nol, dan menggambarnya sebagai
    peta ketiga hanya akan menjadi bidang biru rata.

    Gambar ini menggantikan F2 lama (peta SNR mutlak pada precoder yang sama)
    dan menyerap F2b (peta radar terpisah), yang menjadi mubazir.
    """
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    fig, axes = plt.subplots(1, 2, figsize=(11.0, 4.8), dpi=200,
                             constrained_layout=True, sharey=True)

    frac_gain = _panel(axes[0], fig, grid_xy, ris_gain_db, gain_threshold_db,
                       "penguatan RIS [dB]")
    axes[0].set_title("(a) Penguatan RIS komunikasi, MRT vs MRT\n"
                      rf"{100 * frac_gain:.1f}% titik $\geq$ "
                      rf"{gain_threshold_db:.0f} dB", fontsize=10)
    axes[0].set_ylabel("y [m]", color=TEXT_MUTED)

    frac_ris = _panel(axes[1], fig, grid_xy, scnr_ris_db, gamma_db,
                      "SCNR ideal [dB]")
    direct = np.asarray(scnr_direct_db, dtype=float)
    frac_dir = float(np.mean(direct >= gamma_db))
    axes[1].set_title(r"(b) SNR radar ideal lewat RIS ($\rho$ = 1)" "\n"
                      rf"{100 * frac_ris:.1f}% titik $\geq$ $\Gamma$ = "
                      rf"{gamma_db:.0f} dB; tanpa RIS {100 * frac_dir:.1f}%",
                      fontsize=10)

    fig.suptitle(f"F2 — kontribusi RIS di ROI, M = {m_elements}, "
                 rf"$P_{{\max}}$ = {p_max_dbm:.0f} dBm", fontsize=12)
    fig.savefig(out_path, bbox_inches="tight")
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


# Warna tetap per metode: dipakai F4 sekarang dan gambar evaluasi nanti,
# supaya pembaca tidak perlu membaca ulang legenda di tiap gambar.
METHOD_COLORS = {
    # A1 adalah METODE UTAMA sejak Fase 8, jadi ia memakai warna yang paling
    # mudah dibedakan; M1 dan M2 menjadi ablasi tetapi WARNANYA TIDAK DIPUTAR,
    # supaya gambar Fase 5-7 dan gambar Fase 8 masih bisa dibandingkan
    # berdampingan oleh pembaca yang sudah hafal legendanya.
    "M1": OKABE_ITO["blue"],
    "M2": OKABE_ITO["vermillion"],
    "A1": OKABE_ITO["green"],
    # A1-FullCSI adalah A1 dengan observasi penuh: HUE YANG SAMA dengan A1,
    # lebih gelap. Pasangan dalam satu hue menyampaikan "metode yang sama,
    # setelan berbeda", yang memang hubungannya. Kuning Okabe-Ito sempat
    # dipakai di sini dan dibuang: rasio kontrasnya terhadap latar putih
    # sekitar 1,2:1, sehingga kurvanya nyaris tak terbaca di F4.
    "A1-FullCSI": "#00624A",
    # B0 tanpa RIS sama sekali. BUKAN abu-abu: keluarga abu-abu di bawah
    # adalah tangga oracle, yaitu langit-langit, sedangkan B0 adalah lantai --
    # memberinya abu-abu termuda akan membuatnya terbaca sebagai "oracle yang
    # paling basi". Dipakai sky Okabe-Ito, satu-satunya warna palet yang
    # belum terpakai dan masih terbaca di atas putih.
    "B0": OKABE_ITO["sky"],
    "B1": OKABE_ITO["purple"],
    "B2": OKABE_ITO["orange"],
    # Keluarga oracle digambar sebagai tangga ABU-ABU, bukan sebagai tiga
    # warna kategorikal baru: B3, B4-D5, dan B4-D10 adalah satu metode dengan
    # keputusan yang makin basi, dan nilai abu yang memudar menyampaikan
    # urutan itu sendiri. Warna kategorikal disimpan untuk metode yang
    # benar-benar berbeda.
    "B3": "#1A1A1A",
    "B4-D5": "#6E6E6E",
    "B4-D10": "#A6A6A6",
}
#: Urutan metode di legenda dan tabel (Fase 8): baseline dari yang terlemah,
#: lalu METODE UTAMA A1 dan varian ber-CSI-penuhnya, lalu ablasi M1 dan M2.
METHOD_ORDER = ("B0", "B1", "B2", "B3", "B4-D5", "B4-D10",
                "A1", "A1-FullCSI", "M1", "M2")


def _ordered(names):
    known = [m for m in METHOD_ORDER if m in set(names)]
    return known + sorted(set(names) - set(METHOD_ORDER))


def plot_f4_training(curves: dict, out_path, baselines: dict | None = None,
                     metric: str = "reward_per_step",
                     ylabel: str = "reward val per langkah"):
    """F4 - kurva pelatihan M1, M2, A1 (rata-rata +- std antar-seed, Sec 9).

    :param curves: ``{paper_id: {"timesteps": [...], "seeds": {seed: [...]}}}``
    :param baselines: ``{nama: nilai}`` digambar sebagai garis mendatar.

    Pita adalah std ANTAR-SEED, bukan interval kepercayaan: dengan n = 3 seed
    (Sec 9) pita CI akan lebar dan menyesatkan; std antar-seed menjawab
    pertanyaan yang memang ingin dijawab kurva pelatihan, yaitu seberapa
    bergantung hasilnya pada seed.
    """
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(7.0, 4.4), constrained_layout=True)
    # Urutan legenda mengikuti METHOD_ORDER, bukan urutan kunci dict: dict
    # datang dari urutan METHODS di train.py, yang masih M1 lebih dulu.
    for paper_id in _ordered(curves):
        curve = curves[paper_id]
        steps = np.asarray(curve["timesteps"], dtype=float)
        values = np.asarray([curve["seeds"][s] for s in sorted(curve["seeds"])],
                            dtype=float)
        mean, std = values.mean(axis=0), values.std(axis=0)
        color = METHOD_COLORS.get(paper_id, OKABE_ITO["black"])
        ax.plot(steps / 1e6, mean, color=color, lw=1.8,
                label=f"{paper_id} ({values.shape[0]} seed)")
        ax.fill_between(steps / 1e6, mean - std, mean + std, color=color,
                        alpha=0.18, lw=0)
    for name, value in (baselines or {}).items():
        ax.axhline(float(value), color=METHOD_COLORS.get(name, TEXT_MUTED),
                   ls="--", lw=1.2)
        ax.annotate(f"{name} {float(value):+.2f}",
                    xy=(ax.get_xlim()[1], float(value)),
                    xytext=(-4, 3), textcoords="offset points",
                    ha="right", va="bottom", fontsize=8,
                    color=METHOD_COLORS.get(name, TEXT_MUTED))
    ax.set_xlabel("langkah lingkungan (juta)")
    ax.set_ylabel(ylabel)
    ax.set_title("F4 - kurva pelatihan pada split val")
    ax.legend(frameon=False, loc="lower right")
    _style_axes(ax)
    fig.savefig(out_path, dpi=200)
    plt.close(fig)
    return out_path


def plot_f5_rate_cdf(steps, out_path, scnr_threshold_db: float | None = None):
    """F5 - CDF rate minimum semua metode (Sec 11).

    Dipakai nilai **per langkah**, bukan rata-rata per episode: yang menarik
    justru ekor kirinya -- seberapa buruk pengguna terlemah pada langkah
    terburuk -- dan merata-ratakan per episode menghapusnya.
    """
    import matplotlib.pyplot as plt

    from .metrics import ecdf

    fig, ax = plt.subplots(figsize=(7.0, 4.4), constrained_layout=True)
    for method in _ordered(steps["method"].unique()):
        values = steps.loc[steps["method"] == method, "min_rate"].to_numpy()
        x, f = ecdf(values)
        ax.plot(x, f, lw=1.8, color=METHOD_COLORS.get(method, OKABE_ITO["black"]),
                label=method)
    ax.set_xlabel("rate minimum antar-pengguna (bit/s/Hz)")
    ax.set_ylabel("CDF empiris atas langkah")
    ax.set_title("F5 - distribusi rate minimum pada set test")
    ax.set_ylim(0.0, 1.0)
    ax.legend(frameon=False, loc="lower right", ncol=2, fontsize=8)
    _style_axes(ax)
    fig.savefig(out_path, dpi=200)
    plt.close(fig)
    return out_path


def plot_f6_episode(steps, out_path, trajectory_index: int,
                    methods=("B2", "A1", "M1", "B3"),
                    scnr_threshold_db: float = 13.0,
                    sigma_max_m: float = 5.0, dt_s: float = 0.1):
    """F6 - satu episode: SCNR terhadap waktu, ambang, deteksi, galat tracker.

    Satu seed derau dan satu seed latih saja, supaya yang terlihat adalah
    jalannya episode dan bukan rata-rata yang sudah dihaluskan.
    """
    import matplotlib.pyplot as plt

    sel = steps[steps["trajectory_index"] == int(trajectory_index)]
    noise_seed = int(sel["noise_seed"].min())
    sel = sel[sel["noise_seed"] == noise_seed]

    fig, axes = plt.subplots(2, 1, figsize=(7.2, 5.6), sharex=True,
                             constrained_layout=True)
    for method in _ordered([m for m in methods if m in set(sel["method"])]):
        g = sel[sel["method"] == method]
        g = g[g["train_seed"] == g["train_seed"].min()].sort_values("step")
        t = g["step"].to_numpy() * float(dt_s)
        color = METHOD_COLORS.get(method, OKABE_ITO["black"])
        axes[0].plot(t, g["scnr_db"], lw=1.6, color=color, label=method)
        miss = g["scnr_db"].to_numpy() < scnr_threshold_db
        axes[0].plot(t[miss], g["scnr_db"].to_numpy()[miss], "v", ms=4,
                     color=color, alpha=0.8)
        axes[1].plot(t, g["tracker_error_m"], lw=1.6, color=color)

    # Label ambang ditempel di tepi KANAN: di tepi kiri ia jatuh tepat di atas
    # kurva, yang justru bagian paling ramai pada gambar ini.
    axes[0].axhline(scnr_threshold_db, color=TEXT_MUTED, ls="--", lw=1.2)
    axes[0].annotate(rf"$\Gamma$ = {scnr_threshold_db:g} dB",
                     xy=(1.0, scnr_threshold_db), xycoords=("axes fraction",
                                                            "data"),
                     xytext=(-3, 4), textcoords="offset points", ha="right",
                     fontsize=8, color=TEXT_MUTED)
    axes[0].set_ylabel("SCNR (dB)")
    axes[0].set_title(f"F6 - episode contoh: lintasan {trajectory_index}, "
                      f"seed derau {noise_seed}", fontsize=11)
    axes[0].annotate(r"$\blacktriangledown$ = langkah di bawah $\Gamma$",
                     xy=(0.0, 1.0), xycoords="axes fraction",
                     xytext=(2, -11), textcoords="offset points",
                     fontsize=8, color=TEXT_MUTED)
    axes[0].legend(frameon=False, loc="upper right", ncol=4, fontsize=8)

    axes[1].axhline(sigma_max_m, color=TEXT_MUTED, ls="--", lw=1.2)
    axes[1].annotate(rf"$\sigma_{{max}}$ = {sigma_max_m:g} m",
                     xy=(1.0, sigma_max_m), xycoords=("axes fraction", "data"),
                     xytext=(-3, -12), textcoords="offset points", ha="right",
                     fontsize=8, color=TEXT_MUTED)
    axes[1].set_ylabel("galat posisi tracker (m)")
    axes[1].set_xlabel("waktu (s)")
    for ax in axes:
        _style_axes(ax)
    fig.savefig(out_path, dpi=200)
    plt.close(fig)
    return out_path


def plot_f8_tradeoff(points, out_path):
    """F8 - trade-off rate minimum vs pemenuhan SCNR untuk Gamma berbeda.

    :param points: ``[{"method", "gamma_db", "min_rate", "scnr_compliance",
        "per_seed"(opsional)}]``.

    Tiap metode menjadi satu garis yang menghubungkan nilai Gamma-nya, dengan
    penanda yang membesar seiring Gamma. Seed individual M1 ikut digambar
    sebagai titik kecil: pada Gamma = 16 dB sebarannya besar, dan rata-rata
    saja akan menyembunyikannya (docs/LOG.md 2026-11-12 (c)).
    """
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(7.0, 4.6), constrained_layout=True)
    gammas = sorted({float(p["gamma_db"]) for p in points})
    sizes = {g: 5.0 + 3.0 * i for i, g in enumerate(gammas)}

    by_method: dict[str, list] = {}
    for p in points:
        by_method.setdefault(str(p["method"]), []).append(p)

    # Jarak minimum antar-label, dalam fraksi rentang sumbu. B2 dan B3 nyaris
    # tidak bergerak saat Gamma berubah, sehingga ketiga labelnya menumpuk
    # menjadi gumpalan tak terbaca. Label yang berdekatan digabung menjadi
    # satu rentang ("10-16"), yang sekaligus menyampaikan isinya: metode itu
    # memang tidak peka terhadap Gamma.
    xs = [p["scnr_compliance"] for p in points]
    ys = [p["min_rate"] for p in points]
    span_x = max(max(xs) - min(xs), 1e-9)
    span_y = max(max(ys) - min(ys), 1e-9)
    near = 0.02

    for method in _ordered(by_method):
        rows = sorted(by_method[method], key=lambda r: float(r["gamma_db"]))
        color = METHOD_COLORS.get(method, OKABE_ITO["black"])
        ax.plot([r["scnr_compliance"] for r in rows],
                [r["min_rate"] for r in rows], "-", lw=1.4, color=color,
                alpha=0.9, label=method, zorder=3)
        for r in rows:
            ax.plot(r["scnr_compliance"], r["min_rate"], "o",
                    ms=sizes[float(r["gamma_db"])], color=color, zorder=4)
            for seed_point in r.get("per_seed", []):
                ax.plot(seed_point[0], seed_point[1], ".", ms=4, color=color,
                        alpha=0.55, zorder=2)

        clusters: list[list] = []
        for r in rows:
            if clusters and (abs(r["scnr_compliance"]
                                 - clusters[-1][-1]["scnr_compliance"]) / span_x
                             < near) and (abs(r["min_rate"]
                                              - clusters[-1][-1]["min_rate"])
                                          / span_y < near):
                clusters[-1].append(r)
            else:
                clusters.append([r])
        for group in clusters:
            lo = f"{float(group[0]['gamma_db']):g}"
            hi = f"{float(group[-1]['gamma_db']):g}"
            label = lo if lo == hi else f"{lo}–{hi}"
            anchor = group[-1]
            ax.annotate(label, xy=(anchor["scnr_compliance"],
                                   anchor["min_rate"]),
                        xytext=(6, -3), textcoords="offset points",
                        fontsize=7, color=color)
    ax.set_xlabel(r"pemenuhan SCNR (fraksi langkah dengan SCNR $\geq$ $\Gamma$)")
    ax.set_ylabel("rate minimum rata-rata (bit/s/Hz)")
    ax.set_title(r"F8 - trade-off komunikasi-sensing; label = $\Gamma$ (dB)")
    ax.legend(frameon=False, loc="lower left", ncol=2, fontsize=8)
    _style_axes(ax)
    fig.savefig(out_path, dpi=200)
    plt.close(fig)
    return out_path


def plot_f7_pmax_speed(table, out_path, speed_bins, metrics=None):
    """F7 - kinerja terhadap P_max dan kelompok kecepatan target (E4a).

    :param table: baris dengan kolom ``axis`` ("p_max_dbm" atau
        "speed_group"), ``x``, ``method``, dan tiap metrik beserta
        ``_lo``/``_hi``.

    Kedua kolom BERBAGI sumbu-y per baris (``sharey="row"``). Tanpa itu
    panel kecepatan ter-zoom otomatis ke rentangnya sendiri dan perbedaan
    0,03 terlihat sebesar perbedaan 0,75 di panel daya -- padahal justru
    kedataran panel kecepatan yang merupakan temuannya. Pita adalah CI 95%
    bootstrap berkelompok (Sec 9), bukan std.
    """
    import matplotlib.pyplot as plt

    metrics = metrics or (("min_rate", "rate minimum (bit/s/Hz)"),
                          ("scnr_compliance", "pemenuhan SCNR"))
    axes_spec = (("p_max_dbm", "$P_{max}$ (dBm)"),
                 ("speed_group", "kelompok kecepatan target (m/s)"))
    fig, axs = plt.subplots(len(metrics), 2, figsize=(9.2, 2.6 * len(metrics) + 1.0),
                            constrained_layout=True, squeeze=False,
                            sharey="row")

    labels = [f"{float(lo):g}-{float(hi):g}" for lo, hi in speed_bins]
    for row, (column, ylabel) in enumerate(metrics):
        for col, (axis, xlabel) in enumerate(axes_spec):
            ax = axs[row][col]
            sub = table[table["axis"] == axis]
            for method in _ordered(sub["method"].unique()):
                g = sub[sub["method"] == method].sort_values("x")
                color = METHOD_COLORS.get(method, OKABE_ITO["black"])
                x = g["x"].to_numpy(dtype=float)
                ax.plot(x, g[column], "-o", ms=4, lw=1.6, color=color,
                        label=method)
                ax.fill_between(x, g[f"{column}_lo"], g[f"{column}_hi"],
                                color=color, alpha=0.16, lw=0)
            if axis == "speed_group":
                ax.set_xticks(range(len(labels)))
                ax.set_xticklabels(labels)
            if row == len(metrics) - 1:
                ax.set_xlabel(xlabel)
            if col == 0:
                ax.set_ylabel(ylabel)
            _style_axes(ax)
    axs[0][1].legend(frameon=False, loc="best", ncol=2, fontsize=8)
    fig.suptitle("F7 - kinerja terhadap daya pancar dan kecepatan target "
                 "(tanpa latih ulang)", fontsize=11)
    fig.savefig(out_path, dpi=200)
    plt.close(fig)
    return out_path
