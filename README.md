# RIS-ISAC-DRL (versi ramping)

Deep reinforcement learning untuk RIS-assisted integrated sensing and
communication pada skenario NLoS site-specific, dengan kanal dari NVIDIA
Sionna RT.

Sumber kebenaran tunggal untuk model, MDP, baseline, dan parameter adalah
[`docs/EXPERIMENT_DESIGN.md`](docs/EXPERIMENT_DESIGN.md). Jadwal, fase, dan
gate ada di [`docs/TASKS.md`](docs/TASKS.md); keputusan, kegagalan, dan
angka yang terukur dicatat bertanggal di [`docs/LOG.md`](docs/LOG.md).

## Reproduksi, dari instalasi sampai gambar

Waktu yang tertera **terukur** di mesin pengembangan (Intel i5-13600KF,
32 GB RAM, RTX 4070 12 GB, Windows 11). Tiap langkah menulis hasilnya ke
`results/<eksperimen>/<config_hash>/` beserta salinan config dan commit git,
sehingga langkah berikutnya tidak perlu mengulang yang sebelumnya.

### 0. Environment

```bash
conda create -n sionna-drl python=3.12
conda activate sionna-drl
pip install -r envs/requirements.txt
pip install -e .
python scripts/check_env.py            # Gate 0: versi + VRAM tercatat
```

Sionna RT terbaru tidak mendukung RIS, jadi kanal dibangun dengan pendekatan
hibrida per elemen (§4). **Tidak ada environment Sionna 0.19.2** di versi ini;
validasi E0 memakai model analitik.

### 1. Scene dan kelayakan (Gate 1) — ±3 menit, GPU

```bash
python scripts/run_e1_coverage.py --config base
```

Menghasilkan **F1** (tata letak) dan **F2** (peta cakupan dan SNR radar), serta
`gate1.json`. Gate 1 menuntut kaskade lewat RIS mengalahkan jalur langsung.

### 2. Basis data kanal dan validasi (Gate 2) — ±9 menit, GPU

```bash
python scripts/precompute_channels.py --config base --split all
python scripts/run_e0_validation.py --config base       # T1, F3
pytest -q
```

Prakomputasi: 280 lintasan, 42.000 titik penerima, **8,7 menit**, puncak VRAM
**4,40 GiB**. Jangan menjalankan proses GPU lain bersamaan. Uji implementasi E0
harus di bawah 0,1 dB (terukur **0,0144 dB**).

### 3. Model sinyal, tracker, baseline (Gate 3) — ±2 menit

```bash
python scripts/run_gate3_feasibility.py --config base
```

### 4. Environment RL (Gate 4) — ±5 menit, CPU

```bash
python scripts/run_gate4_smoke.py --config base
```

### 5. Pelatihan (Gate 5) — ±92 menit, CPU

```bash
JOBS=3 bash scripts/run_all_training.sh          # 21 run, bisa dilanjutkan
python scripts/run_gate5_check.py --config base  # F4
for c in gamma10 gamma16 kappa025 kappa050; do
    python scripts/run_gate5_check.py --config "$c" --methods ppo_po
done
```

**Paralelisme terukur:** JOBS=1 → 2.069 langkah/detik; JOBS=3 → 5.112 agregat;
**JOBS=4 gagal** (36 proses × torch melewati batas memori commit Windows) dan
meninggalkan proses yatim yang meracuni percobaan berikutnya. Jangan menyunting
`run_all_training.sh` selagi ia berjalan: bash membacanya per offset byte.

Tiap run menulis `done.json` dan dilewati pada pemanggilan ulang, jadi antrean
aman dihentikan di tengah.

### 6. Evaluasi (Gate 6) — ±25 menit, CPU + GPU

```bash
for c in base gamma10 gamma16 kappa025 kappa050; do
    python -m risisac.eval.evaluate --config "$c"      # T2 per config
done
python scripts/run_gate6_check.py                      # F5, F6, F8
python scripts/run_e4a.py --config base                # F7 (E4a)
python scripts/run_e5_e6.py --precompute-seconds 520.1 # T3 (E5 + E6)
```

Set test (50 lintasan × 3 seed derau = 150 episode per seed latih) baru
disentuh di langkah ini; seluruh penyetelan sudah beku sebelumnya.

### 7. Gambar dan tabel paper (Gate 7) — ±1 menit

```bash
python scripts/make_figures.py --config base    # F1-F8 (PNG + PDF) dan T1-T4
python scripts/check_equations.py               # persamaan <-> kode <-> tes
python scripts/run_gate7_check.py               # ketiganya sekaligus
```

`make_figures.py` **tidak menghitung ulang apa pun**: ia membaca file hasil,
menggambar ulang, dan menulis ke `results/paper/<config_hash>/` beserta
`manifest.json` yang mencatat asal tiap artefak. Tujuh dari sembilan PDF murni
vektor; F2 dan F2b memuat raster karena keduanya peta panas.

## Perintah harian

| Tujuan | Perintah |
|---|---|
| Tes | `pytest -q` |
| Link budget kasar | `python scripts/link_budget.py --m 64 --d-bs-ris 20 --L 4096` |
| Satu run pelatihan | `python -m risisac.train.train --config base --method ppo_po --seed 0` |
| Tabel parameter LaTeX | `python scripts/print_param_table.py --config base` |

## Catatan reproduksibilitas

- **Semua parameter dari `configs/*.yaml`**; tidak ada angka parameter di kode.
  Setiap skrip menerima `--seed`, dan seluruh RNG diturunkan dari seed itu.
- **`config_hash` dihitung dari SELURUH config**, sehingga menambah satu kunci
  yang tidak relevan pun mengganti nama direktori hasil. `make_figures.py`
  menanganinya dengan membandingkan `config_used.json` tiap kandidat dan hanya
  menerima yang selisihnya seluruhnya pada kunci yang dinyatakan tidak relevan;
  kalau tidak ada yang lolos ia berhenti dan mencetak selisihnya, tidak pernah
  diam-diam memakai hasil basi.
- **`channel_config_hash`** sengaja lebih sempit daripada `config_hash`, supaya
  mengubah ambang gate atau parameter reward tidak memaksa ray tracing ulang.
  Pembagiannya eksplisit di `src/risisac/config.py` dan diuji.
- **File kanal, checkpoint, dan hasil tidak masuk git.** Yang masuk git adalah
  kode, config, dan dokumen; hasil dibuat ulang dari ketiganya.

## Kebutuhan perangkat

- GPU NVIDIA 12 GB untuk prakomputasi ray tracing dan Oracle-GD.
- CPU multi-core untuk pelatihan PPO (pelatihan **tidak** memakai GPU).
- Ruang disk kecil: basis data kanal ±28 MB, seluruh hasil di bawah 1 GB.
