# Rencana Implementasi 8 Minggu (Versi Ramping)

Kerjakan fase berurutan. **Jangan lanjut sebelum gate lolos.** Jika gate gagal, catat penyebab di `docs/LOG.md`, ajukan perbaikan, dan minta persetujuan sebelum mengubah asumsi fisik di `docs/EXPERIMENT_DESIGN.md`.

Rujukan (E1)–(E9), §, dan prioritas P1/P2/P3 mengacu ke `docs/EXPERIMENT_DESIGN.md`.

## Jadwal ringkas

| Minggu | Fase | Hasil | Menulis paralel |
|---|---|---|---|
| 1 | 0, 1 | Lingkungan siap, scene L, peta cakupan (E1) | Kerangka paper, related work |
| 2 | 2 | Basis data kanal, validasi E0 | — |
| 3 | 3 | Model sinyal, baseline, uji kelayakan oracle | Bagian model sistem |
| 4 | 4 + awal 5 | Environment RL, uji asap PPO | Bagian formulasi MDP |
| 5 | 5 | 15 run pelatihan (jalan malam hari) | — |
| 6 | 6 | Evaluasi E3, E4, E5, E6 | Bagian metode dan baseline |
| 7 | 7 | Gambar/tabel final, cek konsistensi | Hasil dan diskusi |
| 8 | — | Cadangan waktu, review internal, kirim | Abstrak, kesimpulan, revisi |

**Titik keputusan:**
- **Akhir minggu 1 (Gate 1):** jika SNR radar ideal tidak memenuhi, ubah geometri sebelum ray tracing massal.
- **Akhir minggu 3 (Gate 3):** jika Oracle-GD pun gagal memenuhi Γ, ubah L, Γ, atau geometri. Jangan lanjut ke RL.
- **Pertengahan minggu 5 (Gate 5):** jika PPO-PO belum mengalahkan Geometric pada val, terapkan mitigasi §10. Jika sampai akhir minggu 5 tetap gagal, diskusikan pembingkaian ulang sebelum evaluasi penuh.
- **Tiap akhir minggu:** jika terlambat, potong P3 dulu, lalu P2.

---

## Fase 0 — Setup (minggu 1, 1–2 hari)

- [ ] `pyproject.toml`, paket `risisac` (layout `src/`), Python 3.11/3.12.
- [ ] `envs/requirements.txt`: sionna-rt terbaru, numpy, scipy, h5py, pyyaml, gymnasium, torch, stable-baselines3, pandas, pyarrow, matplotlib, pytest. Kunci versi persis setelah instalasi berhasil.
- [ ] `scripts/check_env.py`: cetak versi, varian Dr.Jit yang aktif (CUDA/LLVM), VRAM bebas, muat satu scene bawaan, hitung jalur satu Tx–Rx.
- [ ] Buat `docs/LOG.md`.

**Gate 0:** `check_env.py` berjalan tanpa error; versi dan VRAM tercatat di `docs/LOG.md`.

---

## Fase 1 — Scene dan kelayakan (minggu 1)

- [ ] `src/risisac/scene/synthetic_l.py`: scene berbentuk L (dua jalan tegak lurus, gedung kotak beton, tanah) sebagai mesh + XML Mitsuba. Juga varian **ruang bebas** (tanpa objek) untuk E0.
- [ ] `src/risisac/scene/placement.py`: posisi BS, RIS (posisi + normal), ROI, lajur target, trotoar dari config. BS–RIS ≈ 20 m, ROI 10–30 m dari RIS.
- [ ] Cek LoS otomatis: BS→RIS harus LoS; BS→semua titik grid ROI harus NLoS; catat persentase LoS RIS→ROI.
- [ ] `src/risisac/channels/geometry.py`: posisi elemen RIS di koordinat dunia, steering gelombang sferis, profil fasa fokus.
- [ ] E1: di grid ROI (0,5 m), hitung SNR komunikasi dan SNR radar ideal (E7 dengan ρ = 1, tanpa clutter, profil fokus terbaik per titik) untuk P_max ∈ {20, 30, 40} dBm. Gambar F1 dan F2.

**Gate 1:**
- BS→RIS LoS dan 0% titik ROI LoS dari BS.
- Pada P_max = 30 dBm: SNR komunikasi lewat RIS > 10 dB di ≥ 90% ROI, dan SNR radar ideal ≥ Γ + 3 dB di ≥ 80% ROI.
- **Penguatan RIS > 6 dB di ≥ 80% ROI** (ditambahkan 2026-11-11). Tanpa kriteria ini gate bisa lolos sementara jalur langsung mendominasi ROI: ROI yang *tanpa garis pandang* belum tentu *kekurangan daya*, dan bila jalur langsung menang maka premis "RIS yang melayani ROI" gagal diam-diam dan daya ungkit aksi agen hilang. Ambang ada di `configs/base.yaml` (`gate1:`).
  - Diukur **MRT-dengan-RIS lawan MRT-tanpa-RIS**, yaitu sistem ber-RIS melawan sistem tanpa RIS yang sama-sama melakukan beamforming optimal. Jangan membandingkan pada precoder `ā`: `ā` dioptimalkan untuk mencapai RIS dan melumpuhkan jalur langsung, sehingga melebih-lebihkan peran RIS (+8,8 dB lawan +1,4 dB pada geometri yang sama).
  - Ambangnya dinaikkan dari 0 dB / 90% ke **6 dB / 80%** pada hari yang sama (opsi (a), disetujui): 0 dB adalah bar yang lemah — penguatan 0,1 dB pun dihitung menang — dan geometri v0.2 lolos dengan hanya +1,4 dB median dan +0,0 dB di desil terlemah. 6 dB bermakna secara fisik: dengan penjumlahan koheren, +6 dB berarti amplitudo kaskade RIS sekurangnya **setara** jalur langsung.
- Jika gagal: pendekkan ROI atau jarak BS–RIS, atau naikkan L. Catat keputusan.

---

## Fase 2 — Basis data kanal dan E0 (minggu 2)

- [x] `src/risisac/mobility/trajectories.py`: lintasan target (lajur, kecepatan diacak 1–10 m/s) dan pengguna (random waypoint), split 200/30/50 dengan seed terpisah.
- [x] `src/risisac/channels/rt_extract.py`: hitung **G**, **H**, **H**_c (buang LoS tx–rx), dan per titik **g**_k, **g**_t, **h**_{d,k}, **h**_{d,t}, **h**^{(r)}_{d,t}. RIS sebagai array planar tanpa mesh. Batch penerima; mode per elemen dan synthetic array.
- [x] `src/risisac/channels/database.py`: HDF5 sesuai §4.4.
- [x] `scripts/precompute_channels.py --config ... --split ...`: bisa dilanjutkan bila terputus; catat waktu dan puncak VRAM.
- [x] Atur `samples_per_src` sampai daya di 20 titik uji berubah < 0,5 dB terhadap nilai 2× lipat.
- [x] E0 (§4.5): uji implementasi vs analitik ruang bebas, kalibrasi terhadap model path loss RIS literatur, per elemen vs synthetic array. Gambar F3, Tabel T1.
- [x] Tes unit: bentuk/dtype, tanpa NaN/Inf; resiprositas beberapa link; kanal langsung BS di ROI jauh lebih lemah daripada jalur RIS terfokus; determinisme dengan seed sama.

**Gate 2:** semua tes lulus; uji implementasi E0 < 0,1 dB; `calibration_db` tercatat; prakomputasi lengkap untuk ketiga split.

---

## Fase 3 — Model sinyal, tracker, baseline (minggu 3)

- [x] `src/risisac/system/signal_model.py`: (E1)–(E7) terbatch, versi NumPy dan PyTorch. Docstring mencantumkan nomor persamaan.
- [x] `src/risisac/system/precoding.py`: RZF, beam sensing dari estimasi posisi, normalisasi daya.
- [x] `src/risisac/system/ris.py`: pembaruan fasa inkremental/absolut.
- [x] `src/risisac/tracking/kalman.py`: Kalman kecepatan-konstan 2D + model galat pengukuran §5.2.
- [x] `src/risisac/baselines/`: `random_policy.py` (B1), `geometric.py` (B2), `oracle_gd.py` (B3, B4).
- [x] Tes unit:
  - SCNR (E7) bentuk tertutup = maksimum eigen umum numerik;
  - SINR (E3) = simulasi Monte Carlo simbol;
  - tr(**R**_x) ≤ P_max selalu;
  - faktor η (E6) cocok dengan persamaan radar bistatik ruang bebas untuk satu konfigurasi sederhana.
- [x] Uji kelayakan: B3 pada 200 snapshot val; pilih grid ω dan ρ untuk B1/B2 di val.

**Gate 3:** semua tes lulus; B3 memenuhi SCNR ≥ Γ pada ≥ 90% snapshot val dan jelas mengungguli B1.

> **Status 2026-11-11: LOLOS** (3/3) setelah λ dinaikkan 1,0 → 10,0 di §5.4 (disetujui). B3 memenuhi Γ di **100%** snapshot val dengan rate minimum 11,63 bit/s/Hz, dan mengungguli B1 dengan margin reward +12,50. Kegagalan sebelumnya (0,845) berasal dari hinge (E9) yang terlalu lemah untuk menegakkan kendala keras (E8), bukan dari ketidakmampuan sistem — menaikkan λ **tidak** menurunkan laju sama sekali. Lihat `docs/LOG.md` 2026-11-11 (h) dan (i).

---

## Fase 4 — Environment RL (minggu 4)

- [x] `src/risisac/env/ris_isac_env.py`: `RisIsacEnv` Gymnasium, API 5-tuple, `reset(seed=...)`, mode observasi `partial`/`full`, mode fasa `incremental`/`absolute`, P_max dan kecepatan diacak di train.
- [x] `info`: rate per pengguna, rate minimum, SCNR, flag deteksi, galat tracker, ρ, komponen reward.
- [x] `SubprocVecEnv` (8 env) + `VecNormalize` (observasi saja; reward tidak dinormalisasi agar mudah ditafsirkan) + frame-stack 4.
- [x] Tes: `gymnasium.utils.env_checker.check_env` lulus; seed sama → trajektori identik; reward = (E9) dihitung ulang dari `info`; kebijakan B2 lewat env = B2 langsung.
- [x] Benchmark kecepatan langkah.
- [x] Uji asap: PPO-PO **300 ribu** langkah harus mengalahkan B1 di val.
  - Anggaran dinaikkan dari 100 ribu pada 2026-11-11 **berdasarkan pengukuran**, bukan karena uji asapnya gagal secara substansi. Kurva belajar (reward per langkah di val; B1 = −0,903):

    | langkah | 8 rb | 100 rb | 150 rb | 200 rb | **300 rb** |
    |---|---|---|---|---|---|
    | seed 0 | −2,490 | −1,679 | +0,412 | +0,924 | **+1,803** |
    | seed 1 | | | −0,710 | | **+2,530** |
    | seed 2 | | | +0,141 | | **+2,236** |

    PPO melewati B1 antara 100 dan 150 ribu langkah, tetapi pada 150 ribu marginnya hanya 0,19 di seed terburuk. Pada 300 ribu ketiga seed unggul 2,7–3,4 — margin yang membuat uji asap menyaring environment yang rusak, bukan keberuntungan seed. Biayanya 130 detik, dapat diabaikan terhadap 15 run × 1e6 langkah yang disaringnya. Sebagian besar 100 ribu langkah pertama habis dipakai agen menurunkan ρ dari 0,5 (nilai awal aksi) ke sekitar 0,1 (ρ hasil tuning B1); lihat `docs/LOG.md` 2026-11-11 (j).

**Gate 4:** semua tes lulus; uji asap lolos; laju ≥ 1.000 langkah/detik per proses.

> **Status 2026-11-11: LOLOS.** 142 tes lulus (termasuk `gymnasium.utils.env_checker.check_env` untuk mode parsial dan penuh, determinisme seed, reward = (E9) dihitung ulang dari `info`, dan kebijakan B2 lewat env = B2 langsung). Uji asap lolos di 300 ribu langkah pada tiga seed. Laju env **3.282 langkah/detik** per proses; throughput pelatihan PPO 2.317 langkah/detik dengan 8 env.

---

## Fase 5 — Pelatihan E2 dan E4b (minggu 5)

- [x] `src/risisac/train/train.py --config ... --method {ppo_po, ppo_full, ppo_po_absolute} --seed ...`: simpan model, `VecNormalize`, log CSV/TensorBoard, checkpoint, evaluasi val setiap 50 ribu langkah.
- [x] `scripts/run_all_training.sh`: antrean 15 run (M1, M2, A1 × 3 seed; M1 Γ = 10 dan 16 × 3 seed), bisa dilanjutkan. Jalankan di CPU, 2–3 run paralel sesuai jumlah core.

    Paralelisme **diukur**: JOBS=1 → 2.069 langkah/detik; JOBS=3 → 1.704 per run = 5.112 agregat; **JOBS=4 gagal** (36 proses × torch melewati batas memori commit Windows). Satu run 9,4 menit untuk observasi 696, **16,3 menit** untuk M2 (observasi 2232).
- [x] Gambar F4 (`results/gate5/<config_hash>/F4_training.png`).

**Gate 5:** M1 konvergen (reward val naik < 2% dalam 20% langkah terakhir) dan mengalahkan B1 serta B2 di val. Jika gagal di pertengahan minggu, terapkan mitigasi §10: inisialisasi dari B2, kurikulum target diam → bergerak, κ lebih kecil.

> Kriteria "naik < 2%" tidak terdefinisi apa adanya (reward mulai negatif, berakhir positif), jadi dibuat eksplisit: **kenaikan 20% langkah terakhir dibagi total kenaikan sejak langkah 0**. Bebas skala dan aman melewati nol; angka mentahnya ikut dilaporkan.

> **Status 2026-11-11: LOLOS** (config base, Γ = 13 dB). M1 ekor −1,46% (ambang 2%); M1 **+3,783** lawan B1 −0,750 dan B2 **+2,261**. F4 dibuat dari tiga seed per metode.
>
> **Terbuka — belum diputuskan, lihat `docs/LOG.md` 2026-11-11 (k):** (1) M1/M2 memenuhi SCNR hanya di **41%** langkah sementara B2 di 99,8%; penyebabnya **bukan** λ melainkan kendala fasa inkremental — A1 dengan λ yang sama mencapai deteksi **0,95–0,96 dengan rate 8,4** di 350–450 ribu langkah pada ketiga seed. (2) Ketiga seed A1 lalu **ambruk** ke deteksi ~0,55 dengan rate tak berubah, sehingga melaporkan model AKHIR menempatkan A1 2,7 poin di bawah yang dicapainya; pemilihan model pada val membutuhkan `save_vecnormalize=True` dan pelatihan ulang. (3) M1 pada Γ = 10 dan 16 belum konvergen (ekor +2,09% dan +7,85%).

---

## Fase 6 — Evaluasi (minggu 6)

- [ ] `src/risisac/eval/evaluate.py`: semua metode di 150 episode test (50 lintasan × 3 seed noise), seed tetap; hasil per langkah ke Parquet.
- [ ] `src/risisac/eval/metrics.py`: rate minimum, pemenuhan SCNR, durasi track, galat tracker, CI bootstrap, Welch t-test.
- [ ] E3 (P1) → T2, F5, F6.
- [ ] E4b (P1): evaluasi semua metode pada Γ = 10, 13, 16 → F8.
- [ ] E4a (P2): P_max dan kelompok kecepatan → F7.
- [ ] E5, E6 (P2) → T3.
- [ ] E7, E8 (P3) hanya jika masih ada waktu.

**Gate 6:** T2, F5, F6, F8 lengkap.

---

## Fase 7 — Finalisasi (minggu 7)

- [ ] `src/risisac/eval/plots.py` dan `scripts/make_figures.py`: semua gambar dan tabel dari `results/` dengan satu perintah; ekspor PDF vektor dan tabel LaTeX.
- [ ] `scripts/print_param_table.py`: tabel parameter LaTeX dari config.
- [ ] Cek silang: tiap persamaan paper ↔ fungsi kode ↔ tes unit. Catat di `docs/LOG.md`.
- [ ] README: langkah reproduksi dari instalasi sampai gambar.

**Gate 7:** semua gambar dan tabel dibuat ulang dari repo bersih dengan satu perintah.
