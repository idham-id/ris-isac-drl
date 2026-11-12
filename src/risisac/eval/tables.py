r"""Tabel LaTeX untuk paper (docs/EXPERIMENT_DESIGN.md §11, docs/TASKS.md Fase 7).

Tabel dibangun dari **file hasil**, bukan dari angka yang diketik ulang, dengan
alasan yang sama seperti gambar: satu sumber kebenaran, dan tabel yang tidak
bisa diam-diam menyimpang dari data.

Keluarannya LaTeX mentah dengan ``booktabs`` (``\toprule`` dst.) dan tanpa
paket tambahan: tidak ada ``siunitx``, tidak ada ``\begin{document}``. Berkas
hasilnya untuk di-``\input`` dari manuskrip.

**Bahasa keluaran: Inggris, dengan titik desimal** (Fase 9). Komentar dan
docstring tetap bahasa Indonesia; keduanya untuk yang mengerjakan kode.

**Tidak ada kode "T#" di ``\caption``** (Fase 9). Nomor tabel diatur LaTeX
lewat urutan ``\begin{table}``, dan ``\label`` sudah menyediakan rujukan
silangnya; menuliskannya juga di dalam caption berarti dua sumber kebenaran
yang pasti berselisih begitu satu tabel dipindahkan. Nama BERKAS tetap
memakai awalan ``T1_``..``T6_``.

Fase 10: T3 dipecah menjadi dua berkas (``T3_ablation.tex`` dan
``T6_latency.tex``) supaya manuskrip bisa menempatkannya di halaman berbeda;
ditambah ``T5_behaviour.tex`` (perilaku per langkah) dan
``T_baselines.tex`` (ikhtisar metode, §6).
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
    ``$M$ (rows $\times$ columns)``, yang berawalan ``$`` tetapi tidak
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
    r"""Format angka untuk tabel paper: **titik desimal** (Fase 9).

    Tanda ditulis sebagai ``$-$`` / ``$+$``, bukan ``-`` / ``+``: di mode teks
    LaTeX, ``-`` adalah tanda HUBUNG dan tercetak jauh lebih pendek daripada
    tanda minus. Pada tabel yang dibuat otomatis, cacat kecil itu akan muncul
    di setiap baris negatif tanpa ada yang memperbaikinya satu per satu.
    """
    if value is None or (isinstance(value, float) and not np.isfinite(value)):
        return Raw("--")
    text = f"{float(value):+.{digits}f}" if plus else f"{float(value):.{digits}f}"
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
            else f"{mant:.1f}")
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
#: Nama profil fasa RIS yang diuji E0, dari kunci di ``T1_e0.json`` ke label
#: paper (Fase 10). Dipetakan di SINI, bukan di skrip E0: mengganti kuncinya
#: berarti menjalankan ulang ray tracing hanya demi teks. ``fokus_0`` adalah
#: fokus PERTAMA, jadi penomoran paper mulai dari 1, bukan dari 0.
PROFILE_LABELS = {"fokus_0": "Focus 1", "fokus_1": "Focus 2",
                  "fokus_2": "Focus 3", "gradien": "Gradient"}


def profile_label(name: str) -> str:
    """Label paper untuk satu profil fasa E0; tak dikenal -> apa adanya."""
    return PROFILE_LABELS.get(str(name), str(name))


def t1_channel_validation(e0: dict) -> str:
    """T1 -- galat validasi kanal, dari ``results/e0/<hash>/T1_e0.json``."""
    per = e0["per_element"]
    rows = [
        [Raw(r"Per-element amplitude, $\mathbf{G}$ (BS--RIS)"),
         number(per["G_amplitude_max_db"], 4), "dB"],
        [Raw(r"Per-element amplitude, $\mathbf{g}$ (RIS--point)"),
         number(per["g_amplitude_max_db"], 4), "dB"],
        [Raw(r"Per-element phase, $\mathbf{G}$"),
         number(per["G_phase_max_deg"], 4), "deg"],
        [Raw(r"Per-element phase, $\mathbf{g}$"),
         number(per["g_phase_max_deg"], 4), "deg"],
    ]
    for name, item in e0["cascade"].items():
        rows.append([f"Cascade, {profile_label(name)} profile",
                     number(item["max_abs_db"], 4), "dB"])
    rows.append(["Calibration against Tang et al. (2021), Eq. (6)",
                 number(e0["calibration_db"], 2), "dB"])
    worst = max(float(i["max_abs_db"]) for i in e0["cascade"].values())
    return latex_table(
        ["Quantity under test", "Difference", "Unit"], rows,
        caption=("Validation of the hybrid channel model against the "
                 "analytic model (E0)."),
        label="tab:t1-channel-validation", align="lrl",
        notes=(f"Implementation-test tolerance {number(e0['tolerance_db'], 1)} "
               f"dB; worst difference {number(worst, 4)} dB. "
               r"\texttt{calibration\_db} is recorded, not applied to the "
               "channel."))


# ------------------------------------------------------------------- T2 (E3)
#: Kolom T2: (kunci di T2.csv, judul kolom, digit, pakai tanda +).
T2_FIELDS = ((("reward_per_step"), "Reward/step", 3, True),
             ("min_rate", "Min. rate", 2, False),
             ("scnr_compliance", "SCNR compliance", 3, False),
             ("track_duration_s", "Track duration (s)", 2, False),
             ("tracker_error_m", "Tracker error (m)", 2, False))

#: Nama metode di paper. Kunci-kunci ini SAMA dengan kunci di file hasil dan
#: nama direktori run; yang berubah di Fase 8 hanya teks tampilannya, supaya
#: pembaca tabel langsung melihat mana metode utama dan mana ablasi.
METHOD_LABELS = {"B0": "B0 No-RIS",
                 "B1": "B1 Random", "B2": "B2 Geometric",
                 "B3": "B3 Oracle-GD", "B4-D5": "B4 Oracle-GD-stale(5)",
                 "B4-D10": "B4 Oracle-GD-stale(10)",
                 "A1": "A1 PPO-PO-absolute (main)",
                 "A1-FullCSI": "A1-FullCSI PPO-absolute, full CSI",
                 "M1": "M1 PPO-PO (incremental-phase ablation)",
                 "M2": "M2 PPO-FullCSI (incremental-phase ablation)"}

#: Urutan baris tabel: sama dengan ``eval.evaluate.METHOD_ORDER`` dan
#: ``eval.plots.METHOD_ORDER``. Diturunkan dari urutan kunci METHOD_LABELS,
#: bukan diketik ulang untuk ketiga kalinya.
METHOD_ORDER = tuple(METHOD_LABELS)


def t2_main_results(t2, gamma_db: float, p_max_dbm: float,
                    with_ci: bool = True) -> str:
    """T2 -- hasil utama set test, dari ``T2.csv`` (indeks = metode)."""
    header = ["Method", "Episodes"] + [h for _, h, _, _ in T2_FIELDS]
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
    # Catatan sensor (Fase 10). Durasi track DIPERTAHANKAN sebagai kolom --
    # ia tetap membedakan metode di ujung bawah -- tetapi angkanya tersensor
    # dari atas oleh panjang episode: episode yang tracknya tidak pernah
    # hilang dilaporkan sepanjang episodenya, bukan sepanjang track yang
    # sebenarnya. Tanpa kalimat ini, "3,69 s" terbaca sebagai pengukuran
    # padahal ia batas bawah untuk sebagian besar metode.
    censored = ""
    if "track_censored" in getattr(t2, "columns", []):
        share = 100.0 * float(t2["track_censored"].max())
        worst = ", ".join(str(m) for m in t2.index
                          if float(t2.loc[m, "track_censored"]) >= 1.0)
        censored = (" Track duration is censored from above by the episode "
                    "length: an episode whose track is never lost is reported "
                    f"at its full length, which happens for up to {share:.0f}"
                    "\\% of episodes"
                    + (f" ({worst})" if worst else "")
                    + ", so for those rows the value is a lower bound, not a "
                      "measured survival time.")
    return latex_table(
        header, rows,
        caption=(f"Test-set results, $\\Gamma$ = {gamma_db:g} dB, "
                 f"$P_{{max}}$ = {p_max_dbm:g} dBm."),
        label="tab:t2-main-results", align="l" + "r" * (len(header) - 1),
        notes=("Brackets: 95\\% bootstrap confidence interval over episodes, "
               "clustered by seed. Agents are reported at their best "
               "validation checkpoint. B0 removes the RIS cascade entirely "
               "and is given perfect direct CSI: it is the floor of a "
               "RIS-free system, not a realistic RIS-free system. B3/B4 use "
               "perfect CSI and perfect positions: upper references, not "
               "deployable methods." + censored))


# ---------------------------------------------------------------- T3 (E5+E6)
#: Label baris T3a, dipetakan dari kolom ``metode`` dan ``config`` di
#: ``T3_e5_ablation.csv``. Dipetakan di SINI, bukan dibaca dari kolom
#: ``varian``, supaya tabel bisa diterjemahkan tanpa menjalankan ulang E5 --
#: dan E5 memuat pengukuran waktu E6 yang memang tidak boleh diulang hanya
#: demi teks (Fase 9: "tanpa menghitung ulang apa pun").
E5_LABELS = {
    ("A1", "base"): Raw("A1 absolute phase, partial obs. (main)"),
    ("A1-FullCSI", "base"): Raw("A1-FullCSI absolute phase, full obs."),
    ("M1", "base"): Raw(r"M1 incremental phase, $\kappa$ = 0.10"),
    ("M1", "kappa025"): Raw(r"M1 incremental phase, $\kappa$ = 0.25"),
    ("M1", "kappa050"): Raw(r"M1 incremental phase, $\kappa$ = 0.50"),
    ("M2", "base"): Raw("M2 incremental phase, full CSI"),
    ("B0", "base"): Raw("B0 no RIS (perfect direct CSI)"),
    ("B2", "base"): Raw("B2 geometric (absolute phase)"),
    ("B3", "base"): Raw("B3 oracle (absolute phase)"),
}


def _e5_label(row):
    """Label satu baris E5; jatuh kembali ke kolom ``varian`` bila tak dikenal."""
    key = (str(row.get("metode", "")), str(row.get("config", "")))
    return E5_LABELS.get(key, row["varian"])


def t3_ablation(e5) -> str:
    """T3a -- ablasi parameterisasi fasa DAN observasi pada set test (E5).

    Dua ablasi dalam satu tabel karena keduanya menjawab pertanyaan yang sama
    bentuknya: berapa harga satu pilihan desain, diukur pada metode utama.
    Baris A1 lawan A1-FullCSI mengisolasi **observasi** (keduanya fasa
    absolut); baris A1 lawan M1/M2 beserta sapuan kappa mengisolasi
    **parameterisasi fasa**.
    """
    rows = [[_e5_label(row), f"{int(row['episode'])}",
             number(row["reward_per_step"], 3, True),
             number(row["min_rate"], 2),
             number(row["scnr_compliance"], 3)]
            for _, row in e5.iterrows()]
    note = ("All rows share the same $\\lambda$, geometry and step budget; "
            "only the phase parameterisation, $\\kappa$ or observation mode "
            "differs. ")
    by_method = {str(r["metode"]): r for _, r in e5.iterrows()
                 if "metode" in e5.columns}
    if {"A1", "A1-FullCSI"} <= set(by_method):
        delta = (float(by_method["A1-FullCSI"]["reward_per_step"])
                 - float(by_method["A1"]["reward_per_step"]))
        note += ("Observation ablation on the main method, A1-FullCSI minus "
                 f"A1: {number(delta, 3, True)} reward per step. A negative "
                 "value means full CSI does NOT help; see Sec. IX for the "
                 "significance test.")
    return latex_table(
        ["Variant", "Episodes", "Reward/step", "Min. rate",
         "SCNR compliance"], rows,
        caption=("Ablation of the phase parameterisation and of the "
                 "observation on the test set (E5)."),
        label="tab:t3-ablation", notes=note)


def t6_latency(cost: dict) -> str:
    """T6 -- biaya komputasi per keputusan (E6).

    Berkas tersendiri sejak Fase 10. Sebelumnya ia menumpang di berkas T3
    bersama ablasi, sehingga manuskrip harus memuat dua ``table`` dari satu
    ``\\input`` dan tidak bisa menempatkannya di halaman berbeda.
    """
    rows = []
    for paper_id, item in cost.get("agents", {}).items():
        rows.append([METHOD_LABELS.get(paper_id, paper_id),
                     number(item["ms_per_decision"], 3),
                     f"CPU, observation {item['observation_dim']}"])
    b2 = cost.get("baselines", {}).get("B2")
    if b2:
        rows.append([METHOD_LABELS["B2"],
                     number(b2["ms_per_decision"], 3), "CPU"])
    b3 = cost.get("baselines", {}).get("B3")
    if b3:
        rows.append([METHOD_LABELS["B3"] + " (online)",
                     number(b3["ms_per_decision_online"], 1),
                     Raw(f"{b3['device'].upper()}, {b3['iterations']} "
                         f"iterations $\\times$ {b3['restarts']} restarts")])
        rows.append([METHOD_LABELS["B3"] + " (amortised)",
                     number(b3["ms_per_decision_batched"], 2),
                     f"{b3['device'].upper()}, {b3['batch_steps']} steps "
                     f"batched at once"])
    note = "Time for one decision, measured on the same machine. "
    for paper_id, key in (("A1", "a1_vs_b3_online_speedup"),
                          ("M1", "m1_vs_b3_online_speedup")):
        speedup = cost.get(key)
        if speedup:
            note += (f"{paper_id} is {int(round(speedup)):,}"
                     "$\\times$ faster than online B3. ")
    note += ("The amortised figure applies only to an offline reference whose "
             "every step is optimised in one batch, not to a controller.")
    return latex_table(["Method", "ms per decision", "Device"], rows,
                       caption="Inference cost per decision (E6).",
                       label="tab:t6-latency", align="lrl", notes=note)


# ------------------------------------------------------- tabel metode (§6)
#: Satu baris per metode: apa yang ia putuskan, informasi apa yang dipakainya,
#: dan di mana ia disetel. Isinya adalah docs/EXPERIMENT_DESIGN.md §6.1 dan
#: §6.2 yang dipindahkan ke bentuk tabel, DITULIS DI SINI dan bukan dibaca
#: dari file hasil: ia menggambarkan desain, bukan mengukur sesuatu, jadi
#: tidak ada file hasil yang bisa menjadi sumbernya. Konsekuensinya satu dan
#: dinyatakan terbuka: kalau §6 berubah, baris ini harus ikut diubah.
#:
#: Kolom "CSI used for precoding" sengaja dipisahkan dari observasi, karena di
#: situlah letak satu-satunya kesalahpahaman yang mudah terjadi pada tabel
#: ini: A1-FullCSI dan M2 melihat kanal per elemen DI OBSERVASINYA, tetapi
#: precoder-nya tetap memakai kanal efektif yang diestimasi dengan NMSE yang
#: sama seperti A1. "Full CSI" di nama metodenya menyangkut apa yang dilihat
#: agen, bukan apa yang dipakai BS untuk membentuk W_c.
BASELINE_ROWS = (
    ("B0", Raw("None (RIS cascade removed)"),
     Raw(r"Perfect direct $\mathbf{h}_d$"),
     Raw(r"True $\mathbf{h}_{d,t}$ (MRT sensing beam)"),
     Raw(r"Val grid ($\rho$, power split)")),
    ("B1", Raw("Absolute, i.i.d. uniform each step"),
     Raw(r"Estimated $\hat{\mathbf{h}}_e$, NMSE $\epsilon$"),
     Raw("Tracker estimate"), Raw(r"Val grid ($\rho$)")),
    ("B2", Raw("Absolute, closed form from estimated positions"),
     Raw(r"Estimated $\hat{\mathbf{h}}_e$, NMSE $\epsilon$"),
     Raw("Tracker estimate"), Raw(r"Val grid ($\omega$, $\rho$)")),
    ("B3", Raw("Absolute, Adam per step (300 iterations, 4 restarts)"),
     Raw(r"Perfect $\mathbf{h}_e$"), Raw(r"True $\mathbf{g}_t$"),
     Raw("Not tuned (re-optimised every step)")),
    ("B4-D", Raw("Absolute, B3 re-run every $D$ steps and held"),
     Raw(r"Perfect $\mathbf{h}_e$, up to $D-1$ steps stale"),
     Raw(r"True $\mathbf{g}_t$, same staleness"),
     Raw(r"Not tuned ($D \in \{5, 10\}$ fixed)")),
    ("A1", Raw("Absolute, learned"),
     Raw(r"Estimated $\hat{\mathbf{h}}_e$, NMSE $\epsilon$"),
     Raw("Tracker estimate"), Raw("Val (best checkpoint)")),
    ("A1-FullCSI", Raw("Absolute, learned"),
     Raw(r"Estimated $\hat{\mathbf{h}}_e$, NMSE $\epsilon$"),
     Raw(r"True positions and $\mathbf{g}$ in the observation"),
     Raw("Val (best checkpoint)")),
    ("M1", Raw(r"Incremental, $\kappa \pi$ per step"),
     Raw(r"Estimated $\hat{\mathbf{h}}_e$, NMSE $\epsilon$"),
     Raw("Tracker estimate"), Raw("Val (best checkpoint)")),
    ("M2", Raw(r"Incremental, $\kappa \pi$ per step"),
     Raw(r"Estimated $\hat{\mathbf{h}}_e$, NMSE $\epsilon$"),
     Raw(r"True positions and $\mathbf{g}$ in the observation"),
     Raw("Val (best checkpoint)")),
)


def baselines_table() -> str:
    """Tabel ikhtisar metode dan baseline (§6.1, §6.2)."""
    rows = [[Raw(METHOD_LABELS.get(key, key) if key != "B4-D"
                 else "B4 Oracle-GD-stale($D$)"), *cells]
            for key, *cells in BASELINE_ROWS]
    return latex_table(
        ["Method", "Phase action", "CSI used for precoding",
         "Target information", "Tuned on"], rows,
        caption="Methods and baselines: what each one decides and what it "
                "is allowed to know.",
        label="tab:baselines", align="lllll",
        notes=(r"$\epsilon$ is the effective-channel NMSE in Table~"
               r"\ref{tab:parameters}. The sensing beam $\mathbf{w}_s$ is "
               "built from the tracker estimate for every method except B0, "
               "B3 and B4, including the two that observe the true positions "
               "(A1-FullCSI, M2): full observation changes what the agent "
               "sees, not how the BS forms its precoders. B1--B4 and B0 run "
               "with absolute phase updates because the random and the "
               "closed-form rules are undefined on incremental actions; this "
               "favours the baselines over M1/M2, not the other way round."))


# ------------------------------------------------------------- T5 (perilaku)
#: Kolom T5: (kunci di T5_behaviour.csv, judul kolom, digit).
T5_FIELDS = ((Raw(r"$\bar{\rho}$"), "rho_mean", 4),
             (Raw(r"$\rho_{95}$"), "rho_p95", 4),
             (Raw("SCNR med."), "scnr_median_db", 1),
             (Raw(r"SCNR $p_5$"), "scnr_p5_db", 1),
             (Raw(r"$R_{\min}$ $p_5$"), "min_rate_p5", 2),
             (Raw(r"$R_{\min}$ $p_{10}$"), "min_rate_p10", 2),
             (Raw(r"$R_{\min}$ $p_{50}$"), "min_rate_p50", 2),
             (Raw(r"Steps $<\Gamma$"), "violation_fraction", 3),
             (Raw("Shortfall"), "mean_shortfall_db", 2))


def t5_behaviour(behaviour, gamma_db: float, tests: dict | None = None) -> str:
    """T5 -- perilaku per langkah: daya sensing, ekor SCNR, ekor rate (E3).

    Tabel ini menjawab pertanyaan yang T2 tidak jawab. T2 melaporkan
    rata-rata; di sini yang dilaporkan adalah **ekor**, dan dua kolom
    terakhir memisahkan "seberapa sering melanggar" dari "seberapa dalam
    melanggarnya" -- dua metode bisa punya pemenuhan SCNR yang sama dengan
    kedalaman pelanggaran yang sangat berbeda.
    """
    header = ["Method"] + [h for h, _, _ in T5_FIELDS]
    rows = []
    for method, row in behaviour.iterrows():
        cells = [METHOD_LABELS.get(method, method)]
        for _, key, digits in T5_FIELDS:
            cells.append(number(row[key], digits))
        rows.append(cells)
    note = (r"Per-step quantities on the test set. $\bar{\rho}$ and "
            r"$\rho_{95}$ are the mean and the 95th percentile of the sensing "
            r"power share; SCNR percentiles are in dB; $R_{\min}$ percentiles "
            r"are in bit/s/Hz. ``Steps $<\Gamma$'' is the fraction of steps "
            r"below the threshold, i.e. one minus the SCNR compliance of "
            r"Table~\ref{tab:t2-main-results}; ``Shortfall'' is the mean of "
            r"$\Gamma - \mathrm{SCNR}$ in dB over those steps only, so a "
            "method that never violates has no shortfall (--) rather than "
            "zero. ")
    note += _welch_sentence(tests)
    return latex_table(header, rows,
                       caption=(f"Per-step behaviour on the test set, "
                                f"$\\Gamma$ = {gamma_db:g} dB."),
                       label="tab:t5-behaviour",
                       align="l" + "r" * (len(header) - 1), notes=note)


def _welch_sentence(tests: dict | None) -> str:
    """Kalimat uji Welch untuk catatan kaki T5, dari file stats.

    Dikelompokkan per PASANGAN, bukan per metrik: sembilan klausa sejajar
    tidak terbaca sebagai apa pun, sedangkan tiga klausa yang masing-masing
    memuat tiga angka langsung menjawab "A1 lebih baik daripada apa, dan di
    besaran mana".
    """
    if not tests:
        return ""
    labels = {"reward_per_step": "reward", "min_rate": "min. rate",
              "scnr_compliance": "SCNR compliance"}
    by_pair: dict[str, list] = {}
    for key, item in tests.items():
        column, pair = key.split("|", 1)
        by_pair.setdefault(pair, []).append((column, item))
    parts = []
    for pair, items in by_pair.items():
        a, b = pair.split("_vs_")
        inner = ", ".join(
            f"{labels.get(column, column)} {number(item['diff'], 3, True)} "
            f"($p$ = {float(item['p']):.4f}, $d$ = {number(item['cohen_d'], 0)})"
            for column, item in items)
        parts.append(f"A1 $-$ {b}: {inner}" if a == "A1"
                     else f"{a} $-$ {b}: {inner}")
    return ("Welch $t$-tests over per-seed means, $n$ = 3 seeds: the power is "
            "low and the effect sizes are correspondingly unstable, so the "
            "signs matter and the magnitudes of $d$ do not. "
            + "; ".join(parts) + ".")


# ------------------------------------------------------------ tabel parameter
#: Baris tabel parameter: (label LaTeX, jalur di config, format).
PARAM_ROWS = (
    (Raw("$f_c$"), ("radio", "carrier_frequency_hz"), "ghz"),
    (Raw("$B$"), ("radio", "bandwidth_hz"), "mhz"),
    (Raw("Noise figure"), ("radio", "noise_figure_db"), "db"),
    (Raw("$N_t = N_r$"), ("radio", "bs", "num_tx"), "int"),
    (Raw(r"$M$ (rows $\times$ columns)"), ("radio", "ris"), "ris"),
    (Raw("$P_{max}$ (evaluation)"), ("radio", "p_max_dbm"), "dbm"),
    (Raw("$P_{max}$ (training)"), ("radio", "p_max_train_range_dbm"),
     "range_dbm"),
    (Raw("$K$ users"), ("radio", "user", "num_users"), "int"),
    (Raw("$Q$ targets"), ("radio", "target", "num_targets"), "int"),
    (Raw(r"$\sigma_{rcs}$"), ("radio", "target", "rcs_m2"), "m2"),
    (Raw("$L$ (integration samples)"), ("sensing", "integration_samples"),
     "int"),
    (Raw(r"$\xi$ (clutter residual)"), ("sensing", "clutter_residual"),
     "plain"),
    (Raw(r"$\Gamma$"), ("sensing", "scnr_threshold_db"), "db"),
    (Raw(r"$\Delta t$"), ("mobility", "dt_s"), "s"),
    # Satu baris, bukan "T = 50": episode berakhir pada 50 langkah ATAU saat
    # target meninggalkan ROI, mana yang lebih dulu, dan di set test yang
    # kedua lebih sering (lihat baris berikutnya, yang diukur).
    (Raw("Episode length"), ("mobility", "episode_steps"), "episode"),
    (Raw(r"$\kappa$ (M1/M2 ablation only)"),
     ("action", "phase_step_kappa"), "plain"),
    # Bobot hinge ditulis mu di paper, bukan lambda: lambda sudah dipakai GAE
    # di baris hiperparameter PPO, dan dua lambda dalam satu tabel adalah
    # cacat yang pasti ditanyakan pengulas. Di config dan kode namanya tetap
    # `reward.lambda` / `reward_lambda`; catatan kaki menyatakan pemetaannya.
    (Raw(r"$\mu$ (hinge weight)"), ("reward", "lambda"), "plain"),
    (Raw(r"$\epsilon$ (channel NMSE)"), ("observation", "eff_channel_nmse_db"),
     "db"),
    (Raw(r"$\sigma_u$"), ("observation", "user_pos_std_m"), "m"),
    (Raw(r"$\sigma_{ref}$"), ("observation", "target_pos_ref_std_m"), "m"),
    (Raw(r"$\sigma_{max}$"), ("observation", "target_pos_max_std_m"), "m"),
    (Raw(r"Ray tracing: \texttt{max\_depth}"), ("ray_tracing", "max_depth"),
     "int"),
    (Raw(r"Ray tracing: \texttt{samples\_per\_src}"),
     ("ray_tracing", "samples_per_src"), "sci"),
    (Raw(r"$\gamma$ (discount)"), ("training", "gamma"), "plain"),
    (Raw("PPO learning rate"), ("training", "ppo", "learning_rate"), "sci"),
    (Raw("Training steps"), ("training", "total_timesteps"), "sci"),
    (Raw("Training seeds"), ("training", "num_seeds"), "int"),
)


def _dig(cfg: dict, path):
    node = cfg
    for key in path:
        node = node[key]
    return node


def _fmt(value, kind: str) -> Raw:
    if kind == "ghz":
        return Raw(f"{float(value) / 1e9:g} GHz")
    if kind == "mhz":
        return Raw(f"{float(value) / 1e6:g} MHz")
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
    if kind == "episode":
        return Raw(f"up to {int(value)} steps (ends when the target leaves "
                   "the ROI)")
    if kind == "ris":
        return Raw(f"{int(value['num_rows']) * int(value['num_cols'])} "
                   f"({int(value['num_rows'])} $\\times$ "
                   f"{int(value['num_cols'])})")
    return Raw(number(value, 3))


def parameter_table(cfg: dict, episode_stats: dict | None = None,
                    sweep_steps: dict | None = None) -> str:
    """Tabel parameter default (§8) langsung dari config, tanpa ketik ulang.

    :param episode_stats: keluaran
        :func:`risisac.eval.metrics.episode_length_stats`. Bila diberikan,
        satu baris TERUKUR ditambahkan: panjang episode di set test. Ia tidak
        ada di config -- ia akibat geometri ROI dan lintasan -- jadi ia datang
        dari file hasil, bukan dari angka yang diketik. Tanpa argumen ini
        (``print_param_table.py``) barisnya dilewati, bukan ditebak.
    """
    rows = []
    for label, path, kind in PARAM_ROWS:
        try:
            rows.append([label, _fmt(_dig(cfg, path), kind)])
        except (KeyError, TypeError):
            continue
    notes = (r"Every value is read directly from \texttt{configs/base.yaml} "
             "when this table is generated; none is retyped. The hinge "
             r"weight $\mu$ is \texttt{reward.lambda} in the configuration "
             r"files; it is written $\mu$ here because $\lambda$ already "
             "denotes the GAE parameter.")
    if episode_stats:
        rows.append([
            Raw(r"$T$ (test set: mean / min / max)"),
            Raw(f"{float(episode_stats['mean']):.1f} / "
                f"{int(episode_stats['min'])} / "
                f"{int(episode_stats['max'])} steps")])
        notes += (" The episode-length row is measured on the test set "
                  f"({int(episode_stats['n_episodes'])} episodes over "
                  f"{int(episode_stats['n_trajectories'])} trajectories); it "
                  "is a property of the trajectories, not of the policy, so "
                  "it is identical for every method.")
    if sweep_steps:
        # Satu kalimat yang mencegah satu-satunya pertanyaan yang pasti
        # muncul dari baris "Training steps": anggaran sapuan Gamma berbeda
        # dari anggaran utama, dan angkanya dibaca dari config sapuan itu
        # sendiri, bukan diketik ulang dari dokumen desain.
        listed = ", ".join(f"$\\Gamma$ = {float(gamma):g} dB: {sci(value)}"
                           for gamma, value in sorted(sweep_steps.items()))
        notes += (" The training-steps row is the budget of the main runs; "
                  f"the $\\Gamma$ sweep overrides it ({listed}) for M1 only, "
                  "whose validation curve is still rising at "
                  "$1 \\times 10^{6}$ steps there, while A1 has already "
                  "passed its peak.")
    return latex_table(
        ["Parameter", "Value"], rows,
        caption="System and training parameters.",
        label="tab:parameters", align="ll", notes=notes)
