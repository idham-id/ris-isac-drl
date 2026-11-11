# CLAUDE.md — Proyek RIS-ISAC-DRL (versi ramping)

## Tujuan proyek
Paper jurnal Q2 tentang DRL untuk RIS-assisted ISAC pada skenario NLoS site-specific dengan observasi parsial dan target bergerak, memakai NVIDIA Sionna RT untuk kanal. **Tenggat < 2 bulan, PC dengan GPU 12 GB.** Prioritas: kebenaran fisik dan konsistensi paper–kode, lalu kecepatan. Jangan menambah fitur di luar cakupan dokumen desain.

## Dokumen yang wajib dibaca
1. `docs/EXPERIMENT_DESIGN.md` (v0.2-lean) — sumber kebenaran tunggal untuk model (E1–E9), MDP, baseline, eksperimen, prioritas P1/P2/P3, dan parameter.
2. `docs/TASKS.md` — jadwal 8 minggu, fase, gate, dan titik keputusan.
3. `docs/LOG.md` — catatan keputusan dan masalah (buat jika belum ada; entri bertanggal).

## Aturan kerja
- Kerjakan satu fase pada satu waktu. Sebelum pindah fase, jalankan pemeriksaan gate dan laporkan hasilnya.
- **Jangan mengubah asumsi fisik, rumus, atau reward tanpa persetujuan.** Jika perlu, usulkan, lalu perbarui dokumen desain dan kode bersamaan.
- Fungsi yang mengimplementasikan rumus mencantumkan nomor persamaan di docstring dan punya tes unit.
- Tidak ada angka parameter di kode; semua dari `configs/*.yaml`.
- **API Sionna berubah antarversi.** Cek dokumentasi atau source versi terpasang, jangan mengandalkan ingatan. Catat versi di `docs/LOG.md`.
- Sionna RT terbaru tidak mendukung RIS: gunakan pendekatan hibrida (§4). **Tidak ada environment Sionna 0.19.2** di versi ini; validasi E0 memakai model analitik.
- Environment RL (`src/risisac/env`) **tidak boleh** mengimpor Sionna; hanya membaca HDF5.
- Setiap skrip menerima `--seed`; semua RNG diturunkan dari seed itu.
- Hasil ke `results/<eksperimen>/<config_hash>/<seed>/` beserta salinan config dan git commit. Gambar dibuat dari file hasil.
- File kanal, checkpoint, dan hasil tidak masuk git.
- Jika jadwal mundur, usulkan pemotongan P3 lalu P2. Jangan memotong P1 tanpa persetujuan.

## Batasan perangkat (GPU 12 GB)
- Ray tracing: batch penerima (`rx_batch_size`, mulai 256) dan `samples_per_src` mulai 1e5. Jika OOM, kecilkan dulu; jika tetap OOM, pakai varian Dr.Jit LLVM (CPU).
- Catat puncak VRAM dan waktu prakomputasi di `docs/LOG.md`.
- Pelatihan PPO di **CPU** (MLP kecil, env NumPy). Oracle-GD boleh di GPU.
- Jangan menjalankan ray tracing dan proses GPU lain bersamaan.

## Konvensi notasi di kode
| Desain | Kode | Bentuk array |
|---|---|---|
| **G** (BS-tx → RIS) | `G` | `(M, Nt)` |
| **H** (RIS → BS-rx) | `H` | `(Nr, M)` |
| **H**_c | `Hc` | `(Nr, Nt)` |
| **g**_k | `g_user` | `(..., K, M)` |
| **g**_t | `g_tgt` | `(..., Q, M)` |
| **h**_{d,k} | `hd_user` | `(..., K, Nt)` |
| **h**_{d,t}, **h**^{(r)}_{d,t} | `hd_tgt_tx`, `hd_tgt_rx` | `(..., Q, Nt)`, `(..., Q, Nr)` |
| φ | `phi` | `(..., M)`, radian [0, 2π) |
| **W**_c, **w**_s | `Wc`, `ws` | `(..., Nt, K)`, `(..., Nt)` |
| η = 4πσ_rcs/λ_c² | `eta` | skalar |

Kanal `complex64`. Daya dalam Watt di kode; dBm/dB hanya di config dan plot. Panjang gelombang ditulis `wavelength`, bukan `lam`, agar tidak tertukar dengan bobot reward `reward_lambda`.

## Struktur repo
```
configs/            base.yaml + override eksperimen
docs/               EXPERIMENT_DESIGN.md, TASKS.md, LOG.md
envs/               requirements.txt
scripts/            check_env, link_budget, precompute_channels, run_all_training.sh, make_figures, print_param_table
src/risisac/
  scene/            synthetic_l, placement
  channels/         geometry, rt_extract, database, validate_analytic
  mobility/         trajectories
  system/           signal_model, precoding, ris
  tracking/         kalman
  env/              ris_isac_env
  baselines/        random_policy, geometric, oracle_gd
  train/            train
  eval/             evaluate, metrics, plots
tests/
results/            (diabaikan git)
data/channels/      (diabaikan git)
```

## Perintah umum (lengkapi setelah Fase 0)
- Tes: `pytest -q`
- Link budget kasar: `python scripts/link_budget.py --m 64 --d-bs-ris 20 --L 4096`
- Prakomputasi kanal: `python scripts/precompute_channels.py --config configs/base.yaml --split train`
- Latih: `python -m risisac.train.train --config configs/base.yaml --method ppo_po --seed 0`

## Pelajaran dari proyek sebelumnya (jangan diulang)
- Kode dan paper pernah tidak cocok (model kanal, ukuran RIS, reward, pembanding). Cocokkan kembali dengan dokumen desain setiap selesai fase.
- Kanal statis yang dibangkitkan sekali membuat masalah menjadi bandit. Di sini state bergantung pada aksi dan waktu.
- Reward sensing menghukum SCNR **di bawah** ambang.
- `env.step` mengembalikan 5 nilai sesuai Gymnasium.
- Faktor η = 4πσ_rcs/λ² wajib ada di SCNR (E6–E7); tanpa itu SNR radar meleset sekitar 32 dB.
