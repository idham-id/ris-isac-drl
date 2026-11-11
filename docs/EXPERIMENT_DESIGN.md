# Rancangan Eksperimen (Versi Ramping): DRL untuk RIS-Assisted ISAC pada Skenario NLoS Site-Specific

**Judul kerja:** *Deep Reinforcement Learning for RIS-Assisted Integrated Sensing and Communication in Site-Specific NLoS Scenarios with Partial Observations and Moving Targets*

**Versi:** 0.2-lean (11 November 2026). Menggantikan v0.1.
**Target:** jurnal Q2, naskah siap kirim dalam ≤ 8 minggu, PC dengan GPU 12 GB VRAM.

Dokumen ini adalah **sumber kebenaran tunggal** untuk model sistem, MDP, baseline, dan eksperimen. Setiap rumus di kode harus bisa ditelusuri ke nomor persamaan di sini.

### Perubahan dari v0.1

| Aspek | v0.1 | v0.2-lean |
|---|---|---|
| Ukuran RIS | M = 144, sapuan 64/144/256 | **M = 64 (8×8) tetap** |
| Scene | Sintetis + kota bawaan + OSM | **Sintetis berbentuk L saja**; scene kota opsional |
| Validasi kanal (E0) | Terhadap Sionna 0.19.2 (env kedua) | **Terhadap model analitik ruang bebas**; tanpa env kedua |
| Metode DRL | PPO, RecurrentPPO, SAC, FullCSI, directW, indicator | **PPO-PO dan PPO-FullCSI**; satu ablasi |
| Baseline | 5 | **4** (Random, Geometric, Oracle-GD, Oracle-GD-stale) |
| Sapuan | M, P_max, Γ, λ, ξ, kecepatan + ketahanan | **P_max dan kecepatan** (tanpa latih ulang), **Γ** (latih ulang) |
| Seed | 5 | **3** |
| Lintasan | 400 / 50 / 100 | **200 / 30 / 50** |
| Integrasi sensing L | 256 | **4096** (hasil hitung link budget, §3.8) |
| SCNR (E7) | σ_rcs langsung | **Dikoreksi dengan faktor 4πσ_rcs/λ²** |

---

## 0. Ringkasan

Sebuah BS ISAC monostatik melayani K = 2 pengguna downlink dan memantau Q = 1 target bergerak di area **NLoS** (terhalang gedung dari BS). Satu RIS 8×8 di dinding sudut persimpangan menciptakan jalur virtual-LoS ke area tersebut. Agen DRL mengatur fasa RIS dan pembagian daya komunikasi–sensing setiap frame, **tanpa CSI kaskade per elemen** (observasi parsial). Precoder BS dihitung analitik dari kanal efektif.

Kanal dihasilkan dengan **Sionna RT** melalui **pendekatan hibrida**: kanal penyusun dihitung sekali dengan ray tracing dan disimpan ke HDF5, lalu fasa RIS diterapkan di Python.

Kontribusi yang ditargetkan:
1. Lingkungan RL untuk RIS-ISAC dengan kanal site-specific dari ray tracing, clutter dari lingkungan, dan target bergerak di area NLoS.
2. Formulasi MDP dengan observasi parsial (kanal efektif + estimasi posisi dari tracker) sehingga keputusan saat ini memengaruhi kualitas observasi berikutnya.
3. Perbandingan DRL terhadap baseline geometris dan oracle ber-CSI-sempurna, termasuk oracle dengan CSI usang dan biaya komputasi.

---

## 1. Pertanyaan Riset dan Hipotesis

| ID | Pertanyaan | Hipotesis (target awal, bukan klaim) | Eksperimen |
|---|---|---|---|
| RQ1 | Seberapa dekat agen DRL dengan observasi parsial terhadap oracle ber-CSI-sempurna? | PPO-PO mencapai ≥ 80% rate minimum Oracle-GD dengan pemenuhan SCNR yang sebanding, dan inferensinya jauh lebih cepat | E3, E6 |
| RQ2 | Apakah agen mempertahankan deteksi target bergerak lebih baik daripada steering geometris dan re-optimasi berkala? | PPO-PO mengungguli Geometric dan Oracle-GD-stale, terutama pada kecepatan target tinggi | E3, E4 |
| RQ3 | Bagaimana trade-off komunikasi–sensing berubah terhadap ambang SCNR dan daya? | Menaikkan Γ menurunkan rate minimum secara monoton; selisih PPO-PO terhadap Geometric membesar pada daya rendah | E4 |
| RQ4 | Apakah kanal hibrida konsisten dengan model RIS analitik? | Selisih ≤ 0,5 dB pada konfigurasi ruang bebas setelah kalibrasi konstan | E0 |

Revisi angka hipotesis setelah Fase 3 jika tidak realistis.

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

- **BS**: di jalan A, ketinggian ~10 m, **jarak ke RIS ≈ 20 m**. Panel pancar dan terima terpisah 0,5 m vertikal.
- **RIS**: di dinding sudut, ketinggian ~6 m, menghadap jalan B.
- **ROI**: segmen jalan B **10–30 m** dari RIS. Tidak ada LoS dari BS ke titik mana pun di ROI (dicek otomatis).
- **Pengguna**: K = 2, di trotoar jalan B.
- **Target**: Q = 1, bergerak di lajur jalan B.

Jarak BS–RIS dan ROI dipilih dari hitungan link budget (§3.8); keduanya bisa digeser di Fase 1 jika gate gagal.

**Lebar jalan ditetapkan 6 m di Fase 1 melalui pengukuran** (`scripts/place_geometry.py`, `docs/LOG.md` 2026-11-11). Dua syarat berbeda harus dipenuhi sekaligus, dan keduanya dikendalikan lebar jalan.

*Syarat bayangan.* "0% LoS BS→ROI" menuntut BS cukup jauh di barat sudut, `u ≥ 2a/(s−1)` dengan `a` setengah lebar jalan, sehingga jalan 20 m memaksa d(BS–RIS) = 50,6 m sedangkan jalan 6 m cukup jauh di bawah 20 m.

*Syarat premis.* NLoS saja tidak cukup: ROI bisa **tanpa garis pandang tetapi tidak kekurangan daya**, karena gelombang langsung tetap sampai sebagai gelombang **terpandu** yang memantul di antara kedua dinding jalan B. Jumlah pantulan yang dibutuhkannya sebanding dengan jarak/lebar, sedangkan hop RIS→ROI adalah LoS dan tidak terpengaruh lebar sama sekali. **Mempersempit jalan karena itu melemahkan jalur langsung tanpa melemahkan jalur RIS.** Terukur pada d(BS–RIS) ≈ 20 m (penguatan RIS median / fraksi titik ≥ 6 dB):

| lebar jalan | 10 m | 9 m | 8 m | 7 m | **6 m** |
|---|---|---|---|---|---|
| d(BS–RIS) | 19,6 m | 20,0 m | 19,6 m | 20,2 m | 20,0 m |
| jalur langsung (MRT) | −70,9 dB | −78,3 dB | −80,8 dB | −84,3 dB | **−87,8 dB** |
| penguatan RIS median | +0,8 dB | +3,4 dB | +5,8 dB | +8,2 dB | **+11,9 dB** |
| fraksi ROI ≥ 6 dB | 0,02 | 0,16 | 0,46 | 0,78 | **0,93** |

Kaskade RIS praktis tidak bergerak di seluruh baris itu (−76,9 sampai −75,4 dB); yang berubah 17 dB hanyalah jalur langsung. Itulah bukti bahwa lebar jalan bekerja lewat gelombang terpandu, bukan lewat link budget RIS.

Tuas kedua adalah memundurkan BS di jalan A, yang memaksa gelombang langsung membelok lebih tajam; pada lebar 6 m tuas itu tidak diperlukan, sehingga d(BS–RIS) = 20,0 m tetap seperti yang diminta di atas. Penampang 6 m: trotoar 2 × 1,0 m + lajur 2 × 2,0 m — jalan kota tua yang padat, yaitu justru tempat pemasangan RIS masuk akal.

Penempatan akhir memaksimalkan penguatan RIS atas sistem tanpa RIS dengan kendala Gate 1 lainnya, **bukan** meminimalkan d(BS–RIS).

### 2.2 Scene

- **Utama:** scene sintetis berbentuk L (dua jalan tegak lurus, gedung kotak beton, tanah), dibuat sebagai mesh + XML Mitsuba. Geometri terkendali dan cepat dihitung.
- **Opsional (hanya jika waktu tersisa di minggu ke-7):** satu scene kota bawaan Sionna RT sebagai uji tambahan tanpa latih ulang.

### 2.3 Mobilitas

- Δt = 0,1 s, horizon T = 50 langkah (5 s).
- Target: kecepatan diacak per episode dari 1–10 m/s, lintasan di lajur jalan B dengan perubahan lajur acak kecil. Episode terpotong jika target keluar ROI.
- Pengguna: pejalan kaki 0–1,5 m/s, random waypoint di trotoar.
- Split lintasan **200 train / 30 val / 50 test** dari seed terpisah. Kanal dihitung di setiap titik lintasan (tidak diinterpolasi).

---

## 3. Model Sistem

### 3.1 Notasi

| Simbol | Dimensi | Arti |
|---|---|---|
| N_t, N_r | skalar | Jumlah antena pancar / terima BS (8 / 8) |
| M = 8 × 8 | skalar | Jumlah elemen RIS (UPA, jarak λ/2) |
| φ ∈ [0, 2π)^M | M | Fasa RIS; Θ = diag(e^{jφ}) |
| **G** | M × N_t | Kanal BS-tx → RIS |
| **H** | N_r × M | Kanal RIS → BS-rx |
| **h**_{d,k} | N_t | Kanal langsung BS → pengguna k |
| **g**_k | M | Kanal RIS → pengguna k |
| **g**_t | M | Kanal RIS ↔ target (resiprokal) |
| **h**_{d,t}, **h**^{(r)}_{d,t} | N_t, N_r | Kanal langsung BS ↔ target (≈ 0 karena NLoS, tetap dihitung) |
| **H**_c | N_r × N_t | Kanal clutter monostatik BS-tx → lingkungan → BS-rx (tanpa jalur LoS tx–rx) |
| **W**_c = [**w**_1 … **w**_K] | N_t × K | Precoder komunikasi |
| **w**_s | N_t | Beam sensing |
| P_max | skalar | Daya pancar maksimum BS |
| σ_n² | skalar | Daya derau per antena per sampel |
| λ_c | skalar | Panjang gelombang pembawa |

Semua kanal adalah koefisien baseband pita sempit pada f_c, ternormalisasi seperti Friis (|h|² = gain link termasuk pola antena). Kode menyebut panjang gelombang `wavelength` agar tidak tertukar dengan λ bobot reward.

### 3.2 Sinyal pancar

**x** = **W**_c **s**_c + **w**_s s_s, E[**s s**^H] = **I**,

**R**_x = **W**_c **W**_c^H + **w**_s **w**_s^H, tr(**R**_x) ≤ P_max. (E1)

### 3.3 Komunikasi downlink

**h**_{e,k}^T = **h**_{d,k}^T + **g**_k^T Θ **G**. (E2)

SINR_k = |**h**_{e,k}^T **w**_k|² / ( Σ_{j≠k} |**h**_{e,k}^T **w**_j|² + β_s |**h**_{e,k}^T **w**_s|² + σ_n² ), (E3)

dengan β_s = 1 (default; aliran sensing menjadi interferensi).

R_k = log₂(1 + SINR_k). (E4)

### 3.4 Sensing

**c**^T = **h**_{d,t}^T + **g**_t^T Θ **G**, **b** = **h**^{(r)}_{d,t} + **H** Θ **g**_t. (E5)

Echo dari target titik dengan RCS σ_rcs (m²) dan fasa acak α:

**y** = √η · α · **b c**^T **x** + **H**_c **x** + **n**, η = 4π σ_rcs / λ_c². (E6)

Faktor η membuat model kanal ternormalisasi Friis setara dengan persamaan radar bistatik. Untuk f_c = 3,5 GHz dan σ_rcs = 1 m², η ≈ 32,3 dB.

Dengan combiner MVDR dan integrasi koheren L sampel per frame:

SCNR = η · (**c**^T **R**_x **c**^*) · **b**^H **R**_{cn}^{-1} **b**, (E7)
**R**_{cn} = ξ · **H**_c **R**_x **H**_c^H + (σ_n² / L) · **I**_{N_r}.

- L = 4096 (≈ 0,2 ms pada 20 MHz, jauh di bawah durasi frame 0,1 s).
- ξ = 0,01: fraksi clutter tersisa setelah filter nol-Doppler (penekanan 20 dB).
- Bentuk tertutup ini sudah dicek numerik sama dengan maksimum rasio Rayleigh umum.

Target dianggap terdeteksi bila SCNR ≥ Γ. Default **Γ = 13 dB** (kira-kira P_d = 0,9 pada P_fa = 10⁻⁶ untuk target non-fluktuasi; verifikasi dengan aproksimasi Albersheim sebelum dipakai di paper).

### 3.5 Clutter

**H**_c dihitung dengan ray tracing monostatik BS-tx → BS-rx, jalur LoS tx–rx dibuang. Clutter lewat RIS **tidak** dimodelkan di versi ini (dinyatakan sebagai asumsi).

### 3.6 Masalah optimasi (acuan oracle)

max_{φ, W_c, w_s} min_k R_k
s.t. SCNR ≥ Γ, tr(**R**_x) ≤ P_max, |e^{jφ_m}| = 1. (E8)

### 3.7 Asumsi yang dinyatakan di paper

1. Kanal pita sempit pada f_c.
2. Isolasi tx/rx BS cukup; self-interference tidak dimodelkan.
3. Target titik dengan RCS konstan; mesh target tidak dimasukkan ke scene.
4. RIS = array elemen independen; pantulan bertingkat lewat RIS, kopling antar-elemen, dan clutter lewat RIS diabaikan.
5. **G** statis dan diketahui (dikalibrasi sekali).
6. Penekanan clutter dimodelkan dengan faktor ξ.

### 3.8 Link budget kasar (ruang bebas, fokus ideal, ρ = 1)

Dihitung dengan Friis per hop, pola elemen RIS gain π (elemen λ/2), N_t = N_r = 8, P_max = 30 dBm, σ_n² = −94 dBm:

| d(BS–RIS) | M | d(RIS–target) | SNR komunikasi | SNR radar, L = 256 | SNR radar, L = 4096 |
|---|---|---|---|---|---|
| 20 m | 64 | 10 m | 46 dB | 25 dB | 37 dB |
| 20 m | 64 | 20 m | 40 dB | 13 dB | 25 dB |
| 20 m | 64 | 30 m | 37 dB | 6 dB | 18 dB |
| 30 m | 64 | 30 m | 33 dB | −1 dB | 11 dB |

Kesimpulan: dengan M = 64, **sensing adalah kendala yang mengikat**, karena path loss empat hop. Komunikasi punya margin besar sehingga terbatas interferensi. Dengan BS–RIS ≈ 20 m, ROI ≤ 30 m, dan L = 4096, margin ideal di ujung ROI sekitar 5 dB di atas Γ sebelum pembagian daya dan kerugian ray tracing. Ini cukup ketat sehingga Gate 1 dan Gate 3 wajib dicek dengan kanal ray tracing. Skrip perhitungan: `scripts/link_budget.py`.

---

## 4. Ekstraksi Kanal dengan Sionna RT (Pendekatan Hibrida)

### 4.1 Alasan

Sionna RT 1.x/2.x belum mendukung RIS. RIS dimodelkan sebagai perangkat radio dengan array planar M elemen di posisi dan orientasi RIS, **tanpa mesh RIS di scene**. Θ diterapkan di Python. Ray tracing hanya sekali per posisi; satu langkah environment hanya aljabar linier kecil.

### 4.2 Prosedur

| Kanal | Pemancar | Penerima | Kapan |
|---|---|---|---|
| **G** | BS-tx (N_t) | RIS (M) | Sekali |
| **H** | RIS (M) | BS-rx (N_r) | Sekali |
| **H**_c | BS-tx (N_t) | BS-rx (N_r) | Sekali; buang jalur LoS |
| **g**_k, **g**_t | RIS (M) | Titik lintasan (1 antena isotropik) | Per titik |
| **h**_{d,k}, **h**_{d,t} | BS-tx (N_t) | Titik lintasan | Per titik |
| **h**^{(r)}_{d,t} | Titik lintasan | BS-rx (N_r) | Per titik (atau via resiprositas) |

Kedalaman maks **5** (bukan 3 seperti rancangan awal), spekular + difus + difraksi; **array per elemen** untuk RIS.

Kedalaman, `samples_per_src`, dan `max_num_paths_per_src` **diukur sampai konvergen di Fase 1**, tidak diandaikan (`docs/LOG.md` 2026-11-11 (f)). Dengan hamburan difus dimatikan — sehingga himpunan jalur deterministik dan konvergensinya terbaca langsung — daya jalur langsung di ROI adalah −124,5 / −86,4 / −86,4 dB pada kedalaman 3 / 5 / 7: **kedalaman 3 membuang 38 dB** karena gelombang terpandu di jalan sempit butuh lebih banyak pantulan dinding. Dengan difus hidup, hamburan menambal lubang itu sehingga kesalahannya tidak terlihat.

**`normalize_delays=False` wajib.** Default Sionna `Paths.cir()` adalah `True`, yang menggeser tundaan tiap pasangan perangkat sehingga jalur pertamanya tiba di t = 0 — dan ikut **menghapus fasa propagasi** dari koefisien kanal: untuk link LoS fasanya menjadi tepat nol. Fasa relatif antar-elemen dalam satu pemanggilan tetap benar, sehingga profil fokus tetap bekerja dan peta cakupan tetap terlihat wajar; yang rusak adalah fasa relatif **antar-pemanggilan**, yaitu persis yang dibutuhkan penjumlahan koheren **h**_e = **h**_d + **g**^T Θ **G** (E2) dan **c** = **h**_{d,t} + **g**_t^T Θ **G** (E5). Ditemukan oleh uji fasa E0 (`docs/LOG.md` 2026-11-11 (g)); diuji ulang di `tests/test_channels_rt.py`.

Anggaran jalur dibatasi VRAM pada **hasil kali** `max_num_paths_per_src × jumlah_sumber`, bukan pada nilai per sumber, sehingga satu nilai tetap pasti salah di salah satu sisi: kanal langsung (8 sumber) butuh 10⁶, sedangkan 10⁶ pada kanal RIS per-elemen (64 sumber) adalah 1 GiB per buffer dan OOM. `max_paths_total` karena itu menurunkan nilai per sumber dari anggaran total. Pemotongan jalur **tidak memunculkan error apa pun**: pada 10⁵ jalur, menaikkan `samples_per_src` dari 10⁵ ke 10⁷ menjatuhkan daya jalur langsung dari −86 ke −144 dB. Uji kewarasannya: daya dengan difus hidup tidak boleh lebih kecil daripada dengan difus mati. Jarak Fraunhofer RIS 8×8 sekitar 3–6 m (2D²/λ dengan D = sisi 0,34 m atau diagonal 0,49 m), jadi ROI (≥ 10 m) umumnya di medan jauh; per elemen tetap dipakai sebagai default yang aman, dan E0 menentukan apakah synthetic array yang lebih cepat cukup akurat. Nama API (`load_scene`, `PlanarArray`, `Transmitter`, `Receiver`, `PathSolver`, dsb.) diverifikasi di dokumentasi versi terpasang.

### 4.3 Anggaran komputasi untuk GPU 12 GB

- Jumlah titik penerima: (200 + 30 + 50) lintasan × 50 langkah × 3 entitas ≈ 42.000 titik. Dua sumber (RIS 64 elemen, BS 8 elemen).
- Batch penerima (`rx_batch_size`) mulai 256; turunkan jika kehabisan memori.
- `samples_per_src` mulai 1e5; naikkan sampai daya terima di sampel titik uji berubah < 0,5 dB.
- Jika CUDA kehabisan memori meskipun batch kecil, pakai varian LLVM (CPU) Dr.Jit untuk prakomputasi; lebih lambat tetapi tanpa batas VRAM.
- Jangan menjalankan prakomputasi ray tracing dan pelatihan PPO bersamaan di GPU yang sama. Pelatihan PPO dengan MLP kecil cukup di CPU.

### 4.4 Penyimpanan

```
data/channels/<scene_id>/<config_hash>.h5
  /static/G, /static/H, /static/Hc
  /meta/  (f_c, posisi dan orientasi BS/RIS, parameter RT, versi Sionna, hash config)
  /traj/<split>/<traj_id>/user_k/{pos, g, hd}
  /traj/<split>/<traj_id>/target_q/{pos, vel, in_roi, g, hd_tx, hd_rx}
```

Environment RL hanya membaca HDF5 dan tidak mengimpor Sionna. Karena itu semua yang dibutuhkannya ikut disimpan, termasuk `in_roi` (§2.3 memotong episode saat target keluar ROI) dan atribut `speed_mps` per target.

Penulisan **bisa dilanjutkan**: tiap grup lintasan baru ditandai `complete` setelah seluruh dataset-nya masuk, sehingga lintasan yang separuh tertulis terbaca sebagai hilang dan dihitung ulang, bukan terbaca sebagai data sah. Lintasan ke-*i* memakai RNG `(seed_split, i)` sehingga isinya tidak bergantung pada urutan pengerjaan.

### 4.5 Validasi ringan (E0)

Pada **scene ruang bebas** (tanpa gedung dan tanah, hanya jalur LoS):
1. **Uji implementasi:** daya terima hibrida untuk 3 profil fokus + 1 profil gradien dibandingkan dengan jumlah analitik per elemen Σ_m a_m e^{jφ_m} menggunakan Friis per hop dan pola elemen yang sama. Selisih harus < 0,1 dB (menguji konvensi fasa, orientasi, indeks elemen).
2. **Kalibrasi fisika:** bandingkan dengan model path loss RIS berbasis fisika dari literatur (mis. Tang dkk., 2021, IEEE TWC; **verifikasi rumusnya dari paper aslinya**). Catat selisih konstan sebagai `calibration_db`.
3. **Per elemen vs synthetic array:** selisih dB di grid ROI scene utama, untuk mengetahui apakah mode yang lebih cepat bisa dipakai.

---

## 5. Formulasi MDP

### 5.1 Struktur frame

Setiap langkah t:
1. Agen memilih aksi a_t dari observasi o_t.
2. RIS diatur ke φ_t; BS mengestimasi kanal efektif ĥ_{e,k} dari pilot.
3. BS menghitung **W**_c (RZF dari ĥ_{e,k}) dan **w**_s (dari estimasi posisi target).
4. Transmisi dan sensing; reward dihitung dari kanal sebenarnya.
5. Tracker memperbarui estimasi target; entitas bergerak.

Masalah ini sekuensial: iluminasi saat ini menentukan deteksi, deteksi menentukan estimasi posisi berikutnya, dan estimasi itu menentukan beam sensing berikutnya. Fasa RIS juga berubah inkremental.

### 5.2 Observasi parsial (PPO-PO)

| Komponen | Dimensi | Keterangan |
|---|---|---|
| ĥ_{e,k} di bawah φ_{t−1} | 2 N_t K = 32 | Re/Im, galat estimasi NMSE ε = −20 dB |
| SINR terlapor | K = 2 | dB, kuantisasi 1 dB, batas [−10, 40] |
| Estimasi posisi pengguna | 2K = 4 | Galat Gaussian σ_u = 0,5 m |
| Estimasi posisi dan kecepatan target | 4 | Output filter Kalman kecepatan-konstan |
| Flag deteksi dan SCNR terakhir | 2 | SCNR dB, batas [−20, 40] |
| Fasa RIS sebelumnya (cos, sin) | 2M = 128 | |
| Fraksi daya sensing sebelumnya | 1 | |
| P_max episode ini (ternormalisasi) | 1 | Karena P_max diacak saat pelatihan |

Total 174 per frame, ditumpuk 4 frame (696). Galat pengukuran posisi target bila terdeteksi: σ_pos = σ_ref · √(Γ_lin / SCNR_lin), σ_ref = 0,5 m, dibatasi 5 m. Bila tidak terdeteksi, tracker hanya memprediksi.

**PPO-FullCSI:** tambahkan **g**_k dan **g**_t (2M(K+Q) = 384) serta posisi sebenarnya.

Normalisasi observasi dengan running mean/std, dibekukan saat evaluasi.

### 5.3 Aksi (model-informed)

a_t = [Δφ ∈ [−1,1]^M, ρ_raw ∈ [−1,1], p_raw ∈ [−1,1]^K], dimensi M + 1 + K = 67.

- φ_t = (φ_{t−1} + κπ Δφ) mod 2π, κ = 0,1. Ablasi: absolut φ_t = π(Δφ + 1).

  **κ disapu atas {0,1; 0,25; 0,5}** (ditambahkan 2026-11-12, disetujui). Alasannya terukur, bukan dugaan: pada κ = 0,1 M1 dan M2 tidak pernah melewati pemenuhan SCNR 0,46 pada seed mana pun, sedangkan A1 — yang berbeda **hanya** pada mode fasa — mencapai pemenuhan 0,95–0,96 dengan rate yang sama. Jadi yang mengikat adalah seberapa cepat fasa boleh bergerak, bukan bobot reward λ. Dari fasa acak, menggeser satu elemen sejauh π butuh 1/κ langkah: 10 langkah pada κ = 0,1 (≈ 29% episode 35 langkah), 4 pada 0,25, 2 pada 0,5. Lihat `docs/LOG.md` 2026-11-11 (k).
- ρ = (ρ_raw + 1)/2: fraksi daya sensing.
- p = softmax(p_raw): bobot daya pengguna.
- **W**_c: arah RZF dari ĥ_{e,k} (regularisasi K σ_n²/P_max), kolom dinormalisasi lalu diskalakan √((1−ρ) P_max p_k).
- **w**_s = √(ρ P_max) · ĉ^*/‖ĉ‖, ĉ^T = ĝ_t^T Θ **G**, dengan ĝ_t dari model LoS gelombang sferis ke estimasi posisi target.

### 5.4 Reward

r_t = min_k R_k − λ · [Γ_dB − SCNR_dB]_+ / 10. (E9)

Hinge menghukum SCNR **di bawah** ambang. **λ = 10,0 tetap** (tidak disapu di versi ini).

λ dinaikkan dari 1,0 di Fase 3 setelah Gate 3 gagal (`docs/LOG.md` 2026-11-11 (h)). (E9) adalah pelonggaran dari kendala **keras** SCNR ≥ Γ pada (E8) §3.6, dan dengan λ = 1 pelonggaran itu terlalu longgar: kegagalan sensing total hanya berbiaya 3,3 bit/s/Hz sementara laju yang dipertaruhkan sekitar 11 bit/s/Hz, sehingga Oracle-GD pun memilih melanggar kendala di 15,5% snapshot. Sapuan pada B3 (200 snapshot val):

| λ | 1 | 3 | 10 | 30 | 100 |
|---|---|---|---|---|---|
| fraksi SCNR ≥ Γ | 0,845 | 0,995 | **1,000** | 1,000 | 1,000 |
| rate minimum rata-rata | 11,47 | 11,57 | **11,63** | 11,64 | 11,58 |

Laju **tidak** turun saat λ naik — memenuhi kendala sensing di geometri ini praktis gratis, sehingga λ = 1 bukan titik kompromi melainkan sekadar bobot yang terlalu kecil untuk menegakkan kendala yang sudah dinyatakan (E8).

### 5.5 Episode

- `reset()`: ambil lintasan dari split aktif; acak P_max dari 20–40 dBm (train) atau pakai nilai tetap (eval); φ_0 acak; tracker diinisialisasi dari posisi awal + noise.
- Truncated pada T = 50 atau saat target keluar ROI. γ = 0,95.

**Pengacakan P_max dan kecepatan saat pelatihan** membuat satu agen bisa dievaluasi di berbagai nilai tanpa latih ulang. Ini menghemat waktu untuk E4.

---

## 6. Metode

### 6.1 Agen DRL (Stable-Baselines3)

| ID | Metode | Observasi |
|---|---|---|
| M1 | **PPO-PO** (utama) | Parsial + frame-stack 4 |
| M2 | PPO-FullCSI | Penuh + frame-stack 4 |
| A1 | PPO-PO-absolute (ablasi) | Seperti M1, fasa absolut |

Hiperparameter: lr 3e-4, γ 0,95, GAE λ 0,95, clip 0,2, n_steps 512 × 8 env, batch 256, 10 epoch, ent_coef 0, MLP [256, 256], 1e6 langkah (2e6 untuk E4b, lihat §7). Tuning ringan hanya di val, lalu dibekukan. **Pelatihan di CPU** (MLP kecil, env NumPy).

**Model yang dilaporkan adalah checkpoint dengan reward val terbaik**, bukan kebijakan pada langkah terakhir (ditambahkan 2026-11-12, disetujui). Val dievaluasi tiap 50 ribu langkah dan statistik `VecNormalize` disimpan bersama tiap checkpoint, sehingga kebijakan terpilih dapat dimuat ulang persis — terverifikasi sampai 0,0e+00. Ini bukan kehalusan: ketiga seed A1 mencapai puncaknya di 350–450 ribu langkah lalu **ambruk**, pemenuhan SCNR 0,95 → 0,55 **tanpa kehilangan rate sedikit pun**. Kebijakan akhir karena itu memang lebih buruk, bukan hasil tukar-tambah, dan melaporkannya akan menempatkan A1 2,7 poin di bawah capaiannya. Pemilihan dilakukan di val dan test tetap tidak tersentuh sampai §7 E3.

### 6.2 Baseline

| ID | Baseline | Informasi |
|---|---|---|
| B1 | **Random**: fasa acak per langkah, ρ terbaik dari grid val | Sama dengan M1 |
| B2 | **Geometric**: φ_m = −arg( Σ_i ω_i [ĝ_i]_m [**G ā**]_m ), ĝ_i model LoS ke estimasi posisi pengguna dan target, **ā** vektor singular kanan utama **G**; ω_i dan ρ dari grid val | Sama dengan M1 |
| B3 | **Oracle-GD**: Adam per langkah atas φ, ρ, p dengan struktur precoder yang sama; objektif softmin(R) − λ·softplus-hinge(SCNR); 300 iterasi, 4 restart (geometris + acak) | CSI dan posisi sempurna |
| B4 | **Oracle-GD-stale(D)**: B3 setiap D ∈ {5, 10} langkah, ditahan di antaranya | CSI sempurna tetapi usang |

---

## 7. Eksperimen

Prioritas: **P1** wajib untuk paper, **P2** penting tetapi murah, **P3** hanya jika waktu tersisa.

| ID | Prio | Desain | Output |
|---|---|---|---|
| E0 | P1 | Validasi ringan §4.5 | F3, T1 |
| E1 | P1 | Peta cakupan BS langsung vs lewat RIS (profil fokus terbaik per titik) dan peta SNR radar ideal di ROI, P_max ∈ {20, 30, 40} dBm. Melaporkan juga **penguatan kaskade RIS atas jalur langsung**, yang menjadi kriteria Gate 1 | F1, F2 |
| E2 | P1 | Kurva pelatihan M1, M2, A1, masing-masing 3 seed | F4 |
| E3 | P1 | Semua metode di set test: 50 lintasan × 3 seed noise = 150 episode, P_max = 30 dBm. Metrik: rata-rata dan CDF rate minimum, pemenuhan SCNR (% langkah ≥ Γ), durasi track, galat posisi tracker | T2, F5, F6 |
| E4a | P2 | Agen dari E2 dievaluasi pada P_max ∈ {20, 25, 30, 35, 40} dBm dan kelompok kecepatan {1–3, 4–7, 8–10} m/s, tanpa latih ulang | F7 |
| E4b | P1 | Latih ulang M1 untuk Γ ∈ {10, 16} dB (3 seed, **2e6 langkah**; Γ = 13 dari E2), evaluasi semua metode untuk menggambar trade-off rate minimum vs pemenuhan SCNR | F8 |
| E5 | P2 | Ablasi fasa inkremental vs absolut (dari E2), **plus sapuan κ ∈ {0,1; 0,25; 0,5} untuk M1 (3 seed)** — mengubah ablasi dari biner menjadi kuantitatif | T3 |
| E6 | P2 | Waktu inferensi per keputusan M1 vs waktu per langkah B3; waktu prakomputasi ray tracing; waktu pelatihan | T3 |
| E7 | P3 | Ketahanan tanpa latih ulang: NMSE ε ∈ {−30, −20, −10} dB, σ_u ∈ {0,1, 0,5, 2} m | F9 |
| E8 | P3 | Uji di scene kota bawaan tanpa latih ulang | Teks |

Jumlah pelatihan: (M1, M2, A1) × 3 + M1(Γ = 10, 16) × 3 + M1(κ = 0,25; 0,5) × 3 = **21 run** (15 × 1e6 + 6 × 2e6 langkah).

---

## 8. Parameter Default

| Parameter | Nilai |
|---|---|
| f_c, B, NF | 3,5 GHz (λ_c ≈ 8,57 cm), 20 MHz, 7 dB → σ_n² ≈ −94 dBm |
| N_t = N_r | 8 (ULA horizontal λ/2), panel terpisah 0,5 m |
| M | 64 (8 × 8) |
| P_max | 30 dBm (eval); acak 20–40 dBm (train) |
| K, Q | 2, 1 |
| σ_rcs | 1 m² |
| L, ξ, Γ, β_s | 4096, 0,01, 13 dB, 1 |
| Δt, T, κ, λ | 0,1 s, 50, 0,1 (disapu {0,1; 0,25; 0,5}, §5.3), **10,0** (λ ditetapkan di Fase 3, §5.4) |
| ε, σ_u, σ_ref, σ_max | −20 dB, 0,5 m, 0,5 m, 5 m |
| Ray tracing | max_depth **5**, samples_per_src 1e5, max_num_paths_per_src 1e6 (max_paths_total 8e6), spekular + difus + difraksi, per elemen — semuanya diukur sampai konvergen, §4.2 |
| Geometri | jalan 6 m; BS (−16, −1, 10); RIS (2,9, 4, 6); d(BS–RIS) 20,0 m; ROI y ∈ [14, 34], 440 titik @ 0,5 m |
| Lintasan | 200 / 30 / 50 |
| Seed pelatihan | 3 |
| Langkah pelatihan | 1e6 (E2, sapuan κ); 2e6 (E4b, karena pada 1e6 kurva val Γ = 10 dan 16 masih menanjak) |
| Model yang dilaporkan | checkpoint dengan reward val terbaik (§6.1) |

Semua nilai di `configs/base.yaml`.

---

## 9. Protokol Statistik

- 3 seed pelatihan per konfigurasi; tiap seed dievaluasi pada 150 episode test yang sama.
- Laporkan rata-rata ± interval kepercayaan 95% (bootstrap atas episode, dikelompokkan per seed). Kurva pelatihan: rata-rata ± std antar-seed.
- Uji beda utama M1 vs B2 dan M1 vs B4: Welch t-test atas rata-rata per seed, plus ukuran efek. Nyatakan bahwa n = 3 seed membatasi daya uji.
- Hasil disimpan sebagai Parquet + salinan config + git commit; gambar dibuat ulang dari file hasil.

---

## 10. Risiko dan Mitigasi

| Risiko | Gejala | Mitigasi | Kapan dicek |
|---|---|---|---|
| SNR radar lewat RIS di bawah Γ | Peta E1 atau Oracle-GD gagal | Pendekkan BS–RIS atau ROI, naikkan L ke 16384, turunkan Γ ke 10 dB (catat alasannya) | Gate 1, Gate 3 |
| VRAM habis saat ray tracing | Error OOM | Kecilkan `rx_batch_size` dan `samples_per_src`; varian LLVM | Fase 2 |
| PPO tidak mengalahkan Geometric | Reward datar atau di bawah B2 | Inisialisasi φ dari B2, kurikulum (target diam → bergerak), normalisasi reward, κ lebih kecil | Titik keputusan minggu 5 |
| Waktu habis | Jadwal mundur | Potong P3 lalu P2 (§7) | Tiap akhir minggu |
| Kode menyimpang dari dokumen | Hasil tak cocok dengan paper | Tes unit per persamaan; cek silang di Fase 7 | Tiap gate |

---

## 11. Gambar dan Tabel Paper

| ID | Isi |
|---|---|
| F1 | Tampak atas scene: BS, RIS, ROI, contoh lintasan |
| F2 | Peta SNR komunikasi dan radar ideal: BS langsung vs lewat RIS |
| F3 | Validasi kanal hibrida vs analitik |
| F4 | Kurva pelatihan M1, M2, A1 |
| F5 | CDF rate minimum semua metode |
| F6 | Contoh episode: SCNR terhadap waktu, ambang Γ, flag deteksi, galat posisi |
| F7 | Kinerja vs P_max dan kecepatan target |
| F8 | Trade-off rate minimum vs pemenuhan SCNR (Γ = 10, 13, 16 dB) |
| T1 | Galat validasi kanal |
| T2 | Hasil utama set test |
| T3 | Ablasi dan biaya komputasi |

---

## 12. Referensi Kunci

- Aït Aoudia, F. dkk. (2025). Sionna RT: Technical Report. arXiv:2504.21719.
- Hoydis, J. dkk. (2023). Sionna RT: Differentiable Ray Tracing for Radio Propagation Modeling. arXiv:2303.11103.
- Liu, R. dkk. (2026). Clutter-Aware Integrated Sensing and Communication: Models, Methods, and Future Directions. arXiv:2602.10537.
- Lemić, F. dkk. (2026). Unified Evaluation Methodology for AI-Native Integrated Sensing and Communication. arXiv:2607.14806.
- Güneşer, A. E. dkk. (2025). RIS Optimization Algorithms for Urban Wireless Scenarios in Sionna RT. arXiv:2501.05817.
- Tarafder dkk. (2026). Digital-Twin Empowered DRL for Site-Specific Radio Resource Management. arXiv:2602.03801.
- Schulman, J. dkk. (2017). Proximal Policy Optimization Algorithms. arXiv:1707.06347.
- Tang, W. dkk. (2021). Wireless Communications With Reconfigurable Intelligent Surface: Path Loss Modeling and Experimental Measurement. IEEE Transactions on Wireless Communications. **Verifikasi rincian bibliografi dan rumus sebelum dikutip.**

Tambahkan referensi persamaan radar bistatik dan aproksimasi Albersheim setelah diverifikasi.
