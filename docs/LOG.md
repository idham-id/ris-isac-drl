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
