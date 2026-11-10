# CLAUDE.md — Proyek RIS-ISAC-DRL

## Tujuan proyek
Riset DRL untuk RIS-assisted ISAC pada skenario NLoS site-specific dengan observasi parsial dan target bergerak, memakai NVIDIA Sionna RT untuk kanal. Hasil akhirnya adalah paper jurnal, jadi **kebenaran fisik, reproduksibilitas, dan konsistensi paper–kode lebih penting daripada kecepatan.**

## Dokumen yang wajib dibaca
1. `docs/EXPERIMENT_DESIGN.md` — sumber kebenaran tunggal untuk model sistem (E1–E9), MDP, baseline, eksperimen, dan parameter.
2. `docs/TASKS.md` — urutan kerja per fase dengan gate.
3. `docs/LOG.md` — catatan keputusan dan masalah (buat jika belum ada; tambahkan entri bertanggal).

## Aturan kerja
- Kerjakan satu fase dari `docs/TASKS.md` pada satu waktu. Sebelum pindah fase, jalankan pemeriksaan gate dan laporkan hasilnya.
- **Jangan mengubah asumsi fisik, rumus, atau definisi reward tanpa persetujuan.** Jika perlu diubah, usulkan dulu, lalu perbarui `docs/EXPERIMENT_DESIGN.md` dan kode bersamaan.
- Setiap fungsi yang mengimplementasikan rumus mencantumkan nomor persamaan (misalnya `# (E7)`) di docstring, dan punya tes unit.
- Tidak ada angka parameter yang ditulis langsung di kode. Semua dari `configs/*.yaml` (lihat `configs/base.yaml`). Override eksperimen ditulis sebagai file YAML kecil yang mewarisi `base.yaml`.
- **API Sionna berubah antarversi** (0.19 berbasis TensorFlow, 1.x/2.x berbasis Dr.Jit/Mitsuba). Selalu cek dokumentasi atau source versi yang terpasang, jangan mengandalkan ingatan. Catat versi di `docs/LOG.md`.
- Sionna RT terbaru **tidak** mendukung RIS. Gunakan pendekatan hibrida (§4 desain). Sionna 0.19.2 hanya dipakai di environment terpisah untuk validasi E0.
- Environment RL (`src/risisac/env`) **tidak boleh** mengimpor Sionna. Ia hanya membaca basis data kanal HDF5.
- Seed: setiap skrip menerima `--seed`; semua RNG (NumPy, PyTorch, lintasan, noise) diturunkan dari seed itu.
- Hasil eksperimen disimpan ke `results/<eksperimen>/<config_hash>/<seed>/` beserta salinan config yang dipakai dan git commit. Gambar selalu dibuat dari file hasil.
- Jangan menyimpan file kanal besar, checkpoint, atau hasil ke git (`.gitignore`).

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

Kanal disimpan sebagai `complex64`. Daya dalam Watt di kode; dBm/dB hanya di config dan plot.

## Struktur repo
```
configs/            base.yaml + override eksperimen
docs/               EXPERIMENT_DESIGN.md, TASKS.md, LOG.md
envs/               requirements-main.txt, requirements-v019.txt
scripts/            check_env, precompute_channels, validate_v019, run_sweep, print_param_table
src/risisac/
  scene/            synthetic_l, placement
  channels/         geometry, rt_extract, database, validate_compare
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
- Cek environment: `python scripts/check_env.py`
- Prakomputasi kanal: `python scripts/precompute_channels.py --config configs/base.yaml --split train`
- Latih: `python -m risisac.train.train --config configs/base.yaml --method ppo_po --seed 0`

## Pelajaran dari proyek sebelumnya (jangan diulang)
- Kode dan paper pernah tidak cocok (model kanal, ukuran RIS, reward, pembanding). Setiap selesai satu fase, cocokkan kembali dengan dokumen desain.
- Kanal statis yang dibangkitkan sekali membuat masalah menjadi bandit, bukan MDP. Di proyek ini state harus bergantung pada aksi dan waktu.
- Reward sensing harus menghukum SCNR **di bawah** ambang, bukan di atasnya.
- `env.step` harus mengembalikan 5 nilai sesuai Gymnasium.
