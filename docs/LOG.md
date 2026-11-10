# Catatan Keputusan dan Masalah

Entri terbaru di atas. Setiap entri bertanggal dan menyebut fase/gate terkait.

---

## 2026-11-10 — Fase 0 selesai, Gate 0 LOLOS

### Perangkat keras

| Komponen | Nilai |
|---|---|
| CPU | Intel Core i5-13600KF, 14 inti fisik / 20 logis |
| RAM | 31,8 GB |
| GPU | NVIDIA GeForce RTX 4070, 12 GB (11,99 GiB), compute capability 8.9 |
| Driver | 610.88, CUDA UMD 13.3 |
| OS | Windows 11 Education 10.0.26300 |
| Disk | C: 62 GB bebas, G: 59 GB bebas |

### Environment

Keduanya conda (miniforge), dibuat terpisah karena TensorFlow 2.15 memaksa
`numpy<2` dan `mitsuba<3.6`, yang bentrok langsung dengan Sionna 2.2.

**`sionna-drl` (utama), Python 3.12.16** — `envs/requirements-main.txt`

| Paket | Versi |
|---|---|
| sionna / sionna-rt | 2.2.0 |
| torch | 2.14.1+cu130 |
| drjit | 1.5.0 |
| mitsuba | 3.9.1 |
| numpy | 2.5.4 |
| scipy | 1.18.1 |
| h5py | 3.16.0 |
| PyYAML | 6.0.3 |
| gymnasium | 1.4.0 |
| stable-baselines3 / sb3-contrib | 2.9.2 |
| pandas | 3.1.1 |
| pyarrow | 26.0.1 |
| matplotlib | 3.11.2 |
| tensorboard | 2.21.0 |
| pytest | 9.2.0 |

**`sionna-v019` (validasi E0), Python 3.11.18** — `envs/requirements-v019.txt`

| Paket | Versi |
|---|---|
| sionna | 0.19.2 |
| tensorflow | 2.15.1 (`tensorflow-intel`, build CPU) |
| mitsuba | 3.5.2 |
| drjit | 0.4.6 |
| numpy | 1.26.4 |
| scipy | 1.17.1 |

Git for Windows 2.56.0.4 dipasang via winget (sebelumnya tidak ada git sama
sekali di mesin ini). Repo di-`git init` pada 2026-11-10.

### Hasil Gate 0

`python scripts/check_env.py` di kedua environment:

- `sionna-drl`: **10 PASS, 0 WARN, 0 FAIL** — exit 0
- `sionna-v019`: **8 PASS, 1 WARN, 0 FAIL** — exit 0

Satu-satunya WARN adalah TensorFlow tidak melihat GPU; ini diterima, alasannya
di bawah.

---

### Masalah yang ditemukan dan keputusannya

#### 1. `torch` dari PyPI adalah build CPU — diam-diam mematikan GPU

`pip install torch` di Windows memberi `2.15.0+cpu`, sehingga
`torch.cuda.is_available()` False dan seluruh pelatihan DRL jatuh ke CPU tanpa
error apa pun. Harus dari index cu130.

**Keputusan:** kunci `torch==2.14.1+cu130` dengan
`--extra-index-url https://download.pytorch.org/whl/cu130` di
`envs/requirements-main.txt` (2.15.0 belum punya varian cu130).
`check_env.py` menggagalkan gate bila `torch.cuda.is_available()` False.

#### 2. RIS per-elemen kehabisan VRAM dengan setelan default — BELUM diperbaiki di config

Dengan `ris_per_element: true` (desain §4.2), jumlah sumber ray tracing sama
dengan M. `PathSolver` memakai default `max_num_paths_per_src=1e6`, sehingga
M=144 mencoba mengalokasikan 1 GiB untuk `specular_chain_counters` dan gagal:

```
RuntimeError: jit_malloc(): out of memory! Could not allocate 1073741824 bytes
  sb_candidate_generator.py:529  specular_chain_counters
```

Gagal bahkan dengan 8 receiver dan `samples_per_src=1e5`. Penyebabnya **bukan**
`samples_per_src` — itu knob yang salah, dan justru knob itulah yang ada di
`configs/base.yaml`, sementara `max_num_paths_per_src` tidak ada sama sekali.

Nilai kerja terukur di GPU ini: `max_num_paths_per_src=1e5` untuk M ≤ 144,
`5e4` untuk M=256.

**USULAN, menunggu persetujuan** (mengubah `configs/base.yaml` berarti mengubah
parameter eksperimen, jadi tidak dikerjakan sepihak):

```yaml
ray_tracing:
  max_num_paths_per_src: 1.0e5   # kunci baru; 5.0e4 untuk M=256
  rx_batch_size: 256             # dari 512; <=128 untuk M=256
```

#### 3. Menurunkan `max_num_paths_per_src` memotong jalur — risiko bias diam

Jumlah jalur yang tersimpan ikut turun: 146 jalur pada M=144 dengan `mnp=1e5`,
tetapi hanya 69 pada M=256 dengan `mnp=5e4`. Ini membiaskan koefisien kanal, dan
**tidak satu pun tes Gate 2** (bentuk, dtype, NaN/Inf, resiprositas,
determinisme) akan menangkapnya.

**Usulan untuk Fase 2:** tambahkan tes konvergensi — naikkan
`max_num_paths_per_src` sampai daya terima total berubah < 0,1 dB, lalu kunci
nilainya dan catat di sini.

#### 4. Sionna 0.19.2 tidak bisa di-import sama sekali tanpa LLVM

`sionna/rt/__init__.py` memilih varian Mitsuba dari
`tf.config.list_physical_devices('GPU')`. TensorFlow tidak punya dukungan GPU
native di Windows sejak 2.11, jadi daftar itu **selalu** kosong dan Sionna
**selalu** memilih `llvm_ad_rgb`. Di mesin ini tidak ada `LLVM-C.dll`, sehingga:

```
ImportError: jit_init_thread_state(): the LLVM backend is inactive because
the LLVM shared library ("LLVM-C.dll") could not be found!
```

**Keputusan:** `conda install -n sionna-v019 -c conda-forge llvmdev`
(122 MB, di dalam env saja, tidak menyentuh sistem) dan
`conda env config vars set -n sionna-v019 DRJIT_LIBLLVM_PATH=<prefix>/Library/bin/LLVM-C.dll`.

Catatan jebakan: `conda env config vars` **hanya** berlaku lewat
`conda activate`. Memanggil `python.exe` langsung lewat path akan melewatkannya.
Karena itu `check_env.py` mencari sendiri `LLVM-C.dll` di `sys.prefix` dan
menyetel variabelnya sebelum impor apa pun.

#### 5. E0 berjalan di CPU — diterima, bukan hambatan

Diukur di `sionna-v019` (Munich, RIS 12×12, `coverage_map(..., ris=True)`):

| Beban | Waktu |
|---|---|
| grid 2,0 m, 1e6 sampel (300 sel) | 7,5 s |
| grid 1,0 m, 1e6 sampel (1.200 sel) | 8,1 s |
| grid 0,5 m, 2e6 sampel (4.800 sel) | 8,3 s |
| `compute_paths` 64 rx | 2,4 s (37,7 ms/rx) |

Biaya didominasi `num_samples`, hampir tidak oleh resolusi grid: menaikkan grid
16× hanya menambah 0,8 detik. Seluruh E0 (4 profil fasa × 2 scene × mode
per-elemen vs synthetic) berada di orde menit.

**Keputusan:** tidak memasang WSL2. Risiko "API Sionna / dua environment" di
desain §10 tetap ditangani dengan penguncian versi di `envs/`.

Caveat: angka di atas diukur dengan `scattering=False`. Desain §4.2 meminta
hamburan difus aktif; ukur ulang saat Fase 3.

#### 6. Biaya prakomputasi Fase 2 jauh di bawah dugaan desain §10

Diukur di `sionna-drl` pada Munich sebagai proksi, RIS per-elemen, `max_depth=3`,
spekular + difus + difraksi, `samples_per_src=1e6`:

| M | ms per receiver | Estimasi 82.500 titik |
|---|---|---|
| 64 | 15,9 | ~22 menit |
| 144 | 38,5 | ~53 menit |
| 256 | 60,8 | ~84 menit |

Beban Fase 2 = 550 lintasan × 50 langkah × (K=2 + Q=1) = 82.500 titik receiver
sisi RIS. Sapuan M lengkap untuk E4 ≈ **2,6 jam per scene**; sisi BS (N_t=8)
dapat diabaikan. Basis data HDF5 untuk ketiga nilai M ≈ 0,4 GB.

Risiko "prakomputasi berhari-hari" di §10 **tidak terbukti** di perangkat ini.

VRAM tetap ketat: M=256 dengan 256 receiver memuncak di 11,9 GB dari 12,3 GB
sementara desktop memakai ~1,7 GB. Tutup aplikasi berat saat prakomputasi.

#### 7. Premis desain §4.1 terkonfirmasi

Tidak ada kelas RIS di Sionna 2.2 (dicari di source, nihil), jadi pendekatan
hibrida memang diperlukan. Scene bawaan yang tersedia di 2.2: `munich`,
`etoile`, `florence`, `san_francisco`, `simple_street_canyon` — §2.2 terpenuhi.

API RIS 0.19.2 yang dibutuhkan E0 lengkap: `RIS(name, position, num_rows,
num_cols, num_modes, look_at)` dengan `focusing_lens()`,
`phase_gradient_reflector()`, `phase_profile`, `cell_world_positions`, serta
`compute_paths(..., ris=True)` dan `coverage_map(..., ris=True)`. RIS 12×12
terbentuk benar: 144 sel, 0,514 × 0,514 m (= 12 × λ/2 pada 3,5 GHz).

#### 8. Catatan API yang mudah menjebak

- `sionna.phy.config.device` menolak `"cuda"`; harus `"cuda:0"`, kalau tidak
  `ValueError: Invalid device`.
- `drjit.has_backend()` hanya ada di drjit 1.x. Memanggilnya di 0.4.6 melempar
  `resource deadlock would occur`.
- Deteksi versi paket di `check_env.py` memakai metadata distribusi, bukan
  impor. Kalau impor dipakai, kegagalan impor (butir 4) membuat deteksi versi
  ikut gagal dan skrip salah memilih cabang API.
- SB3 memperingatkan PPO dengan `MlpPolicy` lebih lambat di GPU daripada CPU.
  Untuk M1/M3 yang jaringannya kecil, `device="cpu"` kemungkinan lebih cepat.
  **Ukur di Fase 6, jangan diasumsikan.**

---

### Catatan untuk fase berikutnya

- Estimasi beban pelatihan (~70 run × 2e6 langkah untuk M1–M6 plus latih ulang
  E4) adalah **perkiraan, belum diukur** — kode environment belum ada.
  Benchmark sesungguhnya ada di Gate 5.
- Bottleneck evaluasi yang sebenarnya diperkirakan Oracle-GD (B3/B4): 300 iterasi
  × 4 restart = 1.200 langkah Adam per keputusan, × 200 episode × 50 langkah =
  1,2e7 iterasi gradien per varian. Harus dibatch lintas episode di GPU.
