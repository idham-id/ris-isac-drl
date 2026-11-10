# Rancangan Eksperimen: DRL untuk RIS-Assisted ISAC pada Skenario NLoS Site-Specific

**Judul kerja:** *Deep Reinforcement Learning for RIS-Assisted Integrated Sensing and Communication in Site-Specific NLoS Scenarios with Partial Observations and Moving Targets*

**Versi:** 0.1 (rancangan awal, 10 November 2026)
**Status:** siap diimplementasikan bertahap mengikuti `docs/TASKS.md`

Dokumen ini adalah **sumber kebenaran tunggal** untuk model sistem, formulasi MDP, baseline, dan eksperimen. Setiap rumus di kode harus bisa ditelusuri ke nomor persamaan di sini, dan setiap perubahan rumus di kode harus diikuti pembaruan dokumen ini.

---

## 0. Ringkasan

Sebuah BS ISAC monostatik melayani K pengguna downlink dan memantau Q target bergerak yang berada di area **NLoS** (terhalang gedung dari BS). Satu RIS di dinding gedung pada persimpangan jalan menciptakan jalur virtual-LoS ke area tersebut. Agen DRL mengatur fasa RIS dan pembagian daya komunikasi–sensing setiap frame, **tanpa CSI kaskade per-elemen** (observasi parsial). Precoder BS dihitung secara analitik dari kanal efektif yang murah diestimasi.

Kanal dihasilkan dengan **Sionna RT** (ray tracing site-specific) melalui **pendekatan hibrida**: kanal penyusun (BS→RIS, RIS→pengguna, RIS→target, clutter) dihitung sekali dengan ray tracing dan disimpan, lalu fasa RIS diterapkan di Python. Pendekatan ini divalidasi terhadap model RIS bawaan Sionna 0.19.2.

Kontribusi yang ditargetkan:
1. Lingkungan RL untuk RIS-ISAC dengan kanal site-specific, clutter dari ray tracing, dan target bergerak di area NLoS.
2. Formulasi MDP dengan observasi parsial yang realistis (kanal efektif + estimasi posisi dari tracker), sehingga keputusan saat ini memengaruhi kualitas observasi berikutnya.
3. Perbandingan sistematis DRL terhadap baseline geometris dan oracle berbasis optimasi dengan CSI sempurna, termasuk latensi komputasi.
4. Validasi kuantitatif pendekatan kanal hibrida terhadap model RIS Sionna 0.19.2.

---

## 1. Pertanyaan Riset dan Hipotesis

| ID | Pertanyaan | Hipotesis | Eksperimen |
|---|---|---|---|
| RQ1 | Seberapa dekat agen DRL dengan observasi parsial terhadap oracle ber-CSI-sempurna dalam rate minimum dan kepatuhan sensing? | Agen PO mencapai ≥ 80% rate minimum oracle dengan tingkat pemenuhan SCNR yang sebanding, dengan waktu inferensi jauh lebih kecil | E3, E7 |
| RQ2 | Apakah agen mampu mempertahankan deteksi target bergerak lebih baik daripada re-optimasi berkala dan steering geometris? | Agen dengan memori (frame-stack/LSTM) mempertahankan track lebih lama, terutama pada kecepatan target tinggi | E3, E4, E5 |
| RQ3 | Bagaimana trade-off komunikasi–sensing berubah terhadap ukuran RIS, daya, ambang SCNR, dan clutter? | Kurva Pareto bergeser keluar dengan M; clutter memperburuk sensing terutama dekat dinding | E4 |
| RQ4 | Seberapa akurat kanal hibrida dibanding model RIS Sionna 0.19.2? | Selisih median daya terima ≤ 2 dB di area yang diterangi RIS | E0 |

Angka pada kolom hipotesis adalah target awal, bukan klaim. Revisi setelah E1–E2 jika tidak realistis.

---

## 2. Skenario dan Geometri

### 2.1 Tata letak

```
                 Jalan B (area NLoS dari BS)
        ┌──────────────────────────────────────────┐
        │  target bergerak  ──►      pengguna k     │
        │                                           │
 ───────┘   ▲ RIS di dinding sudut, menghadap jalan B
            │
   Gedung   │          Jalan A
   (blokade)│   BS ●  (LoS ke RIS, tidak LoS ke jalan B)
            │
```

- **BS**: di jalan A, ketinggian ~10 m, array pancar dan terima terpisah vertikal 0,5 m (ISAC monostatik dengan panel tx/rx terpisah).
- **RIS**: di dinding gedung pada sudut persimpangan, ketinggian ~6 m, menghadap jalan B. LoS ke BS dan ke sebagian besar jalan B.
- **Area NLoS (region of interest, ROI)**: segmen jalan B sepanjang 10–60 m dari sudut. Tidak ada LoS dari BS ke titik mana pun di ROI (diperiksa otomatis).
- **Pengguna**: K = 2 default, di trotoar jalan B (NLoS dari BS).
- **Target**: Q = 1 default (Q = 2 sebagai perluasan), bergerak di lajur jalan B.

Koordinat pasti ditentukan di Fase 1 relatif terhadap scene yang dipilih dan disimpan di `configs/`.

### 2.2 Pilihan scene

| Tahap | Scene | Alasan |
|---|---|---|
| Pengembangan | Scene sintetis berbentuk L (dua jalan tegak lurus, gedung kotak) dibuat dari mesh sederhana | Geometri terkendali, cepat, mudah di-debug |
| Eksperimen utama | Satu scene kota bawaan Sionna RT dengan persimpangan yang cocok (cek daftar scene bawaan di versi terpasang, misalnya Munich atau Etoile) | Site-specific nyata, bisa direproduksi orang lain |
| Opsional | Scene dari OpenStreetMap (mis. kawasan Yogyakarta) | Nilai tambah lokal; butuh konversi Blender → Mitsuba XML |

### 2.3 Mobilitas

- Langkah waktu Δt = 0,1 s, horizon episode T = 50 langkah (5 s).
- Target: kecepatan 1–10 m/s, lintasan lurus di lajur jalan B dengan sedikit perubahan lajur acak. Bila lintasan keluar ROI, episode terpotong.
- Pengguna: pejalan kaki 0–1,5 m/s, random waypoint di trotoar.
- Lintasan dibagi menjadi **train / val / test** dengan seed yang tidak tumpang tindih. Kanal dihitung di setiap titik lintasan (bukan diinterpolasi dari grid kasar), karena fading skala kecil berubah dalam orde λ/2.

---

## 3. Model Sistem

### 3.1 Notasi

| Simbol | Dimensi | Arti |
|---|---|---|
| N_t, N_r | skalar | Jumlah antena pancar / terima BS |
| M = M_y × M_z | skalar | Jumlah elemen RIS (UPA, jarak λ/2) |
| φ ∈ [0, 2π)^M | M | Fasa RIS; Θ = diag(e^{jφ}) |
| **G** | M × N_t | Kanal BS-tx → RIS |
| **H** | N_r × M | Kanal RIS → BS-rx |
| **h**_{d,k} | N_t | Kanal langsung BS → pengguna k (sinyal terima = **h**_{d,k}^T **x**) |
| **g**_k | M | Kanal RIS → pengguna k (elemen m sebagai pemancar) |
| **g**_t | M | Kanal RIS ↔ target (resiprokal) |
| **h**_{d,t}, **h**^{(r)}_{d,t} | N_t, N_r | Kanal langsung BS ↔ target (≈ 0 karena NLoS, tetap dihitung) |
| **H**_c | N_r × N_t | Kanal clutter monostatik BS-tx → lingkungan → BS-rx (tanpa jalur LoS tx–rx) |
| **W**_c = [**w**_1 … **w**_K] | N_t × K | Precoder komunikasi |
| **w**_s | N_t | Beam sensing (aliran radar khusus) |
| P_max | skalar | Daya pancar maksimum BS |
| σ_n² | skalar | Daya derau per antena terima |

Semua kanal adalah koefisien baseband pita sempit pada frekuensi pembawa f_c (penjumlahan koefisien jalur dari CIR Sionna).

### 3.2 Sinyal pancar

**x** = **W**_c **s**_c + **w**_s s_s, dengan E[**s s**^H] = **I** dan

**R**_x = **W**_c **W**_c^H + **w**_s **w**_s^H, tr(**R**_x) ≤ P_max. (E1)

### 3.3 Komunikasi downlink

Kanal efektif pengguna k:

**h**_{e,k}^T = **h**_{d,k}^T + **g**_k^T Θ **G**. (E2)

SINR pengguna k:

SINR_k = |**h**_{e,k}^T **w**_k|² / ( Σ_{j≠k} |**h**_{e,k}^T **w**_j|² + β_s |**h**_{e,k}^T **w**_s|² + σ_n² ), (E3)

β_s ∈ {0, 1}: β_s = 1 (default, konservatif) berarti aliran sensing menjadi interferensi; β_s = 0 berarti pengguna dapat membatalkannya.

R_k = log₂(1 + SINR_k). (E4)

### 3.4 Sensing

Kanal efektif BS → target dan target → BS:

**c**^T = **h**_{d,t}^T + **g**_t^T Θ **G**, **b** = **h**^{(r)}_{d,t} + **H** Θ **g**_t. (E5)

Echo dari target titik dengan RCS σ_rcs dan fasa acak α (|α| = 1):

**y** = √σ_rcs · α · **b c**^T **x** + **H**_c **x** + **n**. (E6)

Dengan combiner MVDR dan integrasi koheren L sampel per frame, SCNR setelah penekanan clutter nol-Doppler adalah

SCNR = σ_rcs · (**c**^T **R**_x **c**^*) · **b**^H **R**_{cn}^{-1} **b**, (E7)
**R**_{cn} = ξ · **H**_c **R**_x **H**_c^H + (σ_n² / L) · **I**_{N_r}.

- L: jumlah sampel terintegrasi per frame (gain pemrosesan terhadap derau).
- ξ ∈ (0, 1]: fraksi clutter tersisa setelah filter nol-Doppler (MTI). ξ = 1 berarti tanpa MTI (kasus terburuk / target diam). Default ξ = 0,01 (penekanan 20 dB); disapu di E4.
- **c**^T **R**_x **c**^* adalah daya iluminasi di target, analog persamaan (7) paper sebelumnya tetapi berbasis posisi, bukan sudut.

Target dianggap terdeteksi bila SCNR ≥ Γ. Default Γ = 13 dB (kira-kira P_d = 0,9 pada P_fa = 10⁻⁶ untuk target non-fluktuasi menurut aproksimasi Albersheim; verifikasi angka ini sebelum dipakai di paper).

### 3.5 Clutter

- **Default (fase 1):** **H**_c dari ray tracing monostatik BS-tx → BS-rx dengan jalur LoS tx–rx dibuang (hanya pantulan, difraksi, hamburan dari lingkungan).
- **Opsional (fase 2):** clutter lewat RIS, **H** Θ **C**_R Θ **G**, dengan **C**_R (M × M) jalur RIS → lingkungan → RIS (dengan ≥ 1 interaksi, kopling langsung antar-elemen dibuang). Hanya diaktifkan jika biaya ray tracing M × M terjangkau.

### 3.6 Masalah optimasi (acuan)

max_{φ, W_c, w_s} min_k R_k
s.t. SCNR_q ≥ Γ ∀q, tr(**R**_x) ≤ P_max, |e^{jφ_m}| = 1 (atau φ_m ∈ himpunan b-bit). (E8)

Ini adalah acuan untuk oracle; agen DRL menangani versi sekuensial dengan observasi parsial (Bagian 5).

### 3.7 Asumsi yang harus dinyatakan di paper

1. Kanal pita sempit pada f_c; OFDM pita lebar sebagai pekerjaan lanjutan.
2. Isolasi tx/rx BS dianggap cukup (self-interference full-duplex tidak dimodelkan di paper ini).
3. Target titik dengan RCS konstan; mesh target tidak memblokir jalur lain.
4. RIS dimodelkan sebagai array elemen independen (Bagian 4); pantulan bertingkat yang melewati RIS dua kali dan kopling antar-elemen diabaikan.
5. **G** statis dan diketahui (BS dan RIS diam; dikalibrasi sekali).
6. Penekanan clutter dimodelkan dengan faktor ξ, bukan pemrosesan range-Doppler penuh.

---

## 4. Ekstraksi Kanal dengan Sionna RT (Pendekatan Hibrida)

### 4.1 Alasan

Sionna RT 1.x/2.x (Dr.Jit + Mitsuba 3) belum mendukung RIS; dukungan RIS hanya ada di Sionna 0.19.2. Pendekatan hibrida memakai versi terbaru untuk kanal penyusun dan menerapkan Θ di Python. Ray tracing hanya dijalankan sekali per posisi, sehingga satu langkah environment hanya berupa operasi aljabar linier kecil.

### 4.2 Prosedur

RIS dimodelkan sebagai **perangkat radio dengan array planar M elemen** (jarak λ/2, pola elemen kosinus atau pola bawaan yang mendekati), di posisi dan orientasi RIS. Mesh RIS **tidak** dimasukkan ke scene (agar tidak menjadi pemantul pasif ganda).

| Kanal | Pemancar | Penerima | Catatan |
|---|---|---|---|
| **G** | BS-tx (N_t) | RIS (M) | Dihitung sekali |
| **H** | RIS (M) | BS-rx (N_r) | Dihitung sekali; cek resiprositas terhadap **G** untuk geometri yang setara |
| **g**_k | RIS (M) | Titik lintasan pengguna (1 antena) | Per titik lintasan |
| **g**_t | RIS (M) | Titik lintasan target (1 antena isotropik) | Per titik lintasan |
| **h**_{d,k}, **h**_{d,t} | BS-tx (N_t) | Titik lintasan | Per titik; seharusnya sangat lemah di ROI |
| **h**^{(r)}_{d,t} | Titik lintasan target | BS-rx (N_r) | Per titik |
| **H**_c | BS-tx (N_t) | BS-rx (N_r) | Sekali; buang jalur LoS |

Pengaturan ray tracing: **kedalaman pantulan maks 5**, pantulan spekular + difus, difraksi aktif (v1.2+), jumlah sampel per sumber disesuaikan sampai hasil stabil. **Array per-elemen** (bukan synthetic array) untuk RIS karena pengguna dan target bisa berada di dekat jarak Fraunhofer RIS; uji perbedaannya di E0.

Kedalaman 5 **diukur, bukan dipilih** (Fase 1 revisi, `docs/LOG.md` 2026-11-11). Pada kedalaman 3 yang dipakai semula, median |h_d|² di ROI meleset ~35 dB karena jalur pembawa daya di kanyon NLoS justru berpantulan 4–6 kali; nilainya baru stabil pada 5–6 (sisa fluktuasi ±2 dB akibat derau Monte Carlo). Menaikkan `samples_per_src` dari 1e6 ke 3e7 tidak memperbaikinya — kedalaman, bukan anggaran sampel, yang membatasi.

Hamburan difus memerlukan `scattering_coefficient > 0` pada material: `ITURadioMaterial` di Sionna 2.2 memakai default **0,0**, sehingga mengaktifkan hamburan difus di solver saja tidak berefek apa pun. Nilai yang dipakai adalah **S = 0,3** untuk beton, di tengah rentang terukur 0,2–0,6 untuk dinding gedung pada model *effective roughness* (Degli-Esposti dkk., IEEE TAP 2007 — model yang sama yang diimplementasikan Sionna), dengan pola hamburan Lambertian.

Dengan array per-elemen, jumlah sumber ray tracing sama dengan M, sehingga **jumlah jalur maksimum per sumber** (`max_num_paths_per_src`) menjadi parameter yang membatasi memori, bukan hanya jumlah sampel. Nilainya harus dilaporkan bersama `samples_per_src` karena menurunkannya memotong jalur dan membiaskan koefisien kanal. Nilai dikunci lewat uji konvergensi di Fase 2: naikkan sampai daya terima total berubah < 0,1 dB. Nama API (misalnya `load_scene`, `PlanarArray`, `Transmitter`, `Receiver`, `PathSolver`) harus diverifikasi di dokumentasi versi terpasang.

Kanal kaskade per elemen m adalah [**g**_k]_m · e^{jφ_m} · [**G**]_{m,:}. Mengalikan koefisien per hop yang dihitung sebagai link antena konsisten dengan model path loss RIS berbasis fisika sampai faktor konstan kecil (orde 1 dB untuk elemen λ/2). Faktor ini dikalibrasi di E0.

### 4.3 Penyimpanan

Semua kanal disimpan sebagai HDF5 per scene/konfigurasi:

```
channels/<scene_id>/<config_hash>.h5
  /static/G, /static/H, /static/Hc
  /meta/  (f_c, posisi BS/RIS, orientasi, parameter RT, versi Sionna, hash config)
  /traj/<split>/<traj_id>/user_k/{pos, g, hd}
  /traj/<split>/<traj_id>/target_q/{pos, vel, g, hd_tx, hd_rx}
```

Environment RL hanya membaca HDF5 dan tidak bergantung pada Sionna. Ini membuat pelatihan cepat, bisa diuji di CPU, dan bisa direproduksi.

### 4.4 Validasi (E0)

Di environment terpisah dengan Sionna 0.19.2, pasang RIS sungguhan dengan profil fasa yang sama (misalnya profil fokus ke satu titik dan profil gradien fasa), lalu bandingkan daya terima di grid ROI terhadap hasil hibrida. Metrik: selisih dB median dan persentil ke-90, korelasi peta cakupan, dan posisi puncak berkas.

---

## 5. Formulasi MDP

### 5.1 Struktur frame

Setiap langkah t (satu frame Δt):
1. Agen memilih aksi a_t dari observasi o_t.
2. RIS diatur ke φ_t. Pengguna mengirim pilot; BS mengestimasi kanal efektif ĥ_{e,k} (dimensi N_t, murah).
3. BS menghitung **W**_c (RZF dari ĥ_{e,k}) dan **w**_s (dari estimasi posisi target).
4. Transmisi dan sensing; reward dihitung dari kanal sebenarnya.
5. Tracker memperbarui estimasi posisi target dari hasil deteksi; entitas bergerak ke posisi berikutnya.

Masalah ini benar-benar sekuensial: iluminasi saat ini menentukan apakah target terdeteksi, yang menentukan kualitas estimasi posisi berikutnya, yang menentukan kualitas beam sensing berikutnya. Fasa RIS juga berubah secara inkremental.

### 5.2 Observasi (parsial, default)

| Komponen | Dimensi | Keterangan |
|---|---|---|
| ĥ_{e,k} di bawah φ_{t−1} | 2 N_t K | Re/Im, dengan galat estimasi NMSE ε (default −20 dB) |
| SINR terlapor tiap pengguna | K | dB, terkuantisasi 1 dB, dibatasi [−10, 40] |
| Estimasi posisi pengguna | 2K | Galat Gaussian σ_u = 0,5 m, dinormalisasi ke ROI |
| Estimasi posisi dan kecepatan target (tracker) | 4Q | Output filter Kalman kecepatan-konstan |
| Flag deteksi dan SCNR terakhir | 2Q | SCNR dB dibatasi [−20, 40] |
| Fasa RIS sebelumnya (cos, sin) | 2M | Agen mengetahui aksinya sendiri |
| Fraksi daya sensing sebelumnya ρ_{t−1} | 1 | |

Model galat posisi target dari sensing: bila SCNR ≥ Γ, pengukuran posisi = posisi sebenarnya + noise dengan σ_pos = σ_ref · √(Γ_lin / SCNR_lin), σ_ref = 0,5 m, dibatasi σ_max = 5 m (skala ∝ 1/√SNR mengikuti perilaku batas Cramér–Rao). Bila SCNR < Γ, tidak ada pengukuran; tracker hanya memprediksi.

**Varian observasi penuh (FullCSI, untuk pembanding):** tambahkan **g**_k, **g**_t (2M(K+Q)) dan posisi sebenarnya. **G** tidak perlu dimasukkan karena statis.

Observasi dinormalisasi dengan statistik berjalan (running mean/std) yang dibekukan saat evaluasi.

### 5.3 Aksi (default: model-informed)

a_t = [Δφ ∈ [−1,1]^M, ρ_raw ∈ [−1,1], p_raw ∈ [−1,1]^K]

- Fasa RIS inkremental: φ_t = (φ_{t−1} + κπ Δφ) mod 2π, κ = 0,1. (Mode absolut φ_t = π(Δφ + 1) sebagai ablasi.)
- Kuantisasi opsional b bit (b ∈ {1, 2, ∞}) diterapkan setelahnya.
- Fraksi daya sensing: ρ = (ρ_raw + 1)/2.
- Bobot daya pengguna: p = softmax(p_raw).
- Precoder: arah kolom **W**_c = RZF dari ĥ_{e,k} (regularisasi K σ_n²/P_max), dinormalisasi, diskalakan √((1−ρ) P_max p_k).
- Beam sensing: **w**_s = √(ρ P_max) · ĉ^*/‖ĉ‖, dengan ĉ^T = ĝ_t^T Θ **G**, dan ĝ_t dari model LoS gelombang sferis antara elemen RIS dan estimasi posisi target. Jadi tidak memakai kanal target sebenarnya.

Dimensi aksi M + 1 + K, jauh lebih kecil daripada mengeluarkan **W** langsung (2 N_t (K+1)). Varian **direct-W** diuji sebagai ablasi.

### 5.4 Reward

r_t = min_k R_k − λ · Σ_q [Γ_dB − SCNR_{q,dB}]_+ / 10. (E9)

- Hinge kontinu: penalti hanya ketika SCNR **di bawah** ambang, sesuai kendala (E8). Ini memperbaiki indikator terbalik pada reward paper sebelumnya.
- λ default 1,0; disapu untuk membentuk kurva Pareto.
- Varian Lagrangian (ablasi): λ diperbarui per iterasi pelatihan, λ ← [λ + η(Γ − rata-rata SCNR_dB)]_+.
- Varian indikator (ablasi): −λ Σ_q 1[SCNR_q < Γ] untuk membandingkan dengan reward lama.

### 5.5 Episode

- `reset()`: ambil satu set lintasan (pengguna + target) dari split aktif; φ_0 diinisialisasi acak (default) atau dari baseline geometris (ablasi); tracker diinisialisasi dari posisi awal dengan noise.
- Episode berakhir (truncated) pada T = 50 atau saat target keluar ROI.
- Faktor diskon γ = 0,95 (horizon efektif ~20 langkah = 2 s).

---

## 6. Metode yang Dibandingkan

### 6.1 Agen DRL

| ID | Metode | Observasi | Catatan |
|---|---|---|---|
| M1 | **PPO-PO** (utama) | Parsial + frame-stack 4 | MLP 2×256 |
| M2 | RecurrentPPO-PO | Parsial | LSTM 128 (sb3-contrib) |
| M3 | SAC-PO | Parsial + frame-stack 4 | Off-policy pembanding |
| M4 | PPO-FullCSI | Penuh | Batas atas untuk agen terlatih |
| M5 | PPO-PO-directW | Parsial | Ablasi: aksi **W** langsung |
| M6 | PPO-PO-indicator | Parsial | Ablasi: reward indikator |

### 6.2 Baseline non-learning

| ID | Baseline | Informasi yang dipakai |
|---|---|---|
| B1 | **Random**: fasa RIS acak per langkah, ρ terbaik dari grid di set validasi | Sama dengan M1 |
| B2 | **Geometric**: φ_m = −arg( Σ_i ω_i [ĝ_i]_m [**G ā**]_m ), dengan ĝ_i model LoS ke estimasi posisi pengguna dan target, **ā** vektor singular kanan utama **G**; ω_i dan ρ dipilih di set validasi | Sama dengan M1 |
| B3 | **Oracle-GD**: optimasi gradien (Adam) per langkah atas φ, ρ, p dengan struktur precoder yang sama, CSI dan posisi sebenarnya; objektif = softmin(R) − λ·softplus-hinge(SCNR); 300 iterasi, 4 restart (geometris + acak) | CSI sempurna |
| B4 | **Oracle-GD-freeW**: seperti B3 tetapi **W**_c dan **w**_s dioptimasi bebas dengan proyeksi daya | CSI sempurna, batas atas |
| B5 | **Oracle-GD-stale(D)**: B3 dijalankan setiap D langkah (D ∈ {5, 10}) dan ditahan di antaranya, meniru latensi komputasi | CSI sempurna tetapi usang |

Oracle-GD dipilih karena memakai objektif yang identik dengan reward sehingga perbandingannya adil. Alternating optimization berbasis SDR (CVXPY) boleh ditambahkan sebagai pembanding tambahan jika waktu memungkinkan.

### 6.3 Hiperparameter awal

| Parameter | PPO | SAC |
|---|---|---|
| Learning rate | 3e-4 | 3e-4 |
| γ | 0,95 | 0,95 |
| GAE λ | 0,95 | – |
| Clip ε | 0,2 | – |
| n_steps × n_envs | 512 × 16 | – |
| Batch / epoch | 256 / 10 | 256 / – |
| Entropy coef | 0,0 (sapu {0, 0,01}) | auto |
| Buffer | – | 1e6 |
| Total langkah | 2e6 (naikkan bila belum konvergen) | 1e6 |

Library: Stable-Baselines3 + sb3-contrib. Tuning ringan hanya di set validasi, lalu dibekukan.

---

## 7. Daftar Eksperimen

### E0 — Validasi kanal hibrida (RQ4)
- **Desain:** scene pengembangan dan scene utama; 3 profil fasa RIS (fokus ke 3 titik berbeda) + 1 profil gradien; bandingkan hibrida (per-elemen dan synthetic array) vs Sionna 0.19.2.
- **Metrik:** selisih dB median dan P90 di ROI; korelasi peta cakupan; selisih posisi puncak (m); faktor kalibrasi konstan.
- **Output:** Gambar F3 (scatter dB hibrida vs referensi, peta selisih), Tabel T1.

### E1 — Kelayakan link budget dan peta cakupan
- **Desain:** peta daya BS langsung vs lewat RIS (profil fokus) di ROI untuk M ∈ {64, 144, 256}, P_max ∈ {20, 30, 40} dBm.
- **Gate:** lihat `TASKS.md` Fase 1.
- **Output:** Gambar F1 (tata letak), F2 (peta cakupan).

### E2 — Konvergensi pelatihan
- **Desain:** M1–M4, 5 seed masing-masing.
- **Metrik:** reward episode, rate minimum, tingkat pemenuhan SCNR vs langkah pelatihan (rata-rata ± std antar-seed).
- **Output:** Gambar F4.

### E3 — Kinerja utama pada set test
- **Desain:** semua metode (M1–M4, B1–B5) pada 200 episode test dengan seed tetap.
- **Metrik:** rata-rata dan CDF rate minimum; tingkat pemenuhan SCNR (% langkah SCNR ≥ Γ); durasi track (langkah berturut-turut terdeteksi); galat posisi tracker.
- **Output:** Tabel T2, Gambar F5 (CDF rate minimum), F6 (contoh episode: SCNR terhadap waktu dan flag deteksi).

### E4 — Sapuan parameter (RQ3)
- **Variabel:** M ∈ {64, 144, 256}; P_max ∈ {20, 25, 30, 35, 40} dBm; Γ ∈ {7, 10, 13, 16} dB; λ ∈ {0,1, 0,3, 1, 3, 10}; ξ ∈ {1, 0,1, 0,01, 0,001}; kecepatan target ∈ {1, 5, 10} m/s.
- **Prinsip:** ubah satu variabel dari nilai default; untuk M dan kecepatan, latih ulang agen; untuk λ, latih ulang untuk membentuk Pareto.
- **Output:** Gambar F7 (rate dan pemenuhan SCNR vs M dan P_max), F8 (Pareto rate–SCNR).

### E5 — Ketahanan
- **Variabel (tanpa latih ulang):** NMSE kanal efektif ε ∈ {−30, −20, −10} dB; σ_u ∈ {0,1, 0,5, 2} m; σ_ref ∈ {0,25, 0,5, 1} m; galat kalibrasi **G** (NMSE −20 dB).
- **Output:** Gambar F9.

### E6 — Ablasi
- Aksi: inkremental vs absolut; model-informed vs direct-W (M5); b ∈ {1, 2, ∞} bit.
- Memori: tanpa frame-stack vs frame-stack vs LSTM (M2).
- Reward: hinge vs indikator (M6) vs Lagrangian.
- Clutter: aktif vs nonaktif saat pelatihan (dievaluasi dengan clutter aktif).
- **Output:** Tabel T3.

### E7 — Biaya komputasi
- **Metrik:** waktu inferensi per keputusan (CPU dan GPU) untuk M1/M2 vs waktu per langkah B3/B4; waktu pelatihan total; waktu prakomputasi ray tracing.
- **Output:** Tabel T4.

---

## 8. Parameter Default

| Parameter | Nilai | Catatan |
|---|---|---|
| f_c | 3,5 GHz | λ ≈ 8,57 cm |
| Bandwidth B | 20 MHz | |
| Noise figure | 7 dB | σ_n² ≈ −174 + 10log₁₀(B) + NF ≈ −94 dBm |
| N_t = N_r | 8 (ULA horizontal, λ/2) | Panel tx/rx terpisah 0,5 m vertikal |
| M | 144 (12 × 12) | Sapuan 64 / 144 / 256 |
| P_max | 30 dBm | Sapuan 20–40 dBm |
| K, Q | 2, 1 | Q = 2 sebagai perluasan |
| σ_rcs | 1 m² | Varian kendaraan 10 m² |
| L | 256 | Sampel terintegrasi per frame |
| ξ | 0,01 | |
| Γ | 13 dB | |
| β_s | 1 | |
| Δt, T | 0,1 s, 50 | |
| κ | 0,1 | |
| λ | 1,0 | |
| ε (NMSE ĥ_e) | −20 dB | |
| σ_u, σ_ref, σ_max | 0,5 m, 0,5 m, 5 m | |
| Ray tracing | max_depth 5, spekular + difus + difraksi | Kedalaman diukur di Fase 1 revisi; depth 3 meleset ~35 dB |
| `scattering_coefficient` (beton) | 0,3 | Lambertian; default Sionna 0,0 membuat hamburan difus tidak berefek |
| `max_num_paths_per_src` | 1e5 (M ≤ 144), 5e4 (M = 256) | Batas memori array per-elemen; dikunci lewat uji konvergensi §4.2 |
| Lintasan | 400 train / 50 val / 100 test | Per scene |

Semua nilai ada di `configs/base.yaml`. Satu sumber, tidak ada angka yang ditulis langsung di kode.

---

## 9. Protokol Statistik dan Pelaporan

- 5 seed pelatihan per metode/konfigurasi. Evaluasi tiap seed pada 200 episode test yang sama.
- Laporkan rata-rata ± interval kepercayaan 95% (bootstrap atas seed). Kurva pelatihan: rata-rata dengan pita ± std.
- Uji beda utama (M1 vs B2, M1 vs B5): Welch t-test atas rata-rata per seed; laporkan juga ukuran efek.
- Semua hasil disimpan sebagai CSV/Parquet beserta hash config dan commit git; gambar dibuat ulang dari file hasil, bukan dari memori proses pelatihan.
- Kode dan config dirilis bersama paper.

---

## 10. Risiko dan Mitigasi

| Risiko | Gejala | Mitigasi |
|---|---|---|
| Link lewat RIS terlalu lemah (path loss ganda) | SNR via RIS < 0 dB di sebagian besar ROI | Perbesar M, geser RIS lebih dekat ke ROI, naikkan P_max (Gate Fase 1) |
| SCNR tidak pernah mencapai Γ (path loss empat hop) | Oracle pun gagal | Atur L, σ_rcs, Γ berdasarkan uji kelayakan oracle (Gate Fase 4) |
| PPO macet karena dimensi aksi besar | Reward datar | Aksi inkremental, inisialisasi geometris, kurikulum (target diam dulu), normalisasi reward |
| Ray tracing per-elemen terlalu mahal | Prakomputasi berhari-hari | Batch penerima, kurangi sampel, synthetic array di luar jarak Fraunhofer setelah diuji di E0 |
| Perubahan API Sionna | Kode gagal setelah upgrade | Kunci versi; dua environment terpisah (RT terbaru dan 0.19.2) |
| Kode menyimpang dari dokumen | Hasil tidak cocok dengan paper | Skrip pengecek konsistensi parameter; uji unit per persamaan |

---

## 11. Rencana Gambar dan Tabel Paper

| ID | Isi |
|---|---|
| F1 | Tampak atas scene: BS, RIS, ROI, contoh lintasan |
| F2 | Peta cakupan: BS langsung vs lewat RIS |
| F3 | Validasi kanal hibrida vs Sionna 0.19.2 |
| F4 | Kurva pelatihan M1–M4 |
| F5 | CDF rate minimum semua metode |
| F6 | Contoh episode: SCNR, ambang Γ, flag deteksi, galat posisi terhadap waktu |
| F7 | Kinerja vs M dan P_max |
| F8 | Pareto rate minimum vs pemenuhan SCNR |
| F9 | Ketahanan terhadap galat estimasi |
| T1 | Galat validasi kanal |
| T2 | Hasil utama set test |
| T3 | Ablasi |
| T4 | Biaya komputasi |

---

## 12. Referensi Kunci

- Aït Aoudia, F. dkk. (2025). Sionna RT: Technical Report. arXiv:2504.21719.
- Hoydis, J. dkk. (2023). Sionna RT: Differentiable Ray Tracing for Radio Propagation Modeling. arXiv:2303.11103.
- Hoydis, J. dkk. (2024). Learning Radio Environments by Differentiable Ray Tracing. IEEE TMLCN. doi:10.1109/tmlcn.2024.3474639.
- Liu, R. dkk. (2026). Clutter-Aware Integrated Sensing and Communication: Models, Methods, and Future Directions. arXiv:2602.10537.
- Lemić, F. dkk. (2026). Unified Evaluation Methodology for AI-Native Integrated Sensing and Communication. arXiv:2607.14806.
- Güneşer, A. E. dkk. (2025). RIS Optimization Algorithms for Urban Wireless Scenarios in Sionna RT. arXiv:2501.05817.
- Tarafder dkk. (2026). Digital-Twin Empowered DRL for Site-Specific Radio Resource Management. arXiv:2602.03801.
- Schulman, J. dkk. (2017). Proximal Policy Optimization Algorithms. arXiv:1707.06347.

Tambahkan referensi model path loss RIS berbasis fisika dan aproksimasi Albersheim setelah diverifikasi.
