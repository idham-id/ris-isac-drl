# Metadata Zenodo untuk arsip data

Berkas ini **bukan** bagian dari kode. Isinya teks siap tempel untuk mengunggah
`dist/ris-isac-drl-data-v1.0.zip` ke Zenodo sebagai *dataset* tersendiri,
terpisah dari arsip kode yang dibuat otomatis oleh integrasi Zenodo-GitHub.

Dua DOI akan terbit, dan keduanya berbeda:

| Arsip | Cara terbit | Lisensi |
|---|---|---|
| Kode (`ris-isac-drl`) | otomatis, dari rilis GitHub `v1.0.0` | Apache-2.0 |
| Data (`ris-isac-drl-data-v1.0.zip`, 267 MB) | unggah manual lewat berkas ini | CC-BY-4.0 |

Setelah keduanya terbit, isikan ke `README.md`, `CITATION.cff`, dan ke bagian
*Data availability* naskah.

---

## Langkah unggah

1. Buka <https://zenodo.org/uploads/new> (masuk dengan akun GitHub yang sama).
2. Unggah **satu** berkas: `dist/ris-isac-drl-data-v1.0.zip`.
   SHA256 berkas itu dicetak oleh `python scripts/package_data.py`; salinan
   `SHA256SUMS` untuk seluruh isinya ada di dalam zip dan di `dist/`.
3. Isi metadata persis seperti di bawah.
4. **Jangan tekan Publish** sebelum rilis GitHub `v1.0.0` ada, karena kolom
   *Related works* menunjuk ke sana.

---

## Resource type

`Dataset`

## Title

```
Ray-traced channel database, evaluation logs and trained policies for
"Real-Time Deep Reinforcement Learning Control of RIS-Assisted Integrated
Sensing and Communication under Partial Observations"
```

## Authors (Creators)

| Nama | Afiliasi | ORCID |
|---|---|---|
| Timur, Muhammad Idham Ananta | Universitas Gadjah Mada | *(TODO: isi)* |
| Ashari, Ahmad | Universitas Gadjah Mada | *(TODO: isi)* |
| Widodo, Triyogatama Wahyu | Universitas Gadjah Mada | *(TODO: isi)* |

## Description

```
Every input and every intermediate result needed to rebuild all figures and
tables of the paper "Real-Time Deep Reinforcement Learning Control of
RIS-Assisted Integrated Sensing and Communication under Partial Observations",
without a GPU and without retraining anything.

The study places a reconfigurable intelligent surface (RIS) so that a base
station can serve two users and track a moving target in a street outside its
line of sight, and trains a proximal policy optimisation agent to set the RIS
phases, the communication-sensing power split and the user weights every
100 ms from partial observations. Channels come from a ray-traced digital twin
built with NVIDIA Sionna RT, using a hybrid per-element RIS model validated to
within 0.015 dB of the analytic cascade.

Contents (267 MB compressed, 299 MB extracted, 296 files):

* data/channels/synthetic_l/6949e64b5418.h5 - the ray-traced channel
  database: 280 trajectories and 42,000 receiver points over the synthetic
  L-shaped street, as an HDF5 file keyed by a hash of the channel-relevant
  configuration.
* results/e0/, results/e1/, results/gate3/, results/gate5/ - channel-model
  validation, scene coverage, signal-model feasibility, and training curves.
* results/eval/ - the test-set logs for five configurations: per-step and
  per-episode Parquet tables for ten methods and three training seeds, plus
  the aggregated tables reported in the paper.
* results/paper/ - the figures (PDF and PNG) and tables (LaTeX) exactly as
  they appear in the manuscript, with a manifest recording which result
  directory and which git commit produced each one.
* results/train/ - for each of 30 training runs (ten method-configuration
  pairs, three seeds each): the checkpoint selected on the validation set,
  its VecNormalize statistics, the run record, the resolved configuration,
  and the training and validation curves. Periodic checkpoints, final
  weights and TensorBoard files are deliberately excluded: they are 6.5 GB
  and no reported number is computed from them.

The analysis code that produced this archive and that reads it is released
separately under Apache-2.0 at https://github.com/idham-id/ris-isac-drl.
Extract this archive at the root of a clone of that repository, then run
"python scripts/make_figures.py --config base" to rebuild every figure and
table in about one minute on a CPU. README_DATA.md inside the archive
describes the folder structure and SHA256SUMS verifies every file.
```

## Licence

`Creative Commons Attribution 4.0 International (CC-BY-4.0)`

## Keywords

```
reconfigurable intelligent surface
integrated sensing and communication
deep reinforcement learning
proximal policy optimisation
ray tracing
digital twin
Sionna
channel database
non-line-of-sight
beamforming
```

## Related works / Related identifiers

| Relation | Identifier | Resource type |
|---|---|---|
| *is supplement to* | `https://github.com/idham-id/ris-isac-drl` | Software |
| *is supplement to* | `10.5281/zenodo.XXXXXXX` (DOI arsip kode) | Software |
| *is supplement to* | DOI naskah, setelah terbit | Publication / Journal article |
| *is derived from* | `https://github.com/NVlabs/sionna` | Software |

## Version

`1.0`

## Language

`English`

## Funding

*(TODO: isi kalau ada hibah yang harus disebut; kosongkan kalau tidak.)*

---

## Setelah kedua DOI terbit

Yang harus diperbarui, dan di mana:

1. `README.md`, bagian *Getting the data*: ganti `10.5281/zenodo.XXXXXXX`
   (kode) dan `10.5281/zenodo.YYYYYYY` (data).
2. `CITATION.cff`: buka blok `identifiers:` yang sekarang dikomentari, isi
   kedua DOI.
3. Naskah, *Data availability*: ganti placeholder dengan kedua DOI dan URL
   repo.
4. Zenodo, record data: tambahkan DOI arsip kode di *Related works* kalau
   belum sempat diisi saat mengunggah.
