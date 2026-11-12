# Catatan Keputusan dan Masalah

Entri terbaru di atas. Setiap entri bertanggal dan menyebut fase/gate terkait.

---

## 2026-11-11 (e) — Kriteria Gate 1 yang saya usulkan ternyata bisa digame

Koreksi terhadap entri (d), ditemukan saat membuat gambar F2 apel-ke-apel.

### Cacatnya

Kriteria yang dipasang di (d) membandingkan kaskade RIS terhadap jalur langsung
**pada precoder `a_bar` yang sama**, dan memberi +8,8 dB. Tetapi `a_bar` adalah
vektor singular kanan utama **G**, yaitu precoder yang dioptimalkan untuk
mencapai RIS — dan karenanya melumpuhkan jalur langsung:

| Komunikasi @30 dBm, median | SNR |
|---|---|
| langsung, precoder `a_bar` | 37,6 dB |
| langsung, MRT (kasus terbaik tanpa RIS) | **51,3 dB** |
| lewat RIS, precoder `a_bar` | 46,8 dB |

Jadi +8,8 dB sebagian adalah artefak pilihan precoder: kriterianya bisa
"dimenangkan" dengan memilih precoder yang menguntungkan RIS. Lebih buruk lagi,
dengan MRT **sistem tanpa RIS sama sekali (51,3 dB) mengungguli peta E1 lewat
RIS (46,8 dB)**.

### Ukuran yang benar

Pertanyaan tingkat sistem adalah: apakah BS ber-RIS mengungguli BS tanpa RIS
yang sama-sama beamforming optimal? Yaitu MRT pada kanal efektif (E2)
`h_e = h_d + G^T (e^{j phi} . g)` lawan MRT pada `h_d`:

> **MRT dengan RIS vs MRT tanpa RIS: median +1,4 dB, p10 +0,0 dB,
> RIS menang di 91,1% ROI.**

Kriteria Gate 1 dan `configs/base.yaml` diubah memakai ukuran ini. Verdict
Gate 1 tidak berubah (0,911 >= 0,90), tetapi angkanya kini jujur.

### Artinya

Premis masih lemah. RIS hanya menambah **~1,4 dB** pada link komunikasi, dan di
sepersepuluh ROI terlemah tidak menambah apa pun (p10 +0,0 dB). Penyebabnya
sama seperti sebelumnya dan belum hilang: ROI ini **tanpa garis pandang tetapi
tidak kekurangan daya**, karena kanyon mengantarkan daya multi-pantul yang kuat.

Ambang 0 dB adalah bar yang lemah — penguatan 0,1 dB pun dihitung menang.
Menaikkannya (mis. >= 6 dB di >= 80% ROI) akan membuat geometri ini GAGAL.

**Menunggu keputusan**, karena ini menentukan apakah Fase 2 layak dimulai:

* (a) Naikkan ambang ke nilai yang bermakna dan cari geometri yang memenuhinya.
  Sapuan sejauh ini (lebar jalan 10-20 m, posisi RIS dan BS) belum menemukan
  satu pun yang memberi penguatan MRT besar; mungkin perlu scene yang ROI-nya
  benar-benar terkurung (bukan kanyon lurus).
* (b) Terima ~1,4 dB dan ubah pembingkaian: kontribusi paper bergeser dari
  "RIS memungkinkan cakupan NLoS" menjadi "DRL mengelola trade-off
  komunikasi-sensing", dengan RIS sebagai derajat kebebasan untuk SENSING
  (di mana perannya jauh lebih besar: SCNR RIS-saja median 39 dB) alih-alih
  untuk cakupan komunikasi.
* (c) Turunkan daya atau perbesar ROI sampai jalur langsung benar-benar lemah.

Catatan untuk (b): kriteria radar Gate 1 sebelumnya terpenuhi 99,5% oleh jalur
langsung saja, jadi klaim "RIS dibutuhkan untuk sensing" juga perlu diuji
dengan ukuran MRT-lawan-MRT yang sama sebelum dipakai.

---


## 2026-11-11 (d) — Geometri dioptimalkan ulang; kriteria Gate 1 baru

Lanjutan entri (c). Dua keputusan disetujui: ukur dulu BS yang lebih jauh, dan
tambahkan kriteria "RIS mengungguli jalur langsung" ke Gate 1.

### Hipotesis saya SALAH: menjauhkan BS memperburuk premis

Sapuan lebar jalan (`results/e1/761053d10851/width_tradeoff.py`), tiap lebar
memakai penempatan layak dengan d(BS-RIS) terkecil:

| lebar | d(BS-RIS) | penguatan RIS median | p10 | langsung > RIS | radar OK (RIS saja) |
|---|---|---|---|---|---|
| **10 m** | 19,6 | **+6,4 dB** | -0,4 | 13,1% | 1,000 |
| 12 m | 24,8 | +3,4 | -3,0 | 27,5% | 0,999 |
| 14 m | 30,2 | -2,6 | -8,4 | 65,1% | 0,990 |
| 16 m | 36,4 | -3,6 | -9,7 | 76,2% | 0,975 |
| 20 m | 50,6 | -5,3 | -11,9 | 82,5% | 0,887 |

Dugaan saya — berdasarkan v0.1, di mana BS 72 m memberi penguatan besar —
adalah menjauhkan BS akan memulihkan premis. Terukur sebaliknya. Kanyon yang
lebih lebar membuat jalur langsung butuh **lebih sedikit** pantulan untuk
mencapai ROI, sementara kaskade RIS kehilangan hop BS-RIS yang memanjang
(19,6 -> 50,6 m, sekitar 8 dB). Kriteria radar juga ikut memburuk, jadi jalan
lebar kalah di kedua sumbu sekaligus. Opsi "jauhkan BS" dibatalkan.

### Objektif pencarian penempatan ternyata keliru

Baris 10 m di atas memberi +6,4 dB, sedangkan geometri yang sudah ditulis ke
config memberi +2,1 dB — padahal keduanya "jalan 10 m, BS ~19,6 m". Bedanya
hanya RIS bergeser 2 m. Sensitivitas sebesar itu menunjukkan
`place_geometry.py` meminimalkan besaran yang salah: jarak BS-RIS, bukan
penguatan RIS.

Pencarian diulang dengan objektif yang benar
(`results/e1/761053d10851/opt_placement.py`):

| lebar | y_RIS | x_BS | d | sudut dari normal | penguatan median | langsung > RIS |
|---|---|---|---|---|---|---|
| **10** | **6,0** | **-13,0** | 20,4 | 52,4 deg | **+8,8 dB** | **8,4%** |
| 10 | 7,0 | -11,0 | 19,2 | 55,1 | +3,6 | 27,8% |
| 10 | 8,0 | -11,0 | 19,7 | 56,3 | +2,2 | 38,0% |
| 10 | 13,0 | -9,0 | 21,6 | 63,2 | -9,5 | 95,3% |

RIS harus **serapat mungkin ke sudut**: sudut datang dari normal RIS yang
menentukan, bukan jarak. Geometri final: BS `[-13, -3, 10]`, RIS `[4.9, 6, 6]`,
normal `[-0.909, 0.417, -0.015]`, ROI `y in [16, 36]`, d(BS-RIS) 20,4 m.

### Kriteria Gate 1 baru

Ditambahkan ke `docs/TASKS.md`, §7 `docs/EXPERIMENT_DESIGN.md`, dan
`configs/base.yaml` (blok `gate1:`, agar tidak ada angka ambang di kode):

> Penguatan kaskade RIS atas jalur langsung > 0 dB di >= 90% ROI.

Ambang 0 dB adalah pernyataan minimal premis: jalur RIS harus mengungguli jalur
langsung di hampir seluruh ROI. Dengan kriteria ini, geometri lama (38% titik
dimenangkan jalur langsung, cakupan 0,62) akan **GAGAL** — persis yang
diinginkan.

### Gate 1 ULANG — LOLOS (enam dari enam)

Hasil di `results/e1/761053d10851/`, config hash `761053d10851`.

| Kriteria | Hasil |
|---|---|
| BS->RIS LoS | PASS (True) |
| BS->ROI NLoS di 100% titik | PASS (0,0000) |
| SNR komunikasi lewat RIS > 10 dB di >= 90% | PASS (1,000) |
| SNR radar ideal >= Gamma+3 di >= 80% | PASS (1,000) |
| **Penguatan RIS > 0 dB di >= 90%** | **PASS (0,914)** |
| Oracle LoS setara PathSolver(depth=0) | PASS (0/64) |

Median pada 30 dBm: SNR komunikasi 46,8 dB, SCNR 43,7 dB, penguatan RIS
+8,8 dB. Seluruh E1 di bawah 5 detik.

**Marginnya tipis dan harus dinyatakan apa adanya:** kriteria baru lolos di
0,914 terhadap target 0,90, dan p10 penguatan hanya +0,4 dB. Artinya di
sepersepuluh ROI terlemah, jalur RIS dan jalur langsung praktis setara. Premis
berdiri, tetapi tidak dengan margin lega; bila Fase 2 mengubah apa pun yang
menyentuh kanal (uji konvergensi `samples_per_src` atau `max_num_paths_per_src`),
kriteria ini harus dicek ulang, bukan dianggap aman.

---


## 2026-11-11 (c) — Migrasi ke v0.2-lean; Gate 0 dan Gate 1 LOLOS, satu temuan terbuka

Paket `ris-isac-drl` v0.2-lean diterima dan menggantikan v0.1. Migrasi dilakukan
**di tempat** agar riwayat git dan kode `src/` yang masih berlaku tetap terpakai:
`README.md`, `CLAUDE.md`, `docs/EXPERIMENT_DESIGN.md`, `docs/TASKS.md`,
`configs/base.yaml`, `.gitignore` diganti; `scripts/link_budget.py` ditambahkan;
`configs/e1_depth6.yaml` dan `envs/requirements-v019.txt` dihapus;
`envs/requirements-main.txt` menjadi `envs/requirements.txt`.

Perubahan yang paling berpengaruh: **M = 64 tetap** (bukan sapuan sampai 256) dan
**tanpa environment Sionna 0.19.2**. Keduanya melarutkan sebagian besar tekanan
VRAM yang dibahas sebelumnya, karena beban terberat dulu ada di M = 256
per-elemen.

### Dua bug v0.1 yang terbawa ke paket baru

1. **Notasi eksponen YAML.** `base.yaml` v0.2 kembali memakai `3.5e9`, `20.0e6`,
   `1.0e5`, `1.0e6` tanpa tanda, sehingga ter-parse sebagai **string**. Guard di
   `config.py` (warisan v0.1) menangkapnya saat skrip pertama dijalankan. Semua
   diubah ke bentuk bertanda; nilainya tidak berubah.
2. **Hamburan difus mati.** `ITURadioMaterial` memakai default
   `scattering_coefficient = 0,0`, sehingga `ray_tracing.diffuse_reflection: true`
   dan §4.2 ("spekular + difus + difraksi") tidak berefek apa pun. Ditetapkan
   S = 0,3 untuk beton, sesuai keputusan yang sudah disetujui sebelumnya.

Selain itu `scene.synthetic_l` (geometri scene) tidak ada di config v0.2 dan
ditambahkan, serta `ray_tracing.max_num_paths_per_src` yang dibutuhkan
`rt_extract.py`.

### Gate 0 — LOLOS (23 PASS, 0 WARN, 0 FAIL)

`scripts/check_env.py` ditulis ulang untuk environment tunggal (versi lama
berisi 376 baris logika dua-environment yang tidak berlaku lagi).

| | |
|---|---|
| Python | 3.12.16 |
| sionna / sionna-rt | 2.2.0 |
| drjit / mitsuba | 1.5.0 / 3.9.1 |
| torch | 2.14.1+cu130 |
| GPU | RTX 4070, **VRAM bebas 10,85 GiB dari 11,99 GiB** |
| Backend Dr.Jit | CUDA |
| Varian Mitsuba | `cuda_ad_mono_polarized` |
| Muat scene munich | 11 objek, 0,66 s |
| Jalur 1 Tx-Rx | 9 jalur, 0,05 s |

### Fase 1 — geometri ditentukan dengan pengukuran, bukan pilihan tangan

§2.1 meminta tiga hal yang saling tarik: BS-RIS ~ 20 m, ROI 10-30 m dari RIS,
dan 0% LoS BS->ROI. Bayangan sudut gedung baru menutupi seluruh lebar jalan B
bila BS cukup jauh ke barat:

    u >= 2a/(s-1),  a = setengah lebar jalan,
    s = (y_dekat - y_BS)/(a - y_BS),  u = jarak BS di barat tepi blok.

Karena d(BS-RIS) ~ sqrt((2a+u)^2 + dy^2), lebar jalan adalah parameter yang
mendamaikan ketiganya — dan §2.2 tidak menetapkannya. Disapu dengan
`scripts/place_geometry.py` (oracle LoS `ray_test` pada scene sebenarnya):

| lebar jalan | d(BS-RIS) minimum dengan 0% LoS |
|---|---|
| **10 m** | **19,7 m** |
| 12 m | 24,8 m |
| 14 m | 30,2 m |
| 16 m | 36,4 m |
| 20 m | 50,6 m |

Jalan 20 m memaksa BS 50,6 m dari RIS; jalan 10 m memberi 19,7 m, yaitu "~20 m"
yang diminta §2.1. Dipilih **10 m** (2 lajur 3 m + trotoar 2 m).

Catatan metodologis: pencarian pertama memakai grid 1,0 m dan memberi
d = 18,7 m, tetapi pada grid E1 yang 0,5 m masih tersisa 1 titik ber-LoS dari
640. Pencarian diulang pada 0,5 m; koordinat final memakai grid yang sama
dengan gate-nya.

Koordinat final: BS `[-11, -3, 10]`, RIS `[4.9, 8, 6]`, normal
`[-0.936, 0.353, -0.010]` (BS dan pusat ROI masing-masing 56,3 deg dari normal),
ROI `x in [-4, 4]`, `y in [18, 38]`, grid 0,5 m = 640 titik.

### Anggaran jalur dan VRAM — batch BUKAN tuas untuk buffer ini

`max_num_paths_per_src = 1e6` gagal OOM dengan alokasi **tepat 1 GiB**, dan
angka itu **tidak berubah** saat `rx_batch_size` diturunkan 256 -> 64. Buffer
image-method berukuran `max_num_paths_per_src * jumlah_sumber * 16 B`
(1e6 x 64 x 16 = 1,07e9), dan ada beberapa buffer sekaligus.

Ini mengoreksi perkiraan sebelumnya bahwa VRAM hanya menukar waktu lewat batch:
untuk buffer ini batch tidak berpengaruh sama sekali. Dipakai 1e5 (102 MiB per
buffer). `release_gpu_memory()` ditambahkan di `rt_extract.py` dan dipanggil
antar-pemanggilan RT.

**Masih terbuka:** konvergensi `max_num_paths_per_src` belum diuji pada geometri
baru. Pada v0.1 nilai terlalu rendah menjatuhkan daya 28 dB tanpa error apa pun.
Uji ini dijadwalkan Fase 2 bersama uji `samples_per_src` (< 0,5 dB).

### Gate 1 — LOLOS

Hasil di `results/e1/8728d05f8051/`. eta = 32,3 dB (cocok §3.4), L = 4096,
Gamma = 13 dB, M = 64. `scripts/link_budget.py` direproduksi terhadap tabel
§3.8 (20 m / 64 / 10 m: 46,4 dan 37,3 dB vs 46 dan 37 di dokumen).

| Kriteria | Hasil |
|---|---|
| BS->RIS LoS | PASS (True) |
| BS->ROI NLoS di 100% titik | PASS (fraksi 0,0000) |
| P=30 dBm: SNR komunikasi lewat RIS > 10 dB di >= 90% | PASS (**1,000**) |
| P=30 dBm: SNR radar ideal >= Gamma+3 di >= 80% | PASS (**1,000**) |
| Oracle LoS setara PathSolver(depth=0) | PASS (0/64) |

Median pada 30 dBm: SNR komunikasi 48,0 dB, SCNR 46,9 dB. Waktu seluruh E1
di bawah 10 detik.

### TEMUAN TERBUKA — RIS nyaris tidak diperlukan di geometri ini

Gate 1 lolos, tetapi **tidak satu pun kriterianya membandingkan RIS terhadap
jalur langsung**. Pemisahan kontribusi
(`results/e1/8728d05f8051/e1_split_diagnostic.py`):

| Komunikasi (SNR dB) | p10 | median | p90 |
|---|---|---|---|
| langsung (MRT) | 49,8 | **53,3** | 61,9 |
| langsung (precoder a-bar) | 33,9 | 43,7 | 52,7 |
| RIS saja (kaskade) | 42,7 | **46,6** | 50,2 |

Penguatan RIS atas jalur langsung hanya **+2,1 dB median**, p10 **-4,4 dB**, dan
di **38,4% titik jalur langsung lebih kuat**.

| SCNR ideal (dB) | p10 | median | p90 |
|---|---|---|---|
| langsung saja | 28,9 | 42,8 | 58,5 |
| RIS saja | 29,7 | 37,6 | 44,9 |
| gabungan (dipakai E1) | 37,2 | 47,0 | 60,4 |

Yang paling menohok: **kriteria radar Gate 1 terpenuhi di 99,5% ROI oleh jalur
langsung saja**, tanpa RIS sama sekali.

Penyebabnya struktural, bukan bug. §3.8 mendorong BS-RIS ke ~20 m agar link
budget sensing (empat hop) memadai; tetapi dengan jalan 10 m, BS 19,7 m dari RIS
berarti BS duduk tepat di mulut persimpangan, sehingga jalur multi-pantul kanyon
ke ROI tetap kuat meski ROI lolos uji LoS. ROI di sini **tanpa garis pandang,
tetapi tidak kekurangan daya** — persis kelas masalah yang ditemukan di v0.1,
kali ini diperkuat oleh jalan sempit dan jarak pendek.

Ada ketegangan tiga arah: SNR radar menuntut BS **dekat**, premis NLoS menuntut
BS **jauh**, dan Gate 1 menuntut keduanya. Margin yang tersedia besar — SCNR
median 47 dB terhadap ambang 16 dB — sehingga menjauhkan BS mungkin masih
muat, tetapi harus diukur: eko turun 40 log10(d1), jadi 20 -> 50 m memakan
sekitar 16 dB dan p10 RIS-saja (29,7 dB) akan mendekati ambang.

**Menunggu keputusan** (titik keputusan akhir minggu 1 di `docs/TASKS.md`):

* (a) Terima dan ubah pembingkaian paper menjadi "RIS menambah ~2 dB". Lemah:
  dengan jalur langsung menang di 38,4% titik, daya ungkit aksi agen kecil dan
  nilai DRL-nya dipertanyakan.
* (b) Jauhkan BS (jalan lebih lebar, mis. 16-20 m sehingga BS 36-51 m dari RIS).
  Memulihkan premis NLoS; harus dicek ulang terhadap kriteria radar Gate 1.
* (c) Tambahkan kriteria "penguatan RIS atas jalur langsung" ke Gate 1 agar
  kegagalan premis tidak lolos diam-diam lagi, apa pun pilihan (a)/(b).

Rekomendasi: (c) wajib, lalu (b) diukur sebelum memilih (a).

### Lain-lain

* `src/risisac/system/signal_model.py` dibuat: `eta_factor` (E6),
  `focus_phases`, `cascaded_coefficient`, `ideal_scnr` (E7 dengan rho = 1 tanpa
  clutter). eta terukur 32,3 dB, cocok dengan §3.4.
* Varian scene **ruang bebas** ditambahkan (`load_free_space`,
  `load_scene_from_config`) untuk E0 Fase 2; terverifikasi memuat 0 objek.
* Fasad berundak v0.1 dimatikan (setback dan variasi tinggi = 0) agar sesuai
  §2.2 "gedung kotak"; pada v0.1 terbukti tidak berpengaruh setelah kedalaman
  konvergen.
* `pytest -q`: **24 lolos**.

---

## 2026-11-11 (b) — Hamburan difus ternyata mati; premis ROI sebagian besar pulih

Lanjutan entri 2026-11-11 (a). Tiga keputusan disetujui: (A) `max_depth` 5,
(B) rancang ulang geometri ROI, (C) aktifkan hamburan difus sesuai §4.2.

### 1. "ROI di balik tikungan kedua" TIDAK bisa dibangun — diukur

Satu RIS harus melihat BS **dan** ROI. Diuji pada scene sekarang: RIS di sudut
pertama (9,9; 12; 6) terhadap 11 titik di lengan jalan kedua (x, 60) →
**LoS 0/11**. Dinaikkan ke z = 25 m (di atas atap) → tetap **0/11**, karena
blok NE menghalangi sampai x = 90.

Jadi opsi (B) sebagaimana dirumuskan mustahil tanpa RIS kedua atau memindahkan
RIS ke sudut kedua (yang mematikan LoS ke BS). Tidak dilaksanakan.

### 2. Penyebab utama bukan geometri, melainkan hamburan difus yang mati

`ITURadioMaterial` memakai default `scattering_coefficient = 0,0`, sehingga
`ray_tracing.diffuse_reflection: true` **tidak berefek apa pun** — ini juga
menjelaskan mengapa uji mekanisme 2026-11-10 ("mematikan difus tidak mengubah
apa pun") memberi hasil nol.

Mengaktifkan S = 0,3 (W=20, y0=35, depth 5, M=144):

| | h_d median | RIS median | penguatan median | langsung > RIS |
|---|---|---|---|---|
| S = 0,0 | -98,6 | -85,1 | +11,9 dB | 2,1% |
| **S = 0,3** | **-109,3** | -86,7 | **+22,5 dB** | **0,0%** |

Jalur langsung (±5 pantulan) kehilangan **10,7 dB**, jalur RIS (pada dasarnya
LoS) hanya 1,6 dB. Perkiraan kasar (1 - S²) per pantulan ≈ 2 dB jauh meleset;
ruginya berlipat sekaligus menghilangkan daya dari rantai spekular.

Tinggi BS **bukan** tuas: 18 m memberi +19,4 dB, lebih buruk dari 10 m.

### 3. Jarak ROI dari sudut — yang bergerak hanya ekornya

S = 0,3, depth 5, lebar jalan 20 m, panjang ROI 50 m:

| y0 | jarak dari sudut | penguatan p10 | penguatan median | langsung > RIS |
|---|---|---|---|---|
| 20 (§2.1 sekarang) | 10-60 m | -1,4 dB | +22,5 dB | 13,6% |
| 25 | 15-65 m | +6,7 dB | +22,2 dB | 5,7% |
| **30** | **20-70 m** | +5,5 dB | +22,4 dB | **0,7%** |
| 35 | 25-75 m | +6,3 dB | +22,6 dB | 0,0% |

Median praktis datar; yang membaik adalah ekor dekat sudut. y0 = 30 sudah
menurunkan "langsung > RIS" dari 13,6% ke 0,7% dengan perubahan §2.1 jauh
lebih kecil daripada rancang ulang topologi.

**Belum diterapkan** — `scene.roi.polygon` dan §2.1 masih y0 = 20.

### 4. `max_num_paths_per_src = 1e5` memotong jalur begitu hamburan aktif

Link langsung saja (8 sumber BS), y0 = 30, S = 0,3:

| depth | samples | max_paths | median h_d |
|---|---|---|---|
| 5 | 1e6 | 1e5 | -108,8 |
| 5 | **1e7** | **1e5** | **-137,1** |
| 5 | 1e7 | 1e6 | -106,7 |
| 6 | 1e7 | 1e6 | -108,1 |
| 7 | 1e7 | 1e6 | -108,7 |

Menaikkan sampel 1e6 → 1e7 sambil menahan tutup di 1e5 **menjatuhkan hasil
28 dB**. Itu pemotongan jalur, bukan fisika: makin banyak sampel menemukan
makin banyak jalur difus, lalu tutup membuang sebagian termasuk yang kuat.

Dua akibat:

* Penurunan monoton h_d terhadap kedalaman (-107,5 → -110,3 dari depth 5 ke 6)
  yang sempat dicurigai sebagai pembatalan koheren **adalah artefak tutup ini**.
  Dengan anggaran memadai (1e6) depth 5/6/7 = -106,7 / -108,1 / -108,7, yaitu
  konvergen dalam 2 dB. **`max_depth: 5` dikonfirmasi.**
* Butir 3 entri 2026-11-10 ("menurunkan `max_num_paths_per_src` memotong jalur —
  risiko bias diam") kini **terbukti**, bukan lagi dugaan. Nilai 1e5 dipilih
  karena batas VRAM, bukan konvergensi.

Peringanan: pada `samples_per_src = 1e6` yang memang dikonfigurasi, tutup 1e5
hanya meleset ~2 dB (-108,8 vs -106,7), jadi angka penguatan +22 dB di butir 2
dan 3 tetap berlaku.

### 5. TERBUKA — apakah link RIS ikut terbias?

Link RIS memakai M sumber per-elemen, dan justru di situ 1e5 dipilih karena
VRAM. Uji M=144 dengan hamburan aktif **belum selesai**: proses dihentikan
sistem karena memori menipis setelah satu baris (depth 3, 1e5 → median
-85,6 dB). Pembanding 2e5 dan 5e5 belum ada.

Ini harus dituntaskan sebelum Fase 2, karena bila link RIS ikut terpotong maka
seluruh basis data kanal Fase 2 terbias, dan tutup tidak bisa dinaikkan tanpa
menabrak batas 12 GB.

### 6. Yang sudah diterapkan di repo

* `configs/base.yaml`: `max_depth: 3 → 5`; `scene.synthetic_l.scattering_coefficient: 0.3`.
* `src/risisac/scene/synthetic_l.py`: `SyntheticLSpec.scattering_coefficient`,
  diteruskan ke BSDF. Pola hamburan **tidak** ditulis ke XML — `RadioMaterial`
  meneruskan tiap properti sisa sebagai kwarg ke factory pola, sehingga
  `scattering_pattern` melempar `LambertianPattern() takes no arguments`
  (`radio_material.py:164`). Lambertian memang default.
* `docs/EXPERIMENT_DESIGN.md` §4.2 dan tabel §8 diperbarui bersamaan.
* `tests/test_scene.py`: tes blok diperbaiki (fasad berundak memecah blok
  menjadi inti + segmen, jadi yang diuji awalan nama), plus tes baru bahwa
  `scattering_coefficient` benar-benar sampai ke XML dan `scattering_pattern`
  tidak. 9/9 lolos.

**E1 belum dijalankan ulang** dengan setelan baru; angka Gate 1 yang berlaku
masih dari konfigurasi lama.

---

## 2026-11-11 — Fase 1 revisi: `max_depth = 3` tidak konvergen, premis ROI goyah

Entri 2026-11-10 dibatalkan sebagian (lihat catatan di sana). Ringkasnya: angka
yang dipakai untuk menyimpulkan "RIS memberi +36,2 dB di ROI" diukur pada
kedalaman pantulan yang terlalu dangkal.

### 1. Uji konvergensi terhadap `max_depth`

Grid uji 396 titik, link langsung BS→ROI, kedua varian fasad:

| depth | rata: nol % / median | berundak: nol % / median |
|---|---|---|
| 3 | 0,0% / **-124,5** | 47,2% / **-93,8** |
| 4 | 0,0% / -93,8 | 14,4% / -90,7 |
| 5 | 0,0% / -89,3 | 0,0% / -88,4 |
| 6 | 0,0% / -89,2 | 0,0% / -89,1 |
| 7 | 0,0% / -89,2 | 0,0% / -90,7 |

Median bergerak **~35 dB** antara depth 3 dan 5. Jadi `max_depth = 3`
(`configs/base.yaml`, `docs/EXPERIMENT_DESIGN.md` §8) **tidak memadai** untuk
geometri NLoS ini — jalur yang membawa daya ke ROI justru yang berpantulan 4–6
kali menyusuri kanyon.

Ini **bukan** soal anggaran sampel: menaikkan `samples_per_src` dari 1e6 ke 3e7
pada depth 3 tidak menggeser apa pun (tetap 47,2% nol). Knob-nya memang depth.

Catatan kejujuran soal "konvergen": pada scene berundak median bergoyang
-88,4 / -89,1 / -90,7 dB di depth 5/6/7 — derau Monte Carlo ~2 dB, tidak
mengunci seketat scene rata (-89,3 / -89,2 / -89,2). "Konvergen" di sini
berarti ±2 dB, dan itu tidak mengubah kesimpulan cakupan di bawah.

### 2. Mengapa E1 depth-6 penuh dibatalkan

`scripts/run_e1_coverage.py --config configs/e1_depth6.yaml` dijalankan, lalu
**dihentikan setelah 6,8 jam** (GPU 100%, VRAM 11969/12282 MiB, baru di sekitar
M=144; ekstrapolasi total ~15 jam).

Alasannya bukan biaya semata, melainkan biaya yang salah sasaran. Hampir seluruh
waktu terbakar di `g_grid` (M sumber per-elemen × 3.600 titik, baris 143–145),
padahal Gate 1 mengukur **RIS→ROI LoS = 100%** sehingga link itu didominasi
sinar langsung. Yang NLoS — dan karenanya butuh depth — hanya link langsung
BS→ROI, dan itu murah (22,4 s → 17,0 s dari depth 3 ke 6 pada grid 3.600).

Asumsi itu **diuji, bukan dipakai begitu saja**: `p_ris` M=144 pada 128 titik,
depth 3 vs 6 → median **-0,14 dB**, p95 |Δ| 0,22 dB, maks |Δ| **0,53 dB**.
Jadi run 15 jam itu akan menghasilkan angka RIS yang sama dalam 0,5 dB.

Diagnostik pengganti: `results/e1/f842993e1f46/depth_diagnostic.py` + `.json`.

### 3. Hasil pada kedalaman sahih

Cakupan (fraksi titik ROI dengan SNR ≥ 0 dB), scene fasad berundak:

| | 20 dBm | 30 dBm | 40 dBm |
|---|---|---|---|
| BS langsung, depth 3 (batal) | 0,525 | 0,525 | 0,525 |
| **BS langsung, depth 6** | **0,994** | **0,999** | **1,000** |
| RIS M=64 / 144 / 256 | 1,000 | 1,000 | 1,000 |

Penguatan RIS atas link langsung depth-6, M=144:

| | depth 3 (batal) | depth 6 |
|---|---|---|
| p10 | -0,4 dB | **-1,4 dB** |
| median | +36,2 dB | **+7,4 dB** |
| p90 | — | +17,4 dB |
| titik langsung > RIS | 11,2% | **14,3%** |

### 4. Konsekuensi — ini masalah premis, bukan masalah angka

ROI tetap NLoS dalam arti penghalangan garis pandang (fraksi LoS 0,0000, Gate 1
kriteria 2 lolos), tetapi **tidak kekurangan daya**: pemanduan kanyon
mengantarkan cukup daya tanpa RIS, menutup 99,4% ROI pada 20 dBm.

Gate 1 tidak menangkap ini karena **tidak satu pun kriterianya membandingkan
jalur RIS terhadap jalur langsung**. Gate lolos sementara premisnya goyah.

Fasad berundak — opsi (b) yang disetujui 2026-11-10 — **tidak menyelesaikannya**:
pada depth 6 median rata vs berundak adalah -89,2 vs -89,1 dB (p90 -77,3 vs
-74,8). Jadi jalur langsung yang kuat itu propagasi kanyon multi-pantul yang
asli, bukan artefak dinding rata. Opsi (b) boleh tetap dipakai, tetapi bukan
sebagai perbaikan untuk masalah ini.

Risiko untuk MDP (lebih berat daripada yang dicatat 2026-11-10, dan tidak lagi
terbatas di y ∈ [20, 35]): bila RIS hanya menambah ~7 dB median dan kalah di
14,3% titik, daya ungkit aksi agen mengecil di seluruh ROI.

### 5. Menunggu keputusan (perubahan parameter/fisika, per `CLAUDE.md`)

* **(A) `max_depth` 3 → 5 atau 6** di `configs/base.yaml` + §8 desain. Ini wajib
  terlepas dari keputusan lain; depth 3 menghasilkan fisika yang salah. Biaya
  pada link langsung dapat diabaikan, tetapi pada prakomputasi RIS per-elemen
  Fase 2 **besar** — perlu diukur ulang, karena estimasi 2,6 jam/scene di entri
  2026-11-10 butir 6 diukur pada `max_depth=3`. Mitigasi yang mungkin: depth
  tinggi hanya untuk link langsung yang NLoS, depth rendah untuk link RIS yang
  LoS — dibenarkan oleh pengukuran di butir 2, tetapi harus ditulis eksplisit di
  §4.2 agar kode dan paper tetap cocok.
* **(B) Premis ROI.** Pilihan: terima dan ubah klaim paper menjadi "RIS menambah
  ~7 dB", atau ubah geometri agar ROI benar-benar terhalang daya (mis. ROI lebih
  dalam di jalan B, atau kanyon yang tidak lurus) — yang terakhir menyentuh §2.1.
* **(C)** `ITURadioMaterial` default `scattering_coefficient = 0.0`, sehingga
  `ray_tracing.diffuse_reflection: true` **tidak berefek** di scene sintetis.
  Konsisten dengan uji mekanisme 2026-11-10 (mematikan difus tidak mengubah apa
  pun). Desain §4.2 meminta hamburan difus aktif, jadi kode dan desain saat ini
  tidak cocok.

Uji unit Fase 2 "h_d di ROI jauh lebih lemah daripada jalur lewat RIS"
(`docs/TASKS.md` Fase 2) akan gagal pada scene ini; tunda sampai (B) diputuskan.

---

## 2026-11-10 — Fase 1 selesai, Gate 1 LOLOS (dengan satu temuan terbuka)

> **SEBAGIAN DIBATALKAN 2026-11-11.** Entri ini dijalankan dengan
> `max_depth = 3`, yang kemudian terbukti belum konvergen untuk geometri NLoS
> ini. Semua angka kanal **langsung** di bawah (termasuk tabel cakupan "BS
> langsung" dan seluruh bagian "TEMUAN TERBUKA", khususnya penguatan RIS
> +36,2 dB) adalah artefak pemotongan kedalaman dan **tidak sahih**. Angka
> sisi RIS tetap berlaku (terukur tak sensitif terhadap depth, ±0,5 dB).
> Koreksi dan pengukuran ulang ada di entri 2026-11-11. Entri ini
> dipertahankan apa adanya sebagai rekam jejak, bukan dihapus.

Hasil di `results/e1/67700d360462/`. Dijalankan dengan
`python scripts/run_e1_coverage.py --config base`.

### Koordinat yang ditetapkan (sekarang di `configs/base.yaml`)

Simpang berpusat di origin, jalan selebar 20 m, empat blok gedung setinggi 20 m
dengan `block_extent_m = 80`. Jalan A memanjang ke -x, jalan B ke +y.

| Entitas | Nilai |
|---|---|
| BS (panel pancar) | (-60, -5, 10) |
| BS (panel terima) | (-60, -5, 9,5) |
| RIS | (9,9, 12, 6) — dinding barat blok NE, dekat sudut |
| Normal RIS | (-0,868, 0,493, -0,051) |
| ROI | x ∈ [-9, 9], y ∈ [20, 70], z = 1,5 — yaitu 10–60 m dari sudut simpang |
| Grid ROI | 0,5 m → 3.600 titik |

Normal RIS dipilih sebagai pembagi dua antara arah ke BS (azimut 193,7°) dan ke
pusat ROI (106,7°), sehingga keduanya berada 43,5° dari normal. Alternatif
dinding rata (normal 180°) membuat pusat ROI 73° dari normal, jauh lebih buruk.

### Hasil Gate 1

| Kriteria | Hasil |
|---|---|
| BS→RIS LoS | PASS (True) |
| BS→ROI NLoS di 100% titik | PASS (fraksi LoS = 0,0000) |
| M=144, P=30 dBm: SNR lewat RIS ≥ 0 dB di ≥80% titik | PASS (**100,0%**) |
| Oracle LoS setara `PathSolver(max_depth=0)` | PASS (0/64 ketidakcocokan) |

Cakupan (fraksi titik ROI dengan SNR ≥ 0 dB):

| | 20 dBm | 30 dBm | 40 dBm |
|---|---|---|---|
| BS langsung | 0,477 | 0,481 | 0,998 |
| RIS M=64 | 1,000 | 1,000 | 1,000 |
| RIS M=144 | 1,000 | 1,000 | 1,000 |
| RIS M=256 | 1,000 | 1,000 | 1,000 |

Waktu: BS→grid 43 s; RIS M=64/144/256 masing-masing 69 / 157 / 309 s.

### Verifikasi, bukan sekadar lolos gate

Cakupan 100% di semua konfigurasi perlu dibuktikan bukan bug. Link budget
analitik model kaskade memberi |h|² = -89,5 dB untuk M=64; ray tracing memberi
median -90,1 dB. Selisih 0,6 dB, jadi model dan simulasi sepakat.

Penskalaan terhadap M lebih rendah dari ideal, dan itu memang yang diharapkan:

| | Harapan (daya ∝ M²) | Terukur | Selisih |
|---|---|---|---|
| M 64→144 | +7,04 dB | +5,77 dB | -1,28 dB |
| M 144→256 | +5,00 dB | +3,87 dB | -1,13 dB |

Panel M=256 berukuran 0,69 m sehingga jarak Fraunhofer-nya 21,9 m, sedangkan
ROI mulai ~10 m dari RIS. Sebagian ROI berada di medan dekat, persis alasan
desain §4.2 menuntut array per-elemen. Kekurangan ~1,2 dB ini adalah tanda model
per-elemen bekerja, bukan galat.

### TEMUAN TERBUKA — jalur langsung terlalu kuat di ROI dekat

Gate 1 lolos, tetapi kriterianya tidak memeriksa hal ini. Perbandingan
per-titik antara jalur lewat RIS (M=144) dan jalur langsung:

| Persentil penguatan RIS atas langsung | dB |
|---|---|
| p0 | -12,1 |
| p10 | -0,4 |
| p25 | +3,7 |
| p50 | +36,2 |
| p100 | +49,9 |

**Di 11,2% titik ROI jalur langsung lebih kuat daripada jalur lewat RIS**, dan
di 47,7% titik penguatannya di bawah 20 dB. Titik-titik itu terkonsentrasi di
y ∈ [20, 35], yaitu sepertiga ROI yang dekat sudut.

Mekanismenya diuji, bukan ditebak. Mematikan difraksi tidak mengubah apa pun;
mematikan pantulan spekular menjatuhkan ROI dekat sebesar 45,8 dB. Geometri
jalur terkuat (dari `paths.vertices`):

```
jalur #1: (-43,10, +10,00, 8,20)  dinding selatan blok NW
          (-20,56, -10,00, 5,81)  dinding utara blok SW
          (+10,00, +17,12, 2,56)  dinding barat blok NE  -> ROI
```

Jadi: **pemanduan gelombang tiga pantulan** menyusuri kanyon jalan A lalu
membelok di sudut. Scene sintetis punya empat dinding beton raksasa yang
sempurna rata dan sejajar, sehingga menjadi pemandu gelombang yang jauh lebih
efisien daripada fasad kota sungguhan.

Dampaknya ada dua:

1. Uji unit Fase 2 "h_d di ROI jauh lebih lemah daripada jalur lewat RIS dengan
   profil fokus" (docs/TASKS.md Fase 2) **akan gagal** di scene ini.
2. Lebih penting: bila jalur langsung sebanding dengan jalur RIS di sepertiga
   dekat ROI, kendali fasa RIS kehilangan daya ungkit di sana, dan aksi agen
   menjadi kurang berpengaruh. Ini melemahkan MDP, bukan sekadar merusak satu tes.

**Menunggu keputusan.** Opsi yang diusulkan:

* (a) Terima untuk scene pengembangan saja, catat keterbatasannya, lalu periksa
  ulang di scene kota utama pada Fase 2 — fasad kota nyata tidak serata ini.
* (b) Rusak keteraturan fasad scene sintetis (undakan/setback atau tinggi gedung
  bervariasi) supaya kanyonnya tidak jadi pemandu gelombang ideal.
* (c) Geser ROI menjauh dari sudut — tetapi ini melanggar §2.1 yang menetapkan
  ROI pada 10–60 m dari sudut.

Rekomendasi: (a) + (b). Keduanya mempertahankan definisi ROI di §2.1.

### Catatan lain

* `sionna.rt` hanya mendaftarkan pola `iso`, `dipole`, `hw_dipole`, `tr38901` —
  tidak ada `cosine` yang diminta config. Didaftarkan sendiri di
  `src/risisac/channels/patterns.py` sebagai G(θ) = 4 cos θ pada setengah bola,
  sesuai §4.2 ("pola elemen kosinus atau pola bawaan yang mendekati"). Perhatikan
  konvensi sudut Sionna: boresight +x lokal, jadi kosinus terhadap normal adalah
  `sin(theta) cos(phi)`, bukan `cos(theta)`.
* Nama objek di `paths.objects` TIDAK selaras dengan urutan `scene.objects.keys()`.
  Gunakan `paths.vertices` (koordinat) untuk mengenali permukaan, jangan namanya.
* Visibilitas LoS memakai `mitsuba.ray_test`, bukan `PathSolver(max_depth=0)`:
  deterministik dan ribuan kali lebih murah untuk grid 3.600 titik. Kesetaraannya
  diuji di `tests/test_scene.py`, pada campuran titik LoS dan NLoS.
* Konvensi fasa kanal Sionna (`PHASE_SIGN = -1`, yaitu exp(-jkr)) **diukur**
  terhadap ray tracing di `tests/test_geometry.py`, tidak diasumsikan. Posisi dan
  urutan elemen (`m = j * num_rows + i`) juga diuji terhadap
  `PlanarArray.rotate` Sionna.
* Validator palet dari skill dataviz tidak bisa dijalankan (Node.js tidak
  terpasang di mesin ini). F1 memakai palet Okabe-Ito yang validasi buta warnanya
  sudah dipublikasikan; F2 memakai skala diverging dengan titik tengah tepat di
  ambang 0 dB sehingga batas Gate 1 terbaca langsung.

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

**DITERAPKAN 2026-11-10** setelah persetujuan:

```yaml
ray_tracing:
  max_num_paths_per_src: 1.0e5   # kunci baru; 5.0e4 untuk M=256
  rx_batch_size: 256             # dari 512; <=128 untuk M=256
```

Nilai untuk M=256 diberikan lewat file override yang mewarisi `base.yaml`,
sesuai aturan di `CLAUDE.md`, bukan dengan mengubah default.

`docs/EXPERIMENT_DESIGN.md` diperbarui bersamaan agar kode dan dokumen tetap
cocok: paragraf baru di §4.2 yang menjelaskan mengapa `max_num_paths_per_src`
adalah parameter pembatas memori pada array per-elemen, dan satu baris di tabel
parameter §8.

#### 2b. Enam nilai di `base.yaml` ter-parse sebagai string, bukan angka

Ditemukan saat memvalidasi perubahan di butir 2. PyYAML memakai resolver
YAML 1.1, yang hanya mengenali notasi eksponen sebagai float bila **tandanya
eksplisit**. `3.5e9` masuk sebagai `str`, `3.5e+9` sebagai `float`.

Yang terkena — semuanya sudah ada sebelum perubahan hari ini, kecuali yang
terakhir yang baru saya tambahkan dengan kesalahan yang sama:

| Kunci | Sebelum | Tipe lama |
|---|---|---|
| `radio.carrier_frequency_hz` | `3.5e9` | str |
| `radio.bandwidth_hz` | `20.0e6` | str |
| `ray_tracing.samples_per_src` | `1.0e6` | str |
| `ray_tracing.max_num_paths_per_src` | `1.0e5` | str |
| `training.total_timesteps` | `2.0e6` | str |
| `training.sac.total_timesteps` | `1.0e6` | str |

`training.ppo.learning_rate: 3.0e-4` selamat karena tandanya sudah ada.

Ini bug yang menunggu meledak jauh dari penyebabnya: `scene.frequency =
"3.5e9"` baru gagal di Fase 1, dan `total_timesteps` sebagai string baru gagal
di Fase 6.

**DITERAPKAN:** semua diubah ke bentuk bertanda (`3.5e+9` dst). **Nilainya
tidak berubah**, hanya tipenya; diverifikasi ulang dengan `yaml.safe_load`.
Aturan ini ditulis sebagai komentar di `base.yaml` agar override baru tidak
mengulanginya.

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

## 2026-11-11 (f) — Opsi (a): premis diperkuat; dua kesalahan solver ditemukan

Keputusan pengguna atas temuan terbuka entri (e): **opsi (a)** — naikkan ambang
Gate 1 ke nilai yang bermakna dan cari geometri yang memenuhinya.

Ambang `gate1.ris_gain_*` dinaikkan dari **0 dB di 90%** menjadi **6 dB di 80%**.
Alasan memilih 6 dB: dengan penjumlahan koheren, penguatan +6 dB berarti
amplitudo kaskade RIS sekurangnya **setara** jalur langsung, yaitu RIS benar-benar
menjadi jalur yang melayani ROI. Ambang 0 dB meloloskan penguatan 0,1 dB.

### Mekanisme yang membuat premis berdiri: lebar jalan

Gelombang langsung mencapai ROI sebagai gelombang **terpandu** yang memantul di
antara kedua dinding jalan B. Jumlah pantulan yang dibutuhkannya ~ jarak/lebar,
sedangkan hop RIS→ROI adalah LoS dan **tidak terpengaruh lebar sama sekali**.
Mempersempit jalan karena itu melemahkan jalur langsung tanpa melemahkan jalur
RIS. Terukur pada d(BS–RIS) ≈ 20 m, grid ROI 0,5 m, setelan solver konvergen:

| lebar jalan | 10 m | 9 m | 8 m | 7 m | **6 m** |
|---|---|---|---|---|---|
| d(BS–RIS) | 19,6 m | 20,0 m | 19,6 m | 20,2 m | 20,0 m |
| jalur langsung (MRT) | −70,9 dB | −78,3 dB | −80,8 dB | −84,3 dB | **−87,8 dB** |
| kaskade RIS | −76,9 dB | −76,8 dB | −76,3 dB | −76,1 dB | −75,4 dB |
| penguatan RIS median | +0,8 dB | +3,4 dB | +5,8 dB | +8,2 dB | **+11,9 dB** |
| fraksi ROI ≥ 6 dB | 0,02 | 0,16 | 0,46 | 0,78 | **0,93** |

Kaskade RIS bergerak 1,5 dB di seluruh baris itu; jalur langsung bergerak 17 dB.
Jadi lebar jalan bekerja lewat gelombang terpandu, bukan lewat link budget RIS.

Tuas kedua, memundurkan BS di jalan A, bergerak searah (lebar 10 m: +0,5 dB pada
d = 18,7 m menjadi +7,7 dB pada d = 41,1 m) tetapi mahal: SCNR turun 40 log₁₀ d₁
dan d(BS–RIS) menjauh dari "≈ 20 m" §2.1. Pada lebar 6 m tuas itu tidak
diperlukan.

**Koreksi entri (e).** Di situ tercatat "kanyon yang lebih lebar JUSTRU
memperburuk premis" dari sapuan lebar jalan. Arahnya benar tetapi sebabnya
salah: sapuan itu mengambil d(BS–RIS) **terkecil yang layak** di tiap lebar,
sehingga lebar dan jarak BS berubah bersama dan tidak terpisahkan. Pada lebar
tetap, memundurkan BS justru **memperbaiki** premis. Yang menentukan adalah
jumlah pantulan dinding, bukan lebar kanyon per se.

### Dua kesalahan solver yang membatalkan angka-angka sebelumnya

Sapuan pertama memberi hasil yang terlalu bagus, dan uji konvergensi
menunjukkan sebabnya. Keduanya **tidak memunculkan error apa pun**.

**1. `max_depth: 3` meleset 38 dB.** v0.1 sudah menyimpulkan kedalaman 5, tetapi
paket v0.2-lean datang dengan 3 dan itu terbawa — bug v0.1 **ketiga** yang
terulang di paket baru. Dengan hamburan difus **dimatikan** (himpunan jalur jadi
deterministik sehingga konvergensinya terbaca langsung), daya jalur langsung di
ROI:

| kedalaman | 3 | 5 | 7 |
|---|---|---|---|
| difus mati | **−124,5 dB** | −86,4 dB | −86,4 dB |
| difus hidup | −87,4 dB | −86,4 dB | −87,0 dB |

Kedalaman 3 tidak mampu membangkitkan pantulan dinding yang dibutuhkan gelombang
terpandu di jalan sempit. Dengan difus hidup, hamburan **menambal** lubang itu
sehingga kesalahannya tersamarkan — inilah sebabnya ia lolos sampai sekarang.
Ditetapkan `max_depth: 5` (5 dan 7 sama dalam 0,6 dB).

**2. Anggaran jalur tidak bisa satu nilai.** Buffer image-method berukuran
`max_num_paths_per_src × jumlah_sumber × 16 B`, jadi yang dibatasi VRAM adalah
**hasil kali**, bukan nilai per sumber. Satu nilai tetap karena itu pasti salah
di salah satu sisi. Pada 1e5 jalur, menaikkan `samples_per_src`:

| samples | 1e5 | 1e6 | 1e7 |
|---|---|---|---|
| jalur langsung, 1e5 jalur | −86,4 dB | −104,5 dB | **−143,9 dB** |
| jalur langsung, 1e6 jalur | −83,7 dB | −86,4 dB | −103,2 dB |

Daya **turun** saat sampel dinaikkan — mustahil secara fisik, dan jauh di bawah
lantai spekular −86,4 dB. Ini pemotongan diam-diam: sampel tambahan mengisi
buffer dengan jalur difus lemah dan membuang jalur kuat.

Uji kewarasan yang sekarang dipakai: **daya dengan difus hidup tidak boleh lebih
kecil daripada dengan difus mati.** Dengan uji itu, satu-satunya setelan yang
sah adalah `samples_per_src = 1e5` dengan `max_num_paths_per_src = 1e6`
(−83,7 dB, yaitu 2,7 dB di atas lantai spekular — hamburan menambah daya, seperti
seharusnya). Konvergensi sampel: 3e4 / 1e5 / 3e5 → −83,79 / −83,72 / −83,52 dB
(< 0,3 dB).

Sisi RIS (64 sumber) tidak muat pada 1e6 jalur (1 GiB per buffer, OOM), tetapi
**diverifikasi tidak terikat**: pada subarray 16 sumber, 1e5 lawan 1e6 jalur
berbeda 0,1 dB, dan anggaran ini bersifat per sumber. Ditambahkan
`ray_tracing.max_paths_total` (8e6) yang menurunkan nilai per sumber dari
anggaran total: 1e6 untuk 8 sumber, 1,25e5 untuk 64 — keduanya 128 MB per buffer.
`RayTracingSettings.paths_budget()` menggantikan `for_array_size()`; tes di
`tests/test_rt_settings.py`.

Ini **menutup utang terbuka** dari entri (b) dan (e): uji konvergensi
`max_num_paths_per_src` dan `samples_per_src` yang dijadwalkan Fase 2 sudah
selesai, dan hasilnya mengubah setelan.

**Catatan perangkat:** varian Dr.Jit LLVM (CPU) **tidak tersedia** di mesin ini —
`jitc_llvm_init(): LLVM API initialization failed`. Mitigasi OOM di `CLAUDE.md`
yang menyebut LLVM tidak bisa dipakai; tuas yang tersisa hanya `max_paths_total`
dan `rx_batch_size`.

### Geometri final

| | v0.2 (entri e) | v0.2 Fase 1 revisi |
|---|---|---|
| lebar jalan | 10 m | **6 m** (trotoar 2 × 1,0 m + lajur 2 × 2,0 m) |
| BS | (−13, −3, 10) | **(−16, −1, 10)** |
| RIS | (4,9, 6, 6) | **(2,9, 4, 6)** |
| d(BS–RIS) | 20,4 m | **20,0 m** |
| ROI | y ∈ [16, 36], 640 titik | **y ∈ [14, 34], 440 titik** |
| normal RIS | 52,4° ke BS dan ROI | **49,4°** |

ROI dilebarkan sampai **0,25 m** dari tiap dinding, bukan 1 m seperti sebelumnya:
§2.1 menempatkan pengguna di **trotoar**, jadi ROI yang berhenti di tepi lajur
meninggalkan pengguna di luar basis data kanal. Titik terdekat ke dinding juga
titik dengan penguatan RIS terkecil, sehingga memasukkannya **memperketat** gate
(fraksi ≥ 6 dB turun 0,96 → 0,93), bukan melonggarkannya.

### Gate 1 — LOLOS (`results/e1/29b21f95195c/`)

| Kriteria | Ambang | Hasil |
|---|---|---|
| BS→RIS LoS | — | PASS (True) |
| BS→ROI NLoS | 100% titik | PASS (0,0000) |
| SNR komunikasi > 10 dB | ≥ 90% | PASS (**1,000**) |
| SCNR ideal ≥ Γ + 3 dB | ≥ 80% | PASS (**1,000**) |
| **penguatan RIS > 6 dB** | **≥ 80%** | PASS (**0,927**) |
| oracle LoS = PathSolver(depth 0) | 0 beda | PASS (0/64) |

Median pada 30 dBm: SNR komunikasi 48,5 dB, SCNR 41,6 dB. Penguatan RIS median
**+11,9 dB**, p10 **+7,0 dB** — bandingkan dengan +1,4 dB dan p10 +0,0 dB pada
geometri lama. Seluruh E1 di bawah 10 detik.

### Premis sekarang berdiri di KEDUA sisi

Pemisahan kontribusi (`e1_split`, geometri baru):

| Komunikasi (SNR dB) | p10 | median | p90 |
|---|---|---|---|
| langsung (MRT) | 31,2 | 36,1 | 43,1 |
| RIS saja (kaskade) | 43,7 | **48,6** | 52,3 |

Jalur langsung menang di **0,0%** titik (sebelumnya 38,4%).

| SCNR ideal (dB) | p10 | median | p90 |
|---|---|---|---|
| langsung saja | −5,3 | 4,8 | 18,8 |
| RIS saja | 31,8 | **41,6** | 49,0 |

**Kriteria radar Gate 1 terpenuhi oleh jalur langsung saja hanya di 16,4% ROI**,
turun dari **99,5%** pada geometri lama. Ini menutup keberatan kedua di entri (e):
klaim "RIS dibutuhkan untuk sensing" kini teruji dengan ukuran yang sama dan
berdiri.

### Dokumen yang diselaraskan

`docs/EXPERIMENT_DESIGN.md` §2.1 (lebar jalan + mekanisme gelombang terpandu),
§4.2 (kedalaman dan anggaran jalur, dengan angka konvergensinya), §8 (tabel
parameter: ray tracing dan baris geometri baru); `docs/TASKS.md` Gate 1
kriteria 5; docstring `scripts/run_e1_coverage.py`.

### Sisa yang terbuka

* `scripts/place_geometry.py` masih mencari **jarak BS–RIS terkecil**, bukan
  penguatan RIS terbesar; objektif itu sudah terbukti keliru dua kali. Sapuan
  yang dipakai di sini ada di scratchpad, belum dipindahkan ke `scripts/`.
* Kalibrasi `radio.ris.calibration_db` masih 0,0 dan menunggu E0 (Fase 2).

---

## 2026-11-11 (g) — Fase 2: basis data kanal dan E0; bug fasa ditemukan E0

Gate 2 **LOLOS**. Dalam prosesnya E0 menangkap satu bug yang membatalkan
seluruh basis data kanal dan sebagian Gate 1 — persis fungsi yang diminta §4.5
untuk uji itu.

### Bug: `normalize_delays` menghapus fasa propagasi

`Paths.cir()` Sionna memakai default **`normalize_delays=True`**, yang menggeser
tundaan tiap pasangan perangkat sehingga jalur pertamanya tiba di t = 0 — dan
ikut **menghapus fasa propagasi dari koefisien kanal**. Terukur pada tiga titik
LoS ruang bebas (10 / 17 / 31 m):

| | fasa koefisien |
|---|---|
| `normalize_delays=True` (default) | 0,0000 / 0,0000 / 0,0000 rad |
| `normalize_delays=False` | 1,5870 / −2,9571 / 0,5212 rad |
| analitik −2πr/λ | 1,5869 / −2,9571 / 0,5212 rad |

**Mengapa ini tidak terlihat sampai sekarang.** Offset-nya sama untuk seluruh
elemen dalam satu pemanggilan, jadi fasa **relatif antar-elemen** tetap benar.
Profil fokus tetap bekerja, penjumlahan koheren lintas elemen tetap optimal,
dan peta cakupan E1 tetap terlihat wajar. Yang rusak adalah fasa relatif
**antar-pemanggilan**, yaitu persis yang dibutuhkan

    h_e = h_d + g^T Theta G   (E2)      dan      c = h_d,t + g_t^T Theta G  (E5),

dua penjumlahan yang menjadi inti seluruh Fase 3 ke atas. `clutter_channel`
kebetulan sudah memakai `False`, sehingga **H**_c pun tidak konsisten dengan
kanal lain.

**Cara menangkapnya.** Uji kaskade saja TIDAK cukup: offset fasa global tidak
mengubah magnitudo |Σ|, jadi uji kaskade E0 lolos 0,0002 dB sementara fasa per
elemen meleset 120°. Kriteria kelulusan E0 karena itu ditambah **fasa per
elemen < 1°**, dan `tests/test_channels_rt.py` mendapat dua tes baru: fasa
absolut sama dengan −2πr/λ, dan dua pemanggilan terpisah bisa dijumlahkan
koheren.

**Dampak.** Seluruh 42.000 titik dihitung ulang. Gate 1 diuji ulang karena tiga
dari enam kriterianya (komunikasi, radar, penguatan RIS) memakai penjumlahan
`h_d + kaskade`. Hasilnya nyaris tidak bergeser — penguatan RIS 0,927 → 0,930,
median +11,9 → +11,8 dB, SCNR median 41,6 → 41,9 dB — karena kaskade memang
mengungguli jalur langsung 12 dB sehingga fasa relatifnya kurang berpengaruh di
sini. Verdict Gate 1 tidak berubah, tetapi sekarang berdiri di atas fisika yang
benar, dan Fase 3 (SINR E3, SCNR E7) tidak akan dimulai dari kanal yang salah.

**Penjaga baru.** `config_hash` hanya menangkap config, bukan KODE, sehingga
basis data lama terbaca sebagai lengkap dan dipakai diam-diam. Commit git kini
disimpan di `meta`, prakomputasi memperingatkan bila berbeda dari HEAD, dan ada
`--rebuild`.

### Lintasan (§2.3)

`src/risisac/mobility/trajectories.py`, murni NumPy, tanpa Sionna. Dua keputusan
yang diambil dari pengukuran:

1. **Target masuk ke ROI, tidak muncul di tengahnya.** Awal yang seragam di
   sepanjang ROI menyisakan rata-rata hanya separuh ROI di depan target:
   median **17 dari 50** langkah sebelum episode terpotong, dan sebagian besar
   anggaran ray tracing terbuang pada langkah yang tidak pernah dipakai. Dengan
   awal diacak di 20% pertama dari tepi masuk: median **34**, rata-rata 35,5,
   minimum 17. Korelasi kecepatan-lawan-lama-di-ROI −0,54 (diuji).
2. **Derau lateral harus berkorelasi waktu.** Derau putih per langkah dengan
   jitter 5 cm menghasilkan kecepatan lateral **4,6 m/s** setelah didiferensiasi
   — tidak fisik, dan merusak asumsi kecepatan-konstan tracker Kalman (§5.2).
   Diganti derau berkernel Gauss; puncaknya kini ditentukan perubahan lajur
   (2 m / 2 s, smoothstep) = 1,5 m/s. Durasi perubahan lajur dinaikkan 1 s → 2 s
   (nilai lazim rekayasa lalu lintas).

ROI juga diperlebar sampai 0,25 m dari dinding supaya **trotoar ikut masuk**:
§2.1 menempatkan pengguna di trotoar, jadi ROI yang berhenti di tepi lajur akan
meninggalkan pengguna di luar basis data kanal.

Total titik penerima: 280 lintasan × 50 langkah × 3 entitas = **42.000**, cocok
dengan perkiraan §4.3.

### Basis data (§4.4)

`src/risisac/channels/database.py`. Penulisan **bisa dilanjutkan**: atribut
`complete` baru ditulis setelah seluruh dataset satu lintasan masuk, sehingga
lintasan separuh tertulis terbaca sebagai hilang dan dihitung ulang. Lintasan
ke-i memakai RNG `(seed_split, i)` sehingga isinya tidak bergantung urutan
pengerjaan. Skema §4.4 ditambah `in_roi` dan atribut `speed_mps`, karena
environment RL tidak boleh mengimpor Sionna dan harus mendapat semuanya dari
file.

**H**_c dihitung monostatik BS-tx → BS-rx dengan jalur LoS tx-rx dibuang lewat
`Paths.interactions` (jalur LoS = seluruh kedalamannya `InteractionType.NONE`),
bukan lewat ambang tundaan yang rapuh. Bentuk `interactions` **berbeda** antara
mode per-elemen (6 dimensi) dan synthetic (4 dimensi); keduanya ditangani.

### Prakomputasi

| | |
|---|---|
| waktu | train 371,7 s + val 55,6 s + test 92,8 s = **8,7 menit** |
| puncak VRAM | **4,40 GiB** dari 11,99 GiB |
| ukuran file | 27,4 MiB |
| laju | ~1,9 s per lintasan (150 titik, 3 jenis link) |

VRAM terpakai merangkak pelan (4,28 → 4,40 GiB selama 280 lintasan). Tidak
masalah pada skala ini, tetapi perlu diawasi bila basis data diperbesar.

### E0 (§4.5) — `results/e0/1365548d0387/`

**1. Uji implementasi** (ambang 0,1 dB):

| | hasil |
|---|---|
| amplitudo per elemen **G** | 0,0000 dB |
| amplitudo per elemen **g** | 0,0000 dB |
| fasa per elemen **G** / **g** | 0,0159° / 0,0142° (ambang 1°) |
| kaskade, 3 profil fokus + 1 gradien | terburuk **0,0144 dB** |

Model analitiknya diturunkan dari source Sionna 2.2 yang terpasang
(`path_solvers/field_calculator.py`), bukan dari ingatan: medan berangkat
sebagai pola antena, 1/r · 1/√(4π), lalu λ/√(4π) dan proyeksi
`jones_vec_dot(u,v) = u^H v` di penerima. Polanya dievaluasi lewat registry
Sionna sendiri, termasuk pola `cosine` yang kita daftarkan.

**2. Kalibrasi fisika.** Tang, W. dkk. (2021), *IEEE Transactions on Wireless
Communications*, 20(1), 421–439, Pers. (6) kasus far-field beamforming:

    PL = 64 pi^3 (d1 d2)^2
         / (G_t G_r G M^2 N^2 d_x d_y lambda^2 F(th_t,ph_t) F(th_r,ph_r) A^2)

Rumusnya **diverifikasi dari paper aslinya** (versi arXiv 1911.05326), bukan
dari ingatan. Hasil: **calibration_db = +1,05 dB**, sebaran **0,00 dB** di
d2 = 11–31 m, jadi benar-benar konstan.

`calibration_db` **dicatat, tidak diterapkan** ke kanal. Pers. (6) adalah
aproksimasi medan jauh yang menganggap seluruh sel satuan punya jarak dan sudut
sama; model hibrida menjumlah per elemen secara eksak dan sudah terverifikasi
terhadap Friis analitik sampai 0,014 dB. Mengurangi 1,05 dB justru merusak
model yang benar agar cocok dengan aproksimasinya.

**3. Per elemen vs synthetic array** (147 titik grid ROI scene utama): median
+0,16 dB, p95 |selisih| **2,19 dB**, maksimum 3,24 dB. **Terlalu besar untuk
dipakai** — mode per elemen dipertahankan. (Jarak Fraunhofer RIS 8×8 adalah
3–6 m, sedangkan ROI 10–30 m, jadi asumsi medan jauhnya tidak jauh meleset;
yang menyimpang adalah titik-titik bersudut besar.)

### Gate 2 — LOLOS

| Kriteria | Hasil |
|---|---|
| semua tes lulus | **70 lolos** (dari 32) |
| uji implementasi E0 < 0,1 dB | **0,0144 dB** |
| `calibration_db` tercatat | **+1,05 dB** (`configs/base.yaml`) |
| prakomputasi lengkap 3 split | **280/280 lintasan, 42.000 titik** |

### TEMUAN untuk Gate 3 — clutter mendominasi lantai derau

Terukur pada geometri final: ‖**H**_c‖² = −53,4 dB. Pada P = 30 dBm dan
ξ = 0,01, suku clutter di **R**_cn berada **77,6 dB di atas** suku derau
σ_n²/L. Tetapi **R**_x berpangkat rendah (rank 1 untuk beam sensing tunggal),
sehingga suku clutter juga rank 1 dan pada prinsipnya bisa di-null MVDR —
itulah sebabnya (E7) memakai **R**_cn⁻¹ dan bukan sekadar derau.

Artinya SCNR sesungguhnya akan bergantung pada **keselarasan b dengan arah
clutter**, bukan pada margin derau yang dilaporkan E1. SCNR ideal E1
(median 41,9 dB terhadap ambang 16 dB) karena itu adalah **batas atas**, bukan
ramalan. Harus diukur di Fase 3 sebelum Gate 3; bila kerugiannya besar,
tuasnya adalah ξ, L, atau geometri BS.

### Lain-lain

* Sisa yang terbuka dari entri (f): `scripts/place_geometry.py` masih memakai
  objektif jarak terkecil yang sudah terbukti keliru. Belum disentuh.
* Dokumen diselaraskan: §4.2 (`normalize_delays`), §4.4 (skema + sifat bisa
  dilanjutkan), `docs/TASKS.md` Fase 2 dicentang.

---

## 2026-11-11 (h) — Fase 3: model sinyal, tracker, baseline; Gate 3 GAGAL (reward, bukan fisika)

Seluruh kiriman Fase 3 selesai dan 128 tes lolos, tetapi **Gate 3 gagal** pada
satu kriteria. Sebabnya bukan ketidakmampuan sistem melainkan bobot reward, dan
perbaikannya menyentuh §5.4 sehingga **menunggu persetujuan** (CLAUDE.md).

### Yang dibangun

| Modul | Isi |
|---|---|
| `system/signal_model.py` | (E1)-(E7) terbatch + reward (E9), NumPy |
| `system/signal_model_torch.py` | padanan PyTorch terdiferensiasi untuk Oracle-GD |
| `system/precoding.py` | RZF, beam sensing, anggaran daya dipenuhi **secara konstruksi** |
| `system/ris.py` | pembaruan fasa inkremental / absolut (ablasi A1) |
| `tracking/kalman.py` | Kalman kecepatan-konstan 2D + model galat §5.2 |
| `baselines/common.py` | mesin evaluasi bersama semua metode |
| `baselines/{random_policy,geometric,oracle_gd}.py` | B1, B2, B3/B4 |

Empat uji yang diminta desain semuanya membandingkan bentuk tertutup dengan
sesuatu yang dihitung **dengan cara lain**: SCNR (E7) lawan maksimum Rayleigh
umum numerik (cocok 1e-8 relatif), SINR (E3) lawan simulasi 400.000 simbol
(cocok 3%), tr(R_x) <= P_max (dipenuhi persis untuk sembarang rho), dan eta
(E6) lawan persamaan radar bistatik (cocok 1e-12).

### Dua temuan solver yang muncul saat merapikan reproduksibilitas

**1. Solver GPU tidak bit-deterministik.** Dua pemanggilan identik berbeda
sampai 0,48 dB; penyebabnya urutan reduksi atomik, bukan RNG (seed-nya sudah
sama). `PathSolver(deterministic=True)` menghilangkannya (7,6e-6 dB) tetapi
**tidak muat di GPU 12 GB**: link RIS 64-sumber meminta alokasi 32 GiB, dan
hanya berjalan pada `rx_batch_size <= 8` dengan biaya sekitar 100x.

Karena itu dibiarkan `false` dan reproduksibilitasnya **diukur**: E1 dijalankan
tiga kali, dan besaran yang dilaporkan bergeser <= 0,05 dB (SCNR median
41,7 / 41,8 / 41,7; penguatan RIS +12,0 / +11,9 / +11,9), sedangkan fraksi
gate identik (0,932 ketiganya). Semua yang dilaporkan adalah median atas
ratusan titik, jadi derau per elemen tidak lolos ke kesimpulan.

**2. `refraction` menyala secara default dan tidak ada di §4.2.** Diukur:
menyalakannya mengubah daya jalur langsung di ROI dengan median **-0,02 dB**
(p90 +0,54, maks +1,58) -- tembusan 0,3 m beton pada 3,5 GHz memang tidak
membuka jalur berarti. Dimatikan agar kode dan §4.2 ("spekular + difus +
difraksi") cocok.

### `channel_config_hash`: hash kanal dipisahkan dari hash config

Menambah blok `gate3` dan `tracking` ke config mengganti nama file basis data
dan membatalkan 9 menit ray tracing, padahal kanalnya identik. Nama file kini
memakai `channel_config_hash`, yang hanya memuat bagian yang benar-benar
menentukan isi kanal (`scene`, `ray_tracing`, `mobility`, dan sebagian
`radio`).

Arah kesalahan yang berbahaya di sini adalah yang sebaliknya -- hash terlalu
sempit memakai ulang kanal basi secara diam-diam -- jadi pembagiannya dibuat
**eksplisit dan diuji**: `tests/test_config.py` menolak kunci tingkat atas baru
yang belum diklasifikasikan.

Catatan: percobaan memakai ulang file lama dengan menamainya ulang **ditolak
oleh pengukuran**. Dibandingkan dengan hitung ulang, isinya berbeda (median
0,015-0,13 dB, maks 28 dB pada elemen lemah) -- yaitu derau Monte Carlo
hamburan difus di atas, bukan kebasian. Basis data tetap dibangun ulang.

### Clutter: temuan terbuka Gate 2 selesai, hasilnya melegakan

Entri (g) menandai bahwa suku clutter di **R**_cn berada 77,6 dB di atas suku
derau, sehingga SCNR ideal E1 adalah batas atas. Terukur sekarang dengan (E7)
lengkap pada 200 snapshot val (fasa acak, rho = 0,5):

| | SCNR median |
|---|---|
| tanpa clutter (xi = 0) | 13,8 dB |
| dengan clutter (xi = 0,01) | 11,6 dB |

Kerugian **median 2,34 dB**, p90 4,98 dB, maks 7,50 dB. Jauh di bawah 77,6 dB
karena **R**_x berpangkat rendah: suku clutter rank-1 dan sebagian besar
di-null MVDR, persis alasan (E7) memakai **R**_cn^{-1}. Tidak perlu mengubah
xi, L, atau geometri.

### B2 lebih lemah daripada B1 pada laju -- dan itu fisik, bukan bug

| metode | reward | min rate | SCNR median | deteksi |
|---|---|---|---|---|
| B1 random | **3,674** | 4,179 | 10,2 dB | 0,390 |
| B2 geometric | 2,275 | 2,275 | **35,5 dB** | **1,000** |
| B3 oracle-GD | **11,428** | **11,472** | 15,1 dB | 0,845 |

B2 memfokuskan RIS dan menaikkan daya kanal pengguna 5 dB, tetapi laju-nya
justru turun. Dugaan pertama -- korelasi antar-pengguna naik (0,39 -> 0,69)
sehingga RZF menderita -- **terbantah oleh pengukuran**: interferensi
antar-pengguna hanya -167 dB, RZF menihilkannya dengan baik. Dekomposisi SINR
(median, P = 1 W, rho = 0,10):

| | sinyal | antar-pengguna | bocor sensing | derau |
|---|---|---|---|---|
| B1 fasa acak | -91,4 | -167,0 | **-105,7** | -124,0 |
| B2 omega_t = 0,75 | -86,4 | -167,4 | **-94,9** | -124,0 |

Yang mengikat adalah **kebocoran beam sensing ke pengguna**: 12 dB lebih besar
pada B2. Mekanismenya langsung -- RIS yang sama melayani pengguna dan target di
jalan yang sama, jadi semakin tajam RIS memfokus ke target, semakin besar
``h_e,k^T w_s``. Dengan beta_s = 1 (§3.3) kebocoran itu murni interferensi.

Ini justru **memperkuat** premis paper: kopling komunikasi-sensing di
RIS-ISAC bukan sekadar pembagian daya, melainkan pembagian **profil fasa**, dan
itulah yang harus dikelola agen. B3 yang mengoptimalkan bersama-sama memperoleh
laju 11,47 **dan** SCNR 15,1 dB sekaligus.

### Gate 3 — GAGAL pada satu kriteria

| Kriteria | Hasil |
|---|---|
| B3 memenuhi SCNR >= Gamma di >= 90% val | **GAGAL (0,845)** |
| B3 mengungguli B1 (margin reward 0,5) | PASS (+7,75) |
| anggaran daya dipenuhi | PASS (4e-16) |

**Sebabnya bukan ketidakmampuan sistem.** B2 sudah memenuhi Gamma di **100%**
snapshot. Sapuan lambda pada B3 memisahkan kedua kemungkinan:

| lambda | min rate | SCNR median | SCNR p10 | deteksi |
|---|---|---|---|---|
| **1,0 (sekarang)** | 11,472 | 15,1 | 12,1 | **0,845** |
| 3,0 | 11,573 | 16,6 | 14,7 | 0,995 |
| 10,0 | 11,630 | 18,0 | 16,1 | **1,000** |
| 30,0 | 11,644 | 19,0 | 17,1 | 1,000 |
| 100,0 | 11,580 | 19,7 | 18,1 | 1,000 |

Yang menentukan: **laju tidak turun sama sekali** saat lambda dinaikkan — malah
naik tipis (11,47 -> 11,64). Memenuhi kendala sensing di geometri ini praktis
gratis; B3 tidak melakukannya pada lambda = 1 semata karena reward tidak
menuntutnya.

Akarnya adalah ketidakcocokan antara (E8) dan (E9). (E8) §3.6 menuliskan
kendala **keras** SCNR >= Gamma; (E9) §5.4 melonggarkannya menjadi hinge dengan
lambda = 1 dan skala 10 dB. Dengan laju sekitar 11 bit/s/Hz, kegagalan sensing
total hanya berbiaya 3,3 bit/s/Hz — lebih murah daripada daya yang dibutuhkan
untuk memperbaikinya. **Pada bobot ini sensing praktis opsional**, dan agen DRL
hampir pasti akan mempelajari hal yang sama.

**MENUNGGU KEPUTUSAN** (§5.4 adalah definisi reward; CLAUDE.md melarang
mengubahnya tanpa persetujuan):

* (a) **Naikkan lambda ke 10** (rekomendasi). Deteksi 1,000, dan tidak ada
  biaya laju sama sekali. lambda = 3 adalah nilai terkecil yang lolos (0,995)
  tetapi tanpa margin.
* (b) Pertahankan lambda = 1 dan longgarkan kriteria Gate 3 menjadi "SCNR
  >= Gamma dapat dicapai", yang sudah dibuktikan B2 (100%). Risikonya paper
  melaporkan agen yang mengabaikan sensing.
* (c) Perketat kendala lewat Gamma, bukan lambda (E4b sudah menyapu
  Gamma = 10/13/16). Tidak menyelesaikan masalah: hinge yang lemah tetap lemah
  pada Gamma berapa pun.

Fase 4 tidak dimulai sebelum ini diputuskan: environment RL memakai (E9)
sebagai reward, jadi melatih dulu berarti melatih pada objektif yang salah.

---

## 2026-11-11 (i) — lambda dinaikkan ke 10; Gate 3 LOLOS

Keputusan pengguna atas titik keputusan entri (h): **opsi (a)**, naikkan bobot
reward. `reward.lambda` 1,0 -> **10,0** di `configs/base.yaml`, dan §5.4 serta
tabel parameter §8 diselaraskan.

`channel_config_hash` tidak berubah (`6949e64b5418`), jadi **tidak ada ray
tracing ulang** -- persis alasan hash kanal dipisahkan dari hash config di
entri (h).

### Gate 3 — LOLOS (3/3), `results/gate3/2ac2654fe51c/`

| Kriteria | Ambang | Hasil |
|---|---|---|
| B3 memenuhi SCNR >= Gamma di val | >= 0,90 | **1,000** |
| B3 mengungguli B1 (margin reward) | >= 0,5 | **+12,50** |
| anggaran daya dipenuhi | < 1e-6 | 4e-16 |

### Efek samping yang menguntungkan: urutan baseline menjadi benar

| metode | reward (lambda=1) | reward (lambda=10) | min rate | SCNR median | deteksi |
|---|---|---|---|---|---|
| B1 random | 3,674 | **-0,874** | 4,179 | 10,2 dB | 0,390 |
| B2 geometric | 2,275 | **2,275** | 2,275 | 35,5 dB | 1,000 |
| B3 oracle-GD | 11,428 | **11,630** | 11,630 | 18,0 dB | 1,000 |

Pada lambda = 1, B1 (fasa acak) mengungguli B2 (geometris) pada reward --
urutan yang akan sulit dipertahankan di paper, karena baseline yang memakai
informasi justru kalah dari yang tidak. Penyebabnya sama dengan kegagalan
Gate 3: B1 membuang sensing (deteksi 0,390) dan nyaris tidak dihukum. Dengan
lambda = 10 urutannya menjadi **B1 < B2 < B3** seperti seharusnya.

Reward B3 kini sama persis dengan rate minimumnya (11,630) karena deteksinya
100%, sehingga hinge-nya nol -- konsisten dengan (E9).

### Yang masih terbuka

* `scripts/place_geometry.py` masih memakai objektif jarak terkecil yang sudah
  terbukti keliru (entri (f)). Tidak dipakai lagi, tetapi membingungkan bila
  dibaca ulang.
* Fase 4 belum dimulai.

---

## 2026-11-11 (j) — Fase 4: environment RL; Gate 4 LOLOS

### Yang dibangun

`src/risisac/env/ris_isac_env.py` (`RisIsacEnv`, `EnvConfig`, `TrajectoryStore`)
dan `src/risisac/env/vec.py`. Environment **tidak mengimpor Sionna**; seluruh
kanal dibaca dari HDF5 Fase 2 dan seluruh lintasan satu split dimuat ke memori
sekali, karena membaca HDF5 tiap `reset()` akan mendominasi waktu langkah dan
menggagalkan syarat laju Gate 4.

Dimensi cocok dengan desain tanpa penyesuaian: observasi parsial **174**
(§5.2), penuh **558** (174 + 2M(K+Q) = 174 + 384), aksi **67** (M + 1 + K,
§5.3), dan setelah frame-stack 4 menjadi **696**.

Tumpukan pembungkus: `SubprocVecEnv(8)` -> `VecNormalize(observasi saja)` ->
`VecFrameStack(4)`. Normalisasi **sebelum** penumpukan supaya statistiknya
dihitung atas 174 fitur satu frame, bukan atas 696 salinan yang berkorelasi.
Reward sengaja **tidak** dinormalisasi (§6.1) agar sebanding dengan tabel hasil.

### Gate 4 — LOLOS

| Kriteria | Hasil |
|---|---|
| semua tes lulus | **142** |
| `check_env` (parsial dan penuh) | LOLOS |
| uji asap PPO-PO mengalahkan B1 di val | LOLOS (300 rb langkah, 3 seed) |
| laju >= 1.000 langkah/detik per proses | **3.282** |

Empat tes yang diminta desain semuanya menguji kesetaraan terhadap sesuatu di
luar environment: `check_env` Gymnasium, determinisme seed (trajektori identik
bit demi bit), reward **dihitung ulang dari `info`** dengan (E9), dan
**kebijakan B2 lewat env = B2 langsung** sampai 1e-9 relatif. Yang terakhir
penting: tanpa itu, selisih agen-lawan-baseline bisa berasal dari dua jalur
hitung yang berbeda, bukan dari kebijakan.

Menyusun tes terakhir itu memunculkan satu detail urutan frame: env membangun
beam sensing dari state tracker di **awal** langkah lalu memperbarui tracker di
**akhir** (§5.1 butir 3 lawan butir 5), jadi pembandingnya harus memakai
`g_hat` sebelum langkah. Membandingkan dengan `g_hat` sesudah langkah memberi
selisih 0,05% -- cukup kecil untuk lolos tanpa dicurigai bila toleransinya
longgar.

### Anggaran uji asap dinaikkan 100 rb -> 300 rb (berdasarkan pengukuran)

Uji asap **gagal** pada 100 ribu langkah seperti tertulis di `docs/TASKS.md`,
tetapi bukan karena environment rusak. Reward per langkah di val
(B1 = -0,903):

| langkah | 8 rb | 100 rb | 150 rb | 200 rb | **300 rb** |
|---|---|---|---|---|---|
| seed 0 | -2,490 | -1,679 | +0,412 | +0,924 | **+1,803** |
| seed 1 | | | -0,710 | | **+2,530** |
| seed 2 | | | +0,141 | | **+2,236** |

Kurvanya monoton naik dan PPO melewati B1 antara 100 dan 150 ribu langkah.
Pada 150 ribu marginnya hanya **0,19** di seed terburuk -- terlalu tipis untuk
sebuah penyaring. Pada 300 ribu ketiga seed unggul **2,7-3,4**.

**Mengapa 100 ribu tidak cukup.** Aksi ρ dimulai di 0,5 (ρ_raw ~ 0 pada
inisialisasi kebijakan), sedangkan nilai yang baik sekitar 0,1 -- yaitu nilai
yang B1 peroleh **gratis** lewat sapuan grid di val. ρ hasil PPO: 0,247
(150 rb) -> 0,227 (200 rb) -> **0,139 / 0,075 / 0,143** (300 rb, tiga seed).
Jadi sebagian besar 100 ribu langkah pertama habis untuk menurunkan ρ, dan
baru setelah itu agen mulai memperbaiki fasa. Perbandingannya memang timpang
di awal: B1 mendapat satu parameternya di-tuning pada data val, PPO tidak.

Agen menemukan sendiri pembagian daya yang hampir sama dengan hasil sapuan
grid B1 (0,075-0,143 lawan 0,100) -- sinyal bahwa (E9) dan precoder-nya
konsisten satu sama lain.

Biaya uji asap 300 ribu langkah adalah **130 detik**, dapat diabaikan
dibanding 15 run x 1e6 langkah yang disaringnya.

### Lain-lain

* Laju env 3.282 langkah/detik per proses; throughput pelatihan PPO 2.317
  langkah/detik dengan 8 env di CPU. Satu run 1e6 langkah karena itu sekitar
  **7,2 menit**, jadi 15 run sekitar 1,8 jam -- jauh di bawah perkiraan
  jadwal (minggu 5 "jalan malam hari").
* Kanal efektif pada observasi diskalakan ke satuan amplitudo SNR
  (`sqrt(P_max/sigma_n^2)`); nilai mentahnya berorde 1e-5 dan akan membuat
  lapisan pertama jaringan bekerja di rentang yang buruk bahkan dengan
  VecNormalize.

---

## 2026-11-11 (k) — Fase 5: 15 run pelatihan; Gate 5 LOLOS, dengan satu temuan besar

### Yang dibangun

`src/risisac/train/train.py` (M1/M2/A1 dari satu config), `src/risisac/env/vec.py`
(`env_overrides`), `src/risisac/baselines/env_policy.py` (B1/B2 sebagai
kebijakan di dalam env), `src/risisac/eval/rollout.py` (satu mesin rollout
untuk semua metode), `plot_f4_training`, `scripts/run_all_training.sh`,
`scripts/run_gate5_check.py`, `configs/gamma10.yaml`, `configs/gamma16.yaml`.
152 tes lulus (dari 142).

Metode diterapkan lewat `env_overrides` pada `EnvConfig`, **bukan** dengan
mengubah dict config: kalau metode mengubah config, `config_hash` ikut berubah
dan hasil tiga metode dari satu config tersebar ke tiga direktori yang tampak
tidak berhubungan.

**Baseline dipindah ke dalam env.** Fase 3 mengevaluasi B1/B2 pada snapshot
lepas; Gate 5 membandingkan pada episode. Dua hal baru muncul di env: estimasi
target datang dari tracker Kalman (kualitasnya bergantung keputusan
sebelumnya), dan panjang episode bergantung keputusan. Keduanya bagian dari
masalah yang diklaim paper, jadi angka baseline untuk paper diambil dari jalur
ini. Hasilnya cocok dengan Fase 3: B2 memberi +2,261 lewat env lawan +2,275
pada snapshot, dengan omega dan rho terpilih yang identik (0,75; 0,1).

**Bug ditemukan saat menulis tesnya:** RNG baseline semula diturunkan dari
penghitung episode env, sehingga hasil B1 pada satu lintasan bergantung pada
berapa episode yang kebetulan dijalankan sebelumnya — terukur menggeser
reward/langkah **0,26** antara sapuan grid dan evaluasi akhir, padahal
keputusannya sama. Diganti ke indeks lintasan; sekarang keduanya cocok sampai
1e-6.

### Gate 5 — LOLOS (config base, Gamma = 13 dB)

Kriteria "reward val naik < 2% dalam 20% langkah terakhir" tidak terdefinisi
apa adanya: reward mulai negatif dan berakhir positif, jadi "naik 2%" relatif
terhadap nilai awal bisa berarti apa saja. Yang dipakai dan dicatat:
kenaikan 20% langkah terakhir dibagi total kenaikan sejak langkah 0.

| kriteria | hasil |
|---|---|
| m1_converged | ekor **-1,46%** dari kenaikan total (ambang 2%) |
| m1_beats_b1 | **+3,783** lawan -0,750 |
| m1_beats_b2 | **+3,783** lawan +2,261 |

Hasil val (reward/langkah, rate minimum, pemenuhan SCNR):

| metode | reward | min rate | SCNR med | deteksi | rho |
|---|---|---|---|---|---|
| B1 | -0,750 | 4,08 | 10,0 | 0,345 | 0,100 |
| B2 | +2,261 | 2,27 | 34,7 | **0,998** | 0,100 |
| M1 | +3,783 | 8,26 | 10,9 | 0,408 | 0,003 |
| M2 | +3,910 | 8,36 | 11,0 | 0,413 | 0,001 |
| A1 | +5,769 | 8,44 | 14,4 | 0,567 | 0,002 |
| B3 (Fase 3) | +11,63 | 11,63 | 18,0 | 1,000 | — |

### Temuan: kendala fasa INKREMENTAL yang mengorbankan sensing, bukan lambda

Pada mulanya ini tampak seperti masalah bobot reward: ketiga agen menurunkan
rho ke ~0,00 dan membiarkan SCNR di bawah Gamma, menukar ~3 dB defisit (biaya
3 bit/s/Hz pada lambda = 10) dengan ~6 bit/s/Hz rate di atas B2. Rasional,
tetapi merusak premis ISAC: B2 memenuhi SCNR di 99,8% langkah, M1 hanya 40,8%.

**Lambda bukan penyebabnya.** F4 dan checkpoint menunjukkan A1 — yang memakai
lambda yang sama persis — mencapai **deteksi 0,95-0,96 dengan rate 8,4** di
sekitar 350-450 ribu langkah, pada ketiga seed:

| run | puncak val | @langkah | deteksi@puncak | akhir | deteksi@akhir |
|---|---|---|---|---|---|
| A1 seed 0 | **+8,220** | 350 rb | **0,960** | +6,442 | 0,627 |
| A1 seed 1 | **+8,026** | 450 rb | **0,949** | +5,464 | 0,529 |
| A1 seed 2 | **+8,139** | 350 rb | **0,948** | +5,400 | 0,546 |
| M1 seed 0-2 | +3,76 .. +4,38 | 700-950 rb | 0,42-0,46 | +3,44 .. +4,25 | 0,39-0,43 |

Jadi solusi ISAC yang baik ADA dan dapat ditemukan agen dengan reward ini —
tetapi hanya saat fasa boleh diatur **absolut**. Dengan pembaruan inkremental
(kappa = 0,1), M1 dan M2 tidak pernah melewati deteksi 0,46 pada seed mana pun.

Dua hal yang mengikat pada mode inkremental: dari fasa acak, menggeser satu
elemen sejauh pi butuh 10 langkah pada 0,1 pi/langkah, yaitu sekitar 29% dari
episode 35 langkah; dan profil fokus harus terus dikejar karena targetnya
bergerak. Terukur, SCNR M1 memang **menurun** sepanjang episode (median 17,2 dB
di t = 0 menjadi ~9,4 dB di t = 20 dan 7,3 dB di t = 48), sementara B2 yang
menghitung ulang fasanya dari geometri tiap langkah bertahan di 34,7 dB.

### Temuan: A1 ambruk setelah puncaknya (dan model akhir yang dilaporkan)

Ketiga seed A1 ambruk dari ~8,1 ke 4,0 antara 0,45 dan 0,8 juta langkah, lalu
pulih sebagian ke 5,4-6,4. Rate-nya TIDAK berubah (8,4 sebelum dan sesudah);
yang hilang hanya sensing (deteksi 0,95 -> 0,55). Jadi kebijakan akhir bukan
hasil tukar-tambah yang rasional, melainkan degradasi.

Konsekuensinya: menyimpan dan melaporkan **model akhir** membuat A1 dilaporkan
2,7 poin di bawah yang benar-benar dicapainya. Pemilihan model pada split val
adalah praktik baku dan §6.1 memang menyediakan val untuk itu.

Kendalanya teknis: `CheckpointCallback` saat ini tidak menyimpan `VecNormalize`
bersama checkpoint, sedangkan `obs_rms` terus berubah selama pelatihan.
Terukur pada A1 seed 0 di 350 rb: dengan statistik SAAT ITU reward +8,220;
dengan statistik AKHIR +7,180 (deteksi tetap 0,960, yang turun rate-nya
8,41 -> 7,35). Jadi pemilihan checkpoint butuh `save_vecnormalize=True` dan
pelatihan ulang; tanpa itu ada kerugian sekitar 1 poin.

### E4b (Gamma = 10 dan 16): belum konvergen

| config | reward M1 | min rate | deteksi | ekor |
|---|---|---|---|---|
| Gamma = 10 | +6,044 | 8,40 | 0,603 | +2,09% (belum) |
| Gamma = 13 | +3,783 | 8,26 | 0,408 | -1,46% (konvergen) |
| Gamma = 16 | +2,808 | 8,08 | 0,346 | +7,85% (belum) |

Arahnya benar untuk F8 (deteksi naik saat Gamma turun), tetapi dua dari tiga
titik belum konvergen pada 1e6 langkah.

### Operasional

* **Paralelisme terukur:** JOBS=1 memberi 2.069 langkah/detik; JOBS=3 memberi
  1.704 per run = 5.112 agregat; **JOBS=4 gagal** — keempatnya mati dengan
  "The paging file is too small" saat mengimpor torch (36 proses sekaligus,
  masing-masing menarik torch lewat `stable_baselines3/__init__.py`).
* **JOBS=4 yang gagal meracuni percobaan berikutnya.** Yang mati adalah proses
  PEKERJA; induknya menggantung menunggu pipa yang tidak pernah menjawab.
  **29 proses yatim bertahan memegang 16 GB selama 1 jam 40 menit tanpa gejala
  apa pun** selain log yang berhenti bertambah, dan membuat antrean JOBS=3
  berikutnya ikut gagal. Bila sebuah run mati dengan MemoryError, periksa
  proses yatim sebelum mencoba lagi.
* **Jangan menyunting skrip shell selagi ia berjalan.** bash membaca skrip
  berdasarkan offset byte; menambah 12 baris di tengah jalan membuat antrean
  mati di run ke-13 dengan `local: can only be used in a function`. Run yang
  sudah berjalan tidak terpengaruh.
* Waktu: M1/A1/Gamma-sweep 9,4 menit per run (1.775 langkah/detik); **M2 16,3
  menit** (1.025 langkah/detik) karena observasinya 3,2x lebih besar
  (558 x 4 lawan 174 x 4). Catat untuk T3 (biaya komputasi, E6).

---

## 2026-11-12 — Fase 5 dijalankan ulang: 21 run, Gate 5 lolos di kelima config

Antrean 21 run (base × 3 metode × 3 seed; κ = 0,25 dan 0,50 × 3 seed; Γ = 10
dan 16 × 3 seed pada 2 juta langkah) selesai dalam **92 menit** pada JOBS=3,
nol kegagalan. Commit kode `d553599`, basis data kanal `6949e64b5418` (tidak
ada ray tracing ulang: `channel_config_hash` tidak berubah).

### (a) Model yang dilaporkan sekarang checkpoint terbaik di val

`save_vecnormalize=True` pada checkpoint, lalu `select_best()` menyalin
pasangan (model, statistik VecNormalize) terbaik ke `model_best.zip` dan
`vecnormalize_best.pkl`. Diverifikasi memuat ulang persis: selisih
**0,00e+00** antara nilai yang tercatat saat pelatihan dan nilai yang dihitung
ulang dari berkas. Tanpa statistik yang cocok kerugiannya terukur ~1 poin
(A1 seed 0: +8,220 menjadi +7,180). `best_timesteps` masuk `done.json`.

Jarak puncak–akhir terukur: A1 +1,78 / +2,56 / +2,74 poin; M1 +0,12…+0,50;
M2 +0,01…+0,58. Satu kasus batas ikut teruji: Γ = 16 seed 0 terbaik di
langkah 2.002.944, yaitu evaluasi **sesudah** pembaruan PPO terakhir, yang
ada di `model.zip` dan bukan di checkpoint bernama sama.

### (b) Sapuan κ: ukuran langkah bukan penyebabnya

| κ | reward/langkah | deteksi | simpangan baku antar-seed |
|---|---|---|---|
| 0,10 | **+4,098** | 0,440 | 0,255 |
| 0,25 | +3,873 | 0,404 | 0,010 |
| 0,50 | +3,782 | 0,401 | 0,075 |

Menaikkan κ lima kali lipat — dari 10 langkah menjadi 2 langkah untuk
menggeser satu elemen sejauh π, yaitu dari 29% panjang episode menjadi 6% —
**tidak memperbaiki pemenuhan SCNR sama sekali**, malah sedikit menurun.
Dengan λ, geometri, dan anggaran langkah yang sama, A1 (fasa absolut)
mencapai deteksi 0,952. Ini menutup pertanyaan yang dibuka 2026-11-11 (k):
yang mengikat adalah **parameterisasi fasa inkremental**, bukan κ dan bukan λ.

κ besar berguna untuk hal lain: ragam antar-seed turun dari 0,255 menjadi
0,010, yaitu konvergen lebih cepat dan lebih seragam ke dataran yang sedikit
lebih rendah. Layak disebut di §5.3 sebagai pertukaran, bukan sebagai
kegagalan.

### (c) Γ pada 2 juta langkah

| Γ (dB) | M1 | deteksi | B1 | B2 | simpangan baku M1 |
|---|---|---|---|---|---|
| 10 | +6,198 | 0,617 | +0,970 | +2,264 | 0,475 |
| 13 | +4,098 | 0,440 | −0,750 | +2,261 | 0,255 |
| 16 | +3,159 | 0,354 | −2,881 | +2,259 | 0,941 |

Ketiganya sekarang konvergen sebagai rata-rata (ekor −0,20% / −1,46% /
−2,56%), berbeda dari 1 juta langkah yang menyisakan +2,09% dan +7,85%.

**Γ = 16 tidak stabil antar-seed:** +4,380 / +3,009 / +2,089; seed 2 jatuh di
bawah B2 (+2,259) dan seed 0 belum konvergen walau 2 juta langkah. Ini harus
muncul di F8 sebagai batas ambang yang masih bisa dipenuhi, bukan ditutup oleh
rata-rata.

### (d) A1 berosilasi — angkanya puncak, bukan dataran

Ketiga seed A1 gagal kriteria ekor dengan +32%. Kurva val seed 0 (reward per
langkah, ribu langkah):

```
0:+0,53  150:+4,58  250:+7,01  350:+8,22  450:+7,51  550:+7,24
650:+5,47  750:+3,84  850:+4,54  950:+6,02  1003:+6,44
```

Naik ke puncak di 350 ribu, ambruk 4,4 poin sampai 750 ribu, lalu pulih
sebagian. Itu osilasi, bukan konvergensi. Angka A1 yang dilaporkan (+8,128)
adalah puncak dan **harus ditulis demikian di paper**, dengan kurvanya di F4.
M1 dan M2 jauh lebih tenang dan benar-benar mendatar.

### (e) Terbuka — keputusan desain, perlu persetujuan

A1 mengalahkan M1 dua kali lipat (+8,128 lawan +4,098; deteksi 0,952 lawan
0,440) dengan λ, geometri, dan anggaran langkah yang sama, dan selisihnya
seluruhnya pada sensing: rate minimum keduanya ~8,2–8,4. Pilihannya:

1. M1 tetap metode utama, A1 sebagai batas atas yang menunjukkan harga
   kendala inkremental. Jujur, tetapi metode utama paper kalah dari
   pembandingnya sendiri.
2. A1 menjadi metode utama, inkremental menjadi studi ablasi tentang biaya
   kendala perangkat keras. Perlu alasan fisik mengapa fasa absolut per
   langkah masuk akal untuk RIS nyata.

Belum diputuskan.

## 2026-11-12 — Fase 6: evaluasi set test (E3, E4a, E4b, E5, E6), Gate 6 lolos

Set test disentuh untuk pertama kalinya. Seluruh penyetelan sudah beku
sebelumnya: ρ dan ω untuk B1/B2 dari grid val, checkpoint agen dari val (§6.1).
Keduanya dicatat ulang di `results/eval/<hash>/meta.json`.

### (a) B3/B4 tidak bisa lewat env apa adanya — ditambahkan `perfect_csi`

§6.2 memberi B3/B4 "CSI dan posisi sempurna", tetapi `env.step` **selalu**
membangun precoder dari `h_hat` ber-NMSE ε dan beam sensing dari posisi
tracker. Menjalankan fasa B3 lewat env tanpa perubahan akan mengukur B3 yang
dilumpuhkan, bukan B3.

Ditambahkan `EnvConfig.perfect_csi` (default **mati**). Saat menyala,
`_estimate_channel` mengembalikan kanal sebenarnya dan
`_estimated_target_channel` mengembalikan `target_g` sebenarnya — persis yang
dipakai `common.evaluate_decision` ketika `g_hat_tgt is None`. Agen dan B1/B2
tidak pernah menyalakannya; ada tes yang menjaganya tetap mati secara default.

**Verifikasi silang:** B3 lewat env memberi **+11,564** lawan **+11,571** di
mesin snapshot — selisih 0,06%, seluruhnya dari pemotongan bobot daya ke kotak
aksi env ([-1, 1] pada `p_raw`, 8,8% entri terpotong). Dua jalur hitung yang
berbeda bertemu di angka yang sama; tidak ada yang perlu diubah di Oracle-GD.

### (b) Panjang episode TIDAK bergantung pada keputusan

`truncated` hanya membaca `target_in_roi` milik lintasan. Jadi semua metode
berjalan pada langkah yang sama persis — yang membuat perbandingannya adil,
dan yang memungkinkan B3 mengoptimalkan seluruh 1.846 langkah set test
sekaligus (8,7 detik di GPU, sekali, dipakai ulang untuk ketiga seed derau).
Komentar lama di `env_policy.py` dan `rollout.py` mengklaim sebaliknya;
keduanya diperbaiki. Ada tes yang mencocokkan `episode_length` dengan env pada
seluruh 50 lintasan test.

### (c) T2 — hasil utama set test (Γ = 13 dB, P_max 30 dBm)

| metode | episode | reward/langkah | rate min | pemenuhan SCNR | durasi track (s) | galat trk (m) |
|---|---|---|---|---|---|---|
| B1 | 150 | −1,120 | 4,024 | 0,353 | 3,11 | 1,07 |
| B2 | 150 | +2,143 | 2,149 | 0,997 | 3,69 | 0,05 |
| B3 | 150 | **+11,542** | 11,542 | 1,000 | 3,69 | 0,18 |
| B4-D5 | 150 | +8,454 | 8,982 | 0,865 | 3,69 | 0,18 |
| B4-D10 | 150 | +7,840 | 8,481 | 0,852 | 3,69 | 0,19 |
| M1 | 450 | +3,590 | 8,183 | 0,398 | 3,09 | 1,05 |
| M2 | 450 | +3,603 | 8,438 | 0,380 | 3,02 | 1,17 |
| A1 | 450 | **+8,334** | 8,456 | 0,964 | 3,69 | 0,11 |

**A1 jatuh di antara B4-D5 dan B4-D10.** Artinya kebijakan yang hanya melihat
observasi parsial setara dengan oracle ber-CSI-sempurna yang keputusannya
ditahan 5–10 langkah. Itu kalimat yang bisa dibawa ke paper.

Val → test tidak menunjukkan overfitting: A1 +8,128 → +8,334; M1 +4,098 →
+3,590 (val dan test memang lintasan berbeda).

### (d) E6 — ini argumen biaya yang sebenarnya, dan hampir salah dilaporkan

| | waktu per keputusan |
|---|---|
| B2 geometris | 0,084 ms (CPU) |
| **M1** | **0,144 ms** (CPU, observasi 696) |
| M2 | 0,163 ms (CPU, observasi 2232) |
| A1 | 0,141 ms (CPU) |
| **B3 daring** | **2.054 ms** (GPU, 300 iterasi × 4 restart) |
| B3 teramortisasi | 3,28 ms (1.846 langkah dibatch sekaligus) |

B3 daring bukan sekadar 14.296× lebih mahal daripada M1 — pada Δt = 0,1 s ia
**20× lebih lambat daripada waktu nyata**, jadi ia tidak bisa menjadi
pengendali sama sekali. Angka 3,28 ms adalah biaya teramortisasi cara kerja
acuan **offline**; melaporkan hanya itu akan membuat oracle tampak layak pakai.
Keduanya dilaporkan, dengan bedanya dijelaskan.

Latihan: M1 9,5 menit, M2 16,3 menit, A1 9,4 menit per seed (CPU).
Prakomputasi ray tracing 8,7 menit (dari Fase 2, **tidak** diukur ulang).

### (e) E4a — pemenuhan SCNR M1 terikat DAYA, bukan kecepatan

| P_max (dBm) | 20 | 25 | 30 | 35 | 40 |
|---|---|---|---|---|---|
| M1 pemenuhan | 0,063 | 0,208 | 0,398 | 0,617 | 0,820 |
| A1 pemenuhan | 0,709 | 0,897 | 0,964 | 0,990 | 0,998 |
| M1 rate min | 6,13 | 7,36 | 8,18 | 8,67 | 8,87 |

Kecepatan target hampir tidak berpengaruh: M1 memberi 0,411 / 0,385 / 0,404
pada kelompok 1–3, 4–7, 8–10 m/s, dan hanya rate yang turun sedikit di
kelompok tercepat (8,26 → 7,92). Jadi kesulitan M1 bukan "mengejar target
cepat" melainkan menegakkan kendala sensing dengan anggaran daya yang ada.
Kelompok kecepatan dihitung dengan memilah hasil E3, bukan rollout baru —
hasilnya identik dengan biaya nol.

### (f) E5 — ablasi di test sejalan dengan val

| varian | reward/langkah | rate min | pemenuhan SCNR |
|---|---|---|---|
| M1 κ = 0,10 | +3,590 | 8,18 | 0,398 |
| M1 κ = 0,25 | +3,353 | 8,34 | 0,375 |
| M1 κ = 0,50 | +3,397 | 8,39 | 0,367 |
| M2 (CSI penuh) | +3,603 | 8,44 | 0,380 |
| A1 (absolut) | **+8,334** | 8,46 | **0,964** |

Pemenuhan SCNR menurun monoton terhadap κ dan tidak pernah mendekati A1.
Urutan reward κ = 0,25 dan 0,50 terbalik dibanding val, tetapi selisihnya
(0,04) jauh di dalam ragam antar-seed — tidak ada yang bisa disimpulkan dari
urutan itu, dan tidak perlu.

### (g) Dua peringatan statistik yang harus masuk paper

1. **Cohen's d di sini tidak berarti apa-apa.** Uji antar-seed menghasilkan
   d = 10–73. Dengan n = 3 dan kebijakan yang sangat konsisten, simpangan baku
   antar-seed nyaris nol sehingga pembaginya runtuh. Yang dilaporkan adalah
   selisih dengan CI bootstrap; d jadi catatan kaki, bukan klaim.
2. **Tiga "seed" baseline bukan tiga kebijakan**, melainkan tiga undian derau
   atas kebijakan yang sama, sementara tiga seed agen adalah tiga kebijakan
   berbeda. Uji M1 lawan B2/B4 karena itu membandingkan dua jenis ragam yang
   berbeda. Dinyatakan di §9, bukan didiamkan.

### (h) Durasi track memisahkan dua kelompok, tidak memeringkat di dalamnya

B2, B3, B4, dan A1 **tidak pernah** kehilangan track (100% episode tersensor
di panjang episode); B1, M1, dan M2 kehilangannya di sekitar 28% episode.
Metrik ini karena itu berguna sebagai pemisah kasar, bukan sebagai peringkat
halus. Fraksi tersensor ikut dilaporkan di T2.

### (i) Catatan utang teknis: `config_hash` memakai SELURUH config

Menambah satu kunci ke blok `evaluation:` akan mengubah `config_hash` dan
membuat 21 run pelatihan yang sudah ada "hilang", padahal blok itu tidak
memengaruhi pelatihan sama sekali. Masalah yang sama sudah dipecahkan untuk
kanal lewat `channel_config_hash` dengan daftar bagian yang eksplisit.

Di Fase 6 ini **tidak ada** kunci config baru yang dibutuhkan: kelompok
kecepatan sudah ada di `mobility.speed_eval_bins_mps` dan sapuan P_max di
`evaluation.p_max_eval_dbm`. Jadi tidak ada yang diubah. Tetapi `training_config_hash`
yang sejajar dengan `channel_config_hash` layak dipertimbangkan di Fase 7 —
beserta cara memindahkan direktori hasil tanpa merusak salinan `config.yaml`
yang menjadi bukti provenans tiap run.

## 2026-11-12 — Fase 7: satu perintah untuk semua gambar dan tabel, Gate 7 lolos

### (a) Cek silang persamaan menemukan dua fungsi rumus tanpa tes

`scripts/check_equations.py` membaca docstring dengan `ast`, bukan regex atas
seluruh berkas — regex ikut menangkap `(E9)` di komentar dan melaporkan
"ada implementasinya" untuk berkas yang hanya kebetulan menyebutnya.

Dua celah nyata, keduanya ditutup:

* **`rzf_directions` (E3)** tidak punya tes. Docstring-nya sendiri
  memperingatkan bahwa memakai `A^H A` alih-alih `A^T conj(A)` adalah
  "kesalahan yang mudah terjadi dan tidak terdeteksi oleh uji daya mana pun".
  Tes barunya membuktikan tepat itu: varian yang benar menolkan interferensi
  sampai 1e-9, varian `A^H A` tidak.
* **`dominant_right_singular` (E2/E5)** tidak punya tes. Sekarang diuji
  terhadap SVD numerik (‖G a_bar‖ = σ_max), terhadap 50 arah acak, dan
  terhadap varian tanpa konjugat — yang memang terbukti lebih buruk.

Pemisahan yang perlu dibuat: docstring **fungsi** yang menyebut `(E#)` adalah
implementasi dan wajib punya tes; docstring **modul** menandai di mana
persamaan itu tinggal. Tanpa pemisahan itu, tiap modul yang menyebut (E9) di
pengantarnya tampak sebagai implementasi tak-teruji. `validate_analytic.py`
kini menulis `(E0)` sesuai konvensi CLAUDE.md, bukan `E0` tanpa kurung.

Hasil akhir: 10 persamaan, 28 fungsi, semuanya punya tes. (E8) dikecualikan
dengan alasan tertulis di skrip: ia kendala keras §3.6 yang dilonggarkan
menjadi (E9), dan tidak ada fungsi yang menghitungnya sendiri.

### (b) E0 dijalankan ulang; E1 sengaja tidak

Hasil E0 yang ada berada di `results/e0/1365548d0387/`, sementara
`config_hash` sekarang `2ac2654fe51c`. Selisihnya **tiga kunci**:
`ray_tracing.deterministic`, `.refraction`, `.seed` — semuanya ditambahkan
setelah E0 dijalankan. Dijalankan ulang: **angkanya identik** (terburuk
0,0144 dB, kalibrasi +1,05 dB, sebaran 0,00 dB). Ketiga kunci itu memang tidak
mengubah fisika, tetapi sekarang hash-nya cocok.

E1 **tidak** dijalankan ulang. Selisih config-nya hanya `reward.lambda`
(1,0 → 10,0 dari Fase 3), yang tidak dipakai E1 sama sekali — E1 adalah peta
cakupan dan SNR radar, tanpa reward. Menjalankannya ulang berarti ray tracing
tanpa guna.

### (c) Utang `config_hash` ditangani di sisi pembaca, bukan dengan menulis ulang sejarah

Masalah yang dicatat 2026-11-12 (i) muncul langsung di Fase 7: `config_hash`
dihitung dari SELURUH config, jadi menambah satu kunci tak relevan membuat
hasil yang masih sah tampak hilang.

Yang **tidak** dilakukan: mengganti nama direktori hasil lama. Tiap direktori
run menyimpan salinan `config.yaml`-nya sendiri sebagai bukti provenans;
mengganti hash-nya sementara salinan itu tetap yang lama akan memalsukan bukti
tersebut.

Yang dilakukan: `make_figures.py` membandingkan `config_used.json` tiap
kandidat dengan config sekarang dan menerima yang selisihnya **seluruhnya**
berada di daftar kunci tak relevan per eksperimen. Arahnya aman — kunci baru
yang belum diklasifikasikan membuat kandidat DITOLAK, bukan diterima — dan
kalau tidak ada yang lolos ia berhenti sambil mencetak selisihnya.

### (d) Dua bug sendiri yang tertangkap saat membangun

* **`both()` menganggap `out_path` selalu argumen terakhir.** Tidak:
  `plot_f6_episode` dan `plot_f7_pmax_speed` menaruhnya di argumen kedua,
  sehingga sebuah `Path` diteruskan ke `trajectory_index`. Diganti dengan
  closure yang menerima jalur.
* **Escape LaTeX menebak dari isi sel.** Aturan "lewatkan kalau diapit `$`"
  menghancurkan label campuran seperti `$M$ (baris $\times$ kolom)`, yang
  berawalan `$` tetapi tidak berakhiran `$`. Diganti penanda eksplisit
  `Raw`: apa pun yang ditulis di `tables.py` boleh `Raw`, apa pun yang datang
  dari file hasil selalu di-escape. Tanda minus juga ditulis `$-$`, bukan `-`,
  karena di mode teks LaTeX `-` adalah tanda hubung dan jauh lebih pendek —
  cacat kecil yang pada tabel otomatis akan muncul di setiap baris negatif.

### (e) Gate 7 — LOLOS

Diperiksa di direktori sementara yang **kosong**, bukan menimpa
`results/paper/`: menulis ke direktori lama akan lolos walau sebuah gambar
diam-diam berhenti dibuat, karena berkas lamanya masih di sana.

| kriteria | hasil |
|---|---|
| cek silang persamaan | 10 persamaan, 28 fungsi, semuanya punya tes |
| satu perintah membuat ulang | 9 gambar (PNG + PDF) + 4 tabel LaTeX |
| pohon git bersih | `git status --porcelain` |

### (f) Percobaan menstabilkan A1 — kedua obat standar gagal

Disetujui pengguna. Dua hipotesis diuji berdampingan, 3 seed A1 masing-masing,
**tanpa menyentuh `configs/base.yaml`** (21 run yang ada tetap sah; dukungan
`target_kl` ditambahkan lewat `ppo_cfg.get(...)`, sehingga absennya di base
berarti `None` dan perilaku base tidak berubah).

| setelan | puncak val | langkah puncak | akhir | ekor |
|---|---|---|---|---|
| base | +8,22 / +8,03 / +8,14 | 350–450k | +6,44 / +5,46 / +5,40 | +32% (ketiganya) |
| `target_kl: 0.02` | +8,13 / +8,19 / +8,36 | 350–450k | +6,03 / +5,15 / +4,32 | +20% / −50% / −39% |
| `ent_coef: 0.003` | +3,95 / +2,03 / +4,03 | 950k–1e6 | +3,52 / +1,78 / +3,60 | +89% / +84% / +34% |

**`target_kl` tidak menyentuh masalahnya.** Puncak sama, waktunya sama,
ambruknya tetap. Yang berubah hanya di leg mana kurva kebetulan berakhir — dan
dua seed "lolos" kriteria ekor dengan rasio −50% dan −39%, persis kasus yang
sudah diperingatkan di `run_gate5_check.py`: kurva yang sedang MENURUN lolos
ambang "naik < 2%" dan harus dibaca sebagai ketidakstabilan.

Efek sampingnya menarik dan tidak relevan untuk keputusan: `target_kl`
membuat pelatihan **1,8× lebih cepat** (3.194 lawan 1.769 langkah/detik)
karena loop epoch berhenti lebih awal.

**`ent_coef: 0.003` merusaknya.** Puncak jatuh dari +8,2 ke +4,0. Pada ruang
aksi kontinu 67 dimensi, entropi sebesar itu menahan kebijakan terlalu
stokastik. Ia tidak ambruk — karena tidak pernah sampai ke ketinggian yang
bisa diambruki.

**Kesimpulan:** ambruknya A1 bertahan terhadap dua obat standar, jadi ia bukan
artefak ukuran langkah PPO dan bukan akibat kebijakan mengerucut terlalu cepat.

**Hipotesis yang tersisa, belum diuji karena menyentuh reward:** hinge
λ[Γ−SCNR]₊/10 bernilai **nol** begitu kendala terpenuhi. Setelah kebijakan
mencapai pemenuhan tinggi, gradien yang MEMPERTAHANKAN SCNR ikut hilang, dan
kebijakan hanyut didorong suku laju sampai pemenuhannya pecah. Cocok dengan
gejalanya: selama ambruk, laju tidak berubah sedikit pun — hanya deteksi yang
jatuh dari 0,95 ke 0,55. Mengujinya berarti mengubah (E9); tidak dilakukan
tanpa persetujuan.

**Akibatnya:** A1 tetap dilaporkan pada checkpoint terbaik di val, kurvanya
ditampilkan apa adanya di F4, dan ketidakstabilannya dinyatakan terbuka
sebagai keterbatasan — opsi 3 di laporan keputusan, bukan opsi 2.

---

## 2026-11-12 — Fase 8: pembingkaian ulang (A1 metode utama), baseline B0, E1 ulang

### Persetujuan yang dicatat

Seluruh perubahan desain di bawah ini **disetujui oleh pengguna pada
2026-11-12**, diberikan sebagai satu instruksi Fase 8:

1. **A1 (PPO-PO, fasa absolut) menjadi METODE UTAMA.** M1 dan sapuan κ
   menjadi ablasi "parameterisasi fasa inkremental"; M2 tetap ada sebagai
   varian inkremental ber-CSI-penuh. Kunci metode dan nama direktori hasil
   **tidak** diubah — hanya peran, urutan, dan label tampilan.
2. **§5.3 mendapat paragraf justifikasi fisik fasa absolut per frame**:
   pembatasan inkremental adalah pilihan desain RL, bukan batasan perangkat
   keras. Angka waktu penyetelan elemen ditandai
   `[RUJUKAN PERLU DIVERIFIKASI]`, tidak dikarang.
3. **Teks hipotesis RQ tidak diubah**; ditambahkan §1.1 "Hasil terhadap
   hipotesis" yang menyatakan apa adanya (A1 ≈ 73% rate minimum B3, bukan
   target 80%; A1 di antara B4-D5 dan B4-D10).
4. **Baseline B0 "No-RIS"** ditambahkan dengan CSI langsung sempurna.
5. **A1-FullCSI** ditambahkan sebagai ablasi observasi, dan **A1 dilatih
   ulang pada Γ = 10 dan 16 dB** (1e6 langkah).
6. **F2 diganti menjadi dua panel** dari data E1; F2b diserap.

Yang **tidak** disetujui dan **tidak** diubah: reward (E9), λ, κ bawaan,
geometri scene, basis data kanal, dan hiperparameter PPO. `configs/base.yaml`
tidak disentuh sama sekali, sehingga 21 run Fase 5 tetap sah dan
`config_hash` base tetap `2ac2654fe51c`.

### Langkah A — E1 dijalankan ulang pada geometri final (GPU)

Hasil E1 yang dipakai Fase 1–7 berasal dari hash `68bdfb2f1292`, yaitu config
sebelum `reward.lambda` dinaikkan. Ia dijalankan ulang di config sekarang
(`2ac2654fe51c`) dan diperluas: selain penguatan komunikasi MRT-lawan-MRT,
kini dihitung juga **SCNR ideal sistem-lawan-sistem** — tiap sistem memakai
beam terbaiknya sendiri, bukan precoder `a_bar` yang sama untuk keduanya.

| besaran @ P_max = 30 dBm | lewat RIS | langsung saja |
|---|---|---|
| penguatan komunikasi (MRT vs MRT) | median **+12,0 dB**, p10 +7,3 dB, 93,2% ROI ≥ 6 dB, RIS menang di **100%** titik | — |
| SCNR ideal, median | **42,2 dB** | 16,2 dB |
| SCNR ideal, fraksi ≥ Γ = 13 dB | **1,000** | **0,645** |

Gate 1 tetap **LOLOS** pada kriteria yang sama (`scnr` berbasis `a_bar`
sengaja dibiarkan sebagai besaran yang digate, supaya riwayat gate tetap bisa
dibaca).

**Temuan yang bertentangan dengan dugaan:** tanpa RIS sama sekali, SCNR ideal
sudah memenuhi Γ di **64,5%** titik ROI pada 30 dBm — jalur sensing jauh
lebih tidak bergantung pada RIS daripada jalur komunikasi. Penyebabnya
terbaca dari anggaran: η = +32,3 dB dan L = 4096 (+36,1 dB) memberi margin
besar yang masih tersisa walau jalur langsung lemah. Yang menjadi pengikat di
sistem nyata karena itu bukan anggaran daya sensing melainkan **ke mana beam
diarahkan**, yang pada B0 dibangun dari h_{d,t} sebenarnya (CSI sempurna) dan
pada metode terapan dari estimasi tracker lewat RIS. B0 di set test
mengukur selisih itu secara langsung.

### Langkah C2 — B0 "No-RIS"

`EnvConfig.no_ris` (default **mati**) menghapus kaskade RIS dari (E2) dan
(E5): h_e = h_d, c = h_{d,t}, b = h^{(r)}_{d,t}. Dipasangkan dengan
`perfect_csi=True`, B0 menjadi batas atas sistem tanpa RIS: RZF dari h_d
sebenarnya dan w_s ∝ h_{d,t}^*/‖h_{d,t}‖. ρ dan bobot daya disapu di grid
val, memakai kembali `baselines.geometric.weight_grid` ketimbang menambah
kunci config baru — menambah kunci akan mengganti `config_hash` seluruh
proyek demi tiga angka.

Clutter **tidak** ikut dihapus: H_c adalah jalur langsung BS-tx → BS-rx dan
tidak melewati RIS; menghapusnya akan memberi B0 keuntungan yang tidak ada
hubungannya dengan RIS.

`evaluate_decision` ikut mendapat argumen `no_ris`, supaya B0 bisa
dibandingkan antara jalur env dan jalur snapshot seperti B2 dan B3 —
`tests/test_b0_no_ris.py` menuntut kesamaan sampai rel = 1e-9, membuktikan
h_e sama **persis** dengan h_d, dan membuktikan fasa RIS tidak berpengaruh
sama sekali pada B0.
