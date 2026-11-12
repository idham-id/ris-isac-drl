r"""Tabel LaTeX untuk paper (docs/EXPERIMENT_DESIGN.md §11, docs/TASKS.md Fase 7).

Tabel dibangun dari **file hasil**, bukan dari angka yang diketik ulang, dengan
alasan yang sama seperti gambar: satu sumber kebenaran, dan tabel yang tidak
bisa diam-diam menyimpang dari data.

Keluarannya LaTeX mentah dengan ``booktabs`` (``\toprule`` dst.) dan tanpa
paket tambahan: tidak ada ``siunitx``, tidak ada ``\begin{document}``. Berkas
hasilnya untuk di-``\input`` dari manuskrip.
"""

from __future__ import annotations

import numpy as np

#: Karakter yang harus di-escape di teks LaTeX. Urutan penting: backslash dulu.
_ESCAPES = (("\\", r"\textbackslash{}"), ("&", r"\&"), ("%", r"\%"),
            ("$", r"\$"), ("#", r"\#"), ("_", r"\_"), ("{", r"\{"),
            ("}", r"\}"), ("~", r"\textasciitilde{}"),
            ("^", r"\textasciicircum{}"))


class Raw(str):
    r"""Penanda bahwa sel ini SUDAH LaTeX dan tidak boleh di-escape.

    Penandanya eksplisit, bukan ditebak dari isinya. Menebak -- misalnya
    "lewatkan kalau diapit ``$``" -- gagal pada label campuran seperti
    ``$M$ (baris $\times$ kolom)``, yang berawalan ``$`` tetapi tidak
    berakhiran ``$``, lalu keluar sebagai sampah backslash di tabel. Aturannya:
    apa pun yang ditulis di berkas ini boleh ``Raw``; apa pun yang datang dari
    file hasil selalu di-escape.
    """


def escape(text) -> str:
    """Escape teks untuk LaTeX, kecuali yang ditandai :class:`Raw`."""
    if isinstance(text, Raw):
        return str(text)
    s = str(text)
    for old, new in _ESCAPES:
        s = s.replace(old, new)
    return s


def number(value, digits: int = 3, plus: bool = False) -> Raw:
    r"""Format angka ala Indonesia (koma desimal) untuk tabel paper.

    Tanda ditulis sebagai ``$-$`` / ``$+$``, bukan ``-`` / ``+``: di mode teks
    LaTeX, ``-`` adalah tanda HUBUNG dan tercetak jauh lebih pendek daripada
    tanda minus. Pada tabel yang dibuat otomatis, cacat kecil itu akan muncul
    di setiap baris negatif tanpa ada yang memperbaikinya satu per satu.
    """
    if value is None or (isinstance(value, float) and not np.isfinite(value)):
        return Raw("--")
    text = f"{float(value):+.{digits}f}" if plus else f"{float(value):.{digits}f}"
    text = text.replace(".", ",")
    if text.startswith("-"):
        text = "$-$" + text[1:]
    elif text.startswith("+"):
        text = "$+$" + text[1:]
    return Raw(text)


def sci(value) -> Raw:
    r"""Notasi ilmiah LaTeX tanpa paket tambahan (``siunitx`` tidak diasumsikan)."""
    v = float(value)
    if v == 0:
        return Raw("$0$")
    exp = int(np.floor(np.log10(abs(v))))
    mant = v / (10.0 ** exp)
    head = (f"{int(round(mant))}" if abs(mant - round(mant)) < 1e-9
            else f"{mant:.1f}".replace(".", "{,}"))
    return Raw(f"${head} \\times 10^{{{exp}}}$")


def latex_table(header, rows, caption: str, label: str,
                align: str | None = None, notes: str | None = None) -> str:
    r"""Satu ``table`` LaTeX dengan ``booktabs``.

    ``header``, ``caption``, dan ``notes`` ditulis oleh pemanggil dan dipakai
    apa adanya; hanya SEL yang di-escape, karena sel bisa berasal dari file
    hasil.
    """
    header = list(header)
    align = align or ("l" + "r" * (len(header) - 1))
    out = ["\\begin{table}[t]", "\\centering",
           f"\\caption{{{caption}}}", f"\\label{{{label}}}",
           f"\\begin{{tabular}}{{{align}}}", "\\toprule",
           " & ".join(str(h) for h in header) + " \\\\", "\\midrule"]
    for row in rows:
        out.append(" & ".join("--" if c is None else escape(c)
                              for c in row) + " \\\\")
    out += ["\\bottomrule", "\\end{tabular}"]
    if notes:
        out.append(f"\\par\\smallskip\\footnotesize {notes}")
    out.append("\\end{table}")
    return "\n".join(out) + "\n"


# ------------------------------------------------------------------- T1 (E0)
def t1_channel_validation(e0: dict) -> str:
    """T1 -- galat validasi kanal, dari ``results/e0/<hash>/T1_e0.json``."""
    per = e0["per_element"]
    rows = [
        [Raw(r"Amplitudo per elemen $\mathbf{G}$ (BS--RIS)"),
         number(per["G_amplitude_max_db"], 4), "dB"],
        [Raw(r"Amplitudo per elemen $\mathbf{g}$ (RIS--titik)"),
         number(per["g_amplitude_max_db"], 4), "dB"],
        [Raw(r"Fasa per elemen $\mathbf{G}$"),
         number(per["G_phase_max_deg"], 4), "derajat"],
        [Raw(r"Fasa per elemen $\mathbf{g}$"),
         number(per["g_phase_max_deg"], 4), "derajat"],
    ]
    for name, item in e0["cascade"].items():
        rows.append([f"Kaskade, profil {name}",
                     number(item["max_abs_db"], 4), "dB"])
    rows.append(["Kalibrasi terhadap Tang dkk. (2021) Pers. (6)",
                 number(e0["calibration_db"], 2), "dB"])
    worst = max(float(i["max_abs_db"]) for i in e0["cascade"].values())
    return latex_table(
        ["Besaran yang diuji", "Selisih", "Satuan"], rows,
        caption=("T1 -- validasi model kanal hibrida terhadap model analitik "
                 "(E0)."),
        label="tab:t1-channel-validation", align="lrl",
        notes=(f"Ambang uji implementasi {number(e0['tolerance_db'], 1)} dB; "
               f"selisih terburuk {number(worst, 4)} dB. "
               r"\texttt{calibration\_db} dicatat, tidak diterapkan ke kanal."))


# ------------------------------------------------------------------- T2 (E3)
#: Kolom T2: (kunci di T2.csv, judul kolom, digit, pakai tanda +).
T2_FIELDS = ((("reward_per_step"), "Reward/langkah", 3, True),
             ("min_rate", "Rate min.", 2, False),
             ("scnr_compliance", "Pemenuhan SCNR", 3, False),
             ("track_duration_s", "Durasi track (s)", 2, False),
             ("tracker_error_m", "Galat tracker (m)", 2, False))

#: Nama metode di paper. Kunci-kunci ini SAMA dengan kunci di file hasil dan
#: nama direktori run; yang berubah di Fase 8 hanya teks tampilannya, supaya
#: pembaca tabel langsung melihat mana metode utama dan mana ablasi.
METHOD_LABELS = {"B0": "B0 No-RIS",
                 "B1": "B1 Random", "B2": "B2 Geometric",
                 "B3": "B3 Oracle-GD", "B4-D5": "B4 Oracle-GD-stale(5)",
                 "B4-D10": "B4 Oracle-GD-stale(10)",
                 "A1": "A1 PPO-PO-absolute (utama)",
                 "A1-FullCSI": "A1-FullCSI PPO-absolute, CSI penuh",
                 "M1": "M1 PPO-PO (ablasi fasa inkremental)",
                 "M2": "M2 PPO-FullCSI (ablasi fasa inkremental)"}


def t2_main_results(t2, gamma_db: float, p_max_dbm: float,
                    with_ci: bool = True) -> str:
    """T2 -- hasil utama set test, dari ``T2.csv`` (indeks = metode)."""
    header = ["Metode", "Episode"] + [h for _, h, _, _ in T2_FIELDS]
    rows = []
    for method, row in t2.iterrows():
        cells = [METHOD_LABELS.get(method, method), f"{int(row['episodes'])}"]
        for key, _, digits, plus in T2_FIELDS:
            value = number(row[key], digits, plus)
            if with_ci and f"{key}_lo" in row:
                value += (f" {{\\tiny[{number(row[f'{key}_lo'], digits)}, "
                          f"{number(row[f'{key}_hi'], digits)}]}}")
            cells.append(Raw(value))
        rows.append(cells)
    return latex_table(
        header, rows,
        caption=(f"T2 -- hasil set test, $\\Gamma$ = {gamma_db:g} dB, "
                 f"$P_{{max}}$ = {p_max_dbm:g} dBm."),
        label="tab:t2-main-results", align="l" + "r" * (len(header) - 1),
        notes=("Kurung siku: interval kepercayaan 95\\% bootstrap atas "
               "episode, dikelompokkan per seed. Agen dilaporkan pada "
               "checkpoint terbaik di val. B0 menghapus kaskade RIS "
               "seluruhnya dan memakai CSI langsung sempurna: ia lantai "
               "sistem tanpa RIS, bukan sistem tanpa RIS yang realistis. "
               "B3/B4 memakai CSI dan posisi sempurna: acuan atas, bukan "
               "metode terapan."))


# ---------------------------------------------------------------- T3 (E5+E6)
def t3_ablation(e5) -> str:
    """T3a -- ablasi parameterisasi fasa DAN observasi pada set test (E5).

    Dua ablasi dalam satu tabel karena keduanya menjawab pertanyaan yang sama
    bentuknya: berapa harga satu pilihan desain, diukur pada metode utama.
    Baris A1 lawan A1-FullCSI mengisolasi **observasi** (keduanya fasa
    absolut); baris A1 lawan M1/M2 beserta sapuan kappa mengisolasi
    **parameterisasi fasa**.
    """
    rows = [[row["varian"], f"{int(row['episode'])}",
             number(row["reward_per_step"], 3, True),
             number(row["min_rate"], 2),
             number(row["scnr_compliance"], 3)]
            for _, row in e5.iterrows()]
    note = ("Seluruh baris memakai $\\lambda$, geometri, dan anggaran "
            "langkah yang sama; yang berbeda hanya parameterisasi fasa, "
            "$\\kappa$, atau mode observasi. ")
    by_method = {str(r["metode"]): r for _, r in e5.iterrows()
                 if "metode" in e5.columns}
    if {"A1", "A1-FullCSI"} <= set(by_method):
        delta = (float(by_method["A1-FullCSI"]["reward_per_step"])
                 - float(by_method["A1"]["reward_per_step"]))
        note += (f"Harga observasi parsial pada metode utama: "
                 f"{number(delta, 3, True)} reward per langkah "
                 "(A1-FullCSI dikurangi A1).")
    return latex_table(
        ["Varian", "Episode", "Reward/langkah", "Rate min.",
         "Pemenuhan SCNR"], rows,
        caption=("T3a -- ablasi parameterisasi fasa dan observasi pada set "
                 "test (E5)."),
        label="tab:t3-ablation", notes=note)


def t3_cost(cost: dict) -> str:
    """T3b -- biaya komputasi per keputusan (E6)."""
    rows = []
    for paper_id, item in cost.get("agents", {}).items():
        rows.append([METHOD_LABELS.get(paper_id, paper_id),
                     number(item["ms_per_decision"], 3),
                     f"CPU, observasi {item['observation_dim']}"])
    b2 = cost.get("baselines", {}).get("B2")
    if b2:
        rows.append([METHOD_LABELS["B2"],
                     number(b2["ms_per_decision"], 3), "CPU"])
    b3 = cost.get("baselines", {}).get("B3")
    if b3:
        rows.append([METHOD_LABELS["B3"] + " (daring)",
                     number(b3["ms_per_decision_online"], 1),
                     Raw(f"{b3['device'].upper()}, {b3['iterations']} iterasi "
                         f"$\\times$ {b3['restarts']} restart")])
        rows.append([METHOD_LABELS["B3"] + " (teramortisasi)",
                     number(b3["ms_per_decision_batched"], 2),
                     f"{b3['device'].upper()}, {b3['batch_steps']} langkah "
                     f"dibatch sekaligus"])
    note = "Waktu satu keputusan, diukur di mesin yang sama. "
    for paper_id, key in (("A1", "a1_vs_b3_online_speedup"),
                          ("M1", "m1_vs_b3_online_speedup")):
        speedup = cost.get(key)
        if speedup:
            note += (f"{paper_id} {int(round(speedup)):,}".replace(",", ".")
                     + "$\\times$ lebih cepat daripada B3 daring. ")
    note += ("Angka teramortisasi hanya berlaku bagi acuan offline yang "
             "seluruh langkahnya dioptimalkan sekaligus, bukan bagi "
             "pengendali.")
    return latex_table(["Metode", "ms per keputusan", "Perangkat"], rows,
                       caption="T3b -- biaya komputasi per keputusan (E6).",
                       label="tab:t3-cost", align="lrl", notes=note)


def t3_ablation_cost(e5, cost: dict) -> str:
    """T3 lengkap: ablasi (E5) diikuti biaya komputasi (E6)."""
    return t3_ablation(e5) + "\n" + t3_cost(cost)


# ------------------------------------------------------------ tabel parameter
#: Baris tabel parameter: (label LaTeX, jalur di config, format).
PARAM_ROWS = (
    (Raw("$f_c$"), ("radio", "carrier_frequency_hz"), "ghz"),
    (Raw("$B$"), ("radio", "bandwidth_hz"), "mhz"),
    (Raw("Noise figure"), ("radio", "noise_figure_db"), "db"),
    (Raw("$N_t = N_r$"), ("radio", "bs", "num_tx"), "int"),
    (Raw(r"$M$ (baris $\times$ kolom)"), ("radio", "ris"), "ris"),
    (Raw("$P_{max}$ (evaluasi)"), ("radio", "p_max_dbm"), "dbm"),
    (Raw("$P_{max}$ (pelatihan)"), ("radio", "p_max_train_range_dbm"),
     "range_dbm"),
    (Raw("$K$ pengguna"), ("radio", "user", "num_users"), "int"),
    (Raw("$Q$ target"), ("radio", "target", "num_targets"), "int"),
    (Raw(r"$\sigma_{rcs}$"), ("radio", "target", "rcs_m2"), "m2"),
    (Raw("$L$ (integrasi)"), ("sensing", "integration_samples"), "int"),
    (Raw(r"$\xi$ (residu clutter)"), ("sensing", "clutter_residual"), "plain"),
    (Raw(r"$\Gamma$"), ("sensing", "scnr_threshold_db"), "db"),
    (Raw(r"$\Delta t$"), ("mobility", "dt_s"), "s"),
    (Raw("$T$ (langkah episode)"), ("mobility", "episode_steps"), "int"),
    (Raw(r"$\kappa$"), ("action", "phase_step_kappa"), "plain"),
    (Raw(r"$\lambda$"), ("reward", "lambda"), "plain"),
    (Raw(r"$\epsilon$ (NMSE kanal)"), ("observation", "eff_channel_nmse_db"),
     "db"),
    (Raw(r"$\sigma_u$"), ("observation", "user_pos_std_m"), "m"),
    (Raw(r"$\sigma_{ref}$"), ("observation", "target_pos_ref_std_m"), "m"),
    (Raw(r"$\sigma_{max}$"), ("observation", "target_pos_max_std_m"), "m"),
    (Raw(r"Ray tracing: \texttt{max\_depth}"), ("ray_tracing", "max_depth"),
     "int"),
    (Raw(r"Ray tracing: \texttt{samples\_per\_src}"),
     ("ray_tracing", "samples_per_src"), "sci"),
    (Raw(r"$\gamma$ (diskon)"), ("training", "gamma"), "plain"),
    (Raw("Laju belajar PPO"), ("training", "ppo", "learning_rate"), "sci"),
    (Raw("Langkah pelatihan"), ("training", "total_timesteps"), "sci"),
    (Raw("Seed pelatihan"), ("training", "num_seeds"), "int"),
)


def _dig(cfg: dict, path):
    node = cfg
    for key in path:
        node = node[key]
    return node


def _fmt(value, kind: str) -> Raw:
    if kind == "ghz":
        return Raw(f"{float(value) / 1e9:g} GHz".replace(".", ","))
    if kind == "mhz":
        return Raw(f"{float(value) / 1e6:g} MHz".replace(".", ","))
    if kind == "db":
        return Raw(f"{number(value, 1)} dB")
    if kind == "dbm":
        return Raw(f"{number(value, 1)} dBm")
    if kind == "range_dbm":
        lo, hi = value
        return Raw(f"{number(lo, 0)}--{number(hi, 0)} dBm")
    if kind == "int":
        return Raw(f"{int(value)}")
    if kind == "m2":
        return Raw(f"{number(value, 1)} m$^2$")
    if kind == "m":
        return Raw(f"{number(value, 2)} m")
    if kind == "s":
        return Raw(f"{number(value, 2)} s")
    if kind == "sci":
        return sci(value)
    if kind == "ris":
        return Raw(f"{int(value['num_rows']) * int(value['num_cols'])} "
                   f"({int(value['num_rows'])} $\\times$ "
                   f"{int(value['num_cols'])})")
    return Raw(number(value, 3))


def parameter_table(cfg: dict) -> str:
    """Tabel parameter default (§8) langsung dari config, tanpa ketik ulang."""
    rows = []
    for label, path, kind in PARAM_ROWS:
        try:
            rows.append([label, _fmt(_dig(cfg, path), kind)])
        except (KeyError, TypeError):
            continue
    return latex_table(
        ["Parameter", "Nilai"], rows,
        caption="Parameter sistem dan pelatihan.",
        label="tab:parameters", align="ll",
        notes=(r"Seluruh nilai dibaca langsung dari \texttt{configs/base.yaml} "
               "saat tabel ini dibuat; tidak ada yang diketik ulang."))
