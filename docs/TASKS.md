# Rencana Implementasi Bertahap

Kerjakan fase secara berurutan. **Jangan lanjut ke fase berikutnya sebelum gate fase saat ini lolos.** Jika gate gagal, catat penyebab di `docs/LOG.md`, ajukan perbaikan, dan minta persetujuan sebelum mengubah asumsi fisik di `docs/EXPERIMENT_DESIGN.md`.

Rujukan persamaan (E1–E9) dan bagian (§) mengacu ke `docs/EXPERIMENT_DESIGN.md`.

---

## Fase 0 — Setup lingkungan

- [ ] Buat `pyproject.toml` dengan paket `risisac` (layout `src/`), Python 3.11 atau 3.12.
- [ ] Environment utama (`envs/requirements-main.txt`): sionna-rt versi terbaru, numpy, scipy, h5py, pyyaml, gymnasium, torch, stable-baselines3, sb3-contrib, matplotlib, pandas, pytest. Kunci versi persis setelah instalasi berhasil.
- [ ] Environment validasi terpisah (`envs/requirements-v019.txt`): sionna==0.19.2 dan versi TensorFlow yang didukungnya (cek dokumentasi Sionna 0.19.2). Hanya untuk E0.
- [ ] Skrip `scripts/check_env.py`: cetak versi paket, deteksi GPU (Dr.Jit backend CUDA/LLVM dan PyTorch CUDA), muat satu scene bawaan, hitung jalur satu Tx–Rx.
- [ ] Buat `docs/LOG.md` untuk catatan keputusan dan masalah.

**Gate 0:** `check_env.py` berjalan di kedua environment tanpa error; versi tercatat di `docs/LOG.md`.

---

## Fase 1 — Scene, penempatan, dan kelayakan link (E1)

- [ ] `src/risisac/scene/synthetic_l.py`: bangun scene berbentuk L (dua jalan tegak lurus, gedung kotak beton) sebagai mesh + XML Mitsuba yang bisa dimuat Sionna RT.
- [ ] `src/risisac/scene/placement.py`: definisikan posisi BS, RIS (posisi, orientasi normal), ROI, lajur target, dan trotoar dari config.
- [ ] Fungsi cek visibilitas LoS (jalur kedalaman 0) untuk: BS→RIS (harus LoS), BS→setiap titik ROI (harus NLoS), RIS→titik ROI (catat persentase LoS).
- [ ] `src/risisac/channels/geometry.py`: posisi elemen RIS dalam koordinat dunia, vektor steering gelombang sferis ke titik sembarang, profil fasa fokus.
- [ ] Hitung peta daya di grid ROI (jarak 0,5 m): (a) BS langsung, (b) lewat RIS dengan profil fokus ke tiap titik grid (gain koheren terbaik per titik), untuk M ∈ {64, 144, 256} dan P_max ∈ {20, 30, 40} dBm.
- [ ] Gambar F1 (tata letak) dan F2 (peta cakupan).

**Gate 1:**
- BS→RIS LoS; tidak ada LoS BS→ROI di 100% titik grid ROI.
- Dengan M = 144 dan P_max = 30 dBm, SNR lewat RIS > 0 dB di ≥ 80% titik ROI.
- Jika gagal: geser RIS, ubah orientasi, atau naikkan M default. Catat keputusan.

---

## Fase 2 — Ekstraksi kanal dan basis data (§4)

- [ ] `src/risisac/mobility/trajectories.py`: pembangkit lintasan target (lajur, kecepatan 1–10 m/s) dan pengguna (random waypoint di trotoar), dengan split train/val/test dari seed terpisah.
- [ ] `src/risisac/channels/rt_extract.py`: hitung **G**, **H**, **H**_c (tanpa jalur LoS tx–rx), dan per titik lintasan **g**_k, **g**_t, **h**_{d,k}, **h**_{d,t}, **h**^{(r)}_{d,t}. RIS sebagai array planar M elemen tanpa mesh. Mendukung batch penerima dan mode per-elemen vs synthetic array.
- [ ] `src/risisac/channels/database.py`: tulis/baca HDF5 sesuai skema §4.3, termasuk metadata dan hash config.
- [ ] `scripts/precompute_channels.py --config ... --split ...` yang bisa dilanjutkan bila terputus.
- [ ] Tes unit:
  - bentuk dan dtype semua array, tanpa NaN/Inf;
  - resiprositas: menukar peran tx/rx untuk beberapa link memberi koefisien yang sama (toleransi kecil relatif);
  - **h**_{d,t} di ROI jauh lebih lemah daripada jalur lewat RIS dengan profil fokus;
  - determinisme: dua kali prakomputasi dengan seed sama menghasilkan file identik (atau selisih di bawah toleransi numerik).

**Gate 2:** semua tes lulus; waktu prakomputasi per titik lintasan tercatat; ukuran basis data wajar.

---

## Fase 3 — Validasi terhadap Sionna 0.19.2 (E0)

- [ ] `scripts/validate_v019.py` (dijalankan di env validasi): bangun scene yang sama, pasang RIS 0.19.2 dengan profil fasa yang diekspor dari env utama, hitung daya terima di grid ROI.
- [ ] `src/risisac/channels/validate_compare.py` (env utama): bandingkan dengan hasil hibrida untuk 4 profil fasa; hitung faktor kalibrasi konstan.
- [ ] Bandingkan juga mode per-elemen vs synthetic array.
- [ ] Gambar F3, Tabel T1.

**Gate 3:** selisih median ≤ 2 dB dan P90 ≤ 4 dB di area yang diterangi RIS (setelah kalibrasi konstan). Jika gagal, telusuri pola elemen, orientasi, dan konvensi fasa sebelum lanjut. Ambang ini adalah usulan awal; jika diubah, catat alasannya.

---

## Fase 4 — Model sinyal dan baseline

- [ ] `src/risisac/system/signal_model.py`: (E1)–(E7) secara terbatch (NumPy dan versi PyTorch untuk oracle). Setiap fungsi mencantumkan nomor persamaan di docstring.
- [ ] `src/risisac/system/precoding.py`: RZF, beam sensing dari estimasi posisi, normalisasi daya.
- [ ] `src/risisac/system/ris.py`: pembaruan fasa inkremental/absolut, kuantisasi b-bit.
- [ ] `src/risisac/tracking/kalman.py`: filter Kalman kecepatan-konstan 2D dan model galat pengukuran (§5.2).
- [ ] `src/risisac/baselines/`: `random_policy.py` (B1), `geometric.py` (B2), `oracle_gd.py` (B3, B4, B5).
- [ ] Tes unit:
  - SCNR (E7) dengan MVDR bentuk tertutup sama dengan maksimum numerik u^H A u / u^H R u (eigen umum) untuk kanal acak;
  - SINR (E3) sama dengan perhitungan langsung dari simulasi Monte Carlo simbol;
  - tr(**R**_x) ≤ P_max selalu terpenuhi;
  - |e^{jφ}| = 1 dan kuantisasi menghasilkan tepat 2^b level.
- [ ] **Uji kelayakan:** jalankan B3 pada 200 snapshot val; catat persentase snapshot yang memenuhi SCNR ≥ Γ.

**Gate 4:** semua tes lulus; B3 memenuhi SCNR ≥ Γ pada ≥ 90% snapshot val dengan parameter default, dan B3 jelas lebih baik daripada B1. Jika tidak, sesuaikan Γ, L, atau σ_rcs (catat alasannya) sebelum lanjut.

---

## Fase 5 — Environment RL (§5)

- [ ] `src/risisac/env/ris_isac_env.py`: kelas Gymnasium `RisIsacEnv` dengan API 5-tuple (`obs, reward, terminated, truncated, info`), `reset(seed=...)`, mode observasi `partial` / `full`, mode aksi `model_informed` / `direct_w`, mode reward `hinge` / `indicator` / `lagrangian`.
- [ ] `info` memuat: rate per pengguna, rate minimum, SCNR per target, flag deteksi, galat posisi tracker, ρ, komponen reward.
- [ ] Pembungkus vektor (SubprocVecEnv) dan normalisasi observasi.
- [ ] Tes:
  - `gymnasium.utils.env_checker.check_env` lulus;
  - seed sama → trajektori identik;
  - reward sama dengan perhitungan ulang dari `info` dan (E9);
  - kebijakan B2 yang dijalankan lewat env memberi hasil sama dengan B2 langsung.
- [ ] Benchmark kecepatan langkah.

**Gate 5:** semua tes lulus; ≥ 2.000 langkah/detik per proses untuk konfigurasi default (target awal, sesuaikan bila perangkat keras berbeda).

---

## Fase 6 — Pelatihan (E2)

- [ ] `src/risisac/train/train.py --config ... --method ... --seed ...`: membaca config, menyimpan model, log TensorBoard/CSV, checkpoint, dan evaluasi berkala di set val.
- [ ] Uji asap: PPO-PO 100 ribu langkah pada scene sintetis harus mengalahkan B1.
- [ ] Latih M1–M4 dengan 5 seed; kemudian M5, M6.
- [ ] Gambar F4.

**Gate 6:** M1 konvergen (reward val tidak naik > 2% dalam 20% langkah terakhir) dan mengalahkan B1 serta B2 pada set val. Jika tidak mengalahkan B2, lakukan diagnosis (normalisasi, κ, inisialisasi, kurikulum) sebelum menjalankan sapuan.

---

## Fase 7 — Evaluasi dan sapuan (E3–E7)

- [ ] `src/risisac/eval/evaluate.py`: jalankan semua metode di set test dengan seed tetap; simpan hasil per langkah ke Parquet.
- [ ] `src/risisac/eval/metrics.py`: rate minimum, pemenuhan SCNR, durasi track, galat tracker, CI bootstrap, Welch t-test.
- [ ] `src/risisac/eval/plots.py`: F5–F9 dari file hasil.
- [ ] `scripts/run_sweep.py` untuk E4 dan E5; ablasi E6; pengukuran waktu E7.
- [ ] Tabel T2–T4 sebagai CSV dan LaTeX.

**Gate 7:** semua gambar dan tabel bisa dibuat ulang dari `results/` dengan satu perintah.

---

## Fase 8 — Reproduksibilitas dan konsistensi paper–kode

- [ ] `scripts/print_param_table.py`: cetak tabel parameter dari config dalam format LaTeX untuk paper.
- [ ] Cek silang: setiap persamaan di paper ↔ fungsi di kode ↔ tes unit.
- [ ] README berisi langkah reproduksi lengkap dari instalasi sampai gambar.
- [ ] Opsional: scene utama kedua atau scene OSM untuk uji generalisasi.

**Gate 8:** orang lain bisa mereproduksi T2 dari repo bersih mengikuti README.
