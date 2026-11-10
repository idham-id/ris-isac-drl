# Catatan Keputusan dan Masalah

Entri terbaru di atas. Setiap entri bertanggal dan menyebut fase/gate terkait.

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
