# RIS-ISAC-DRL

Deep reinforcement learning untuk RIS-assisted integrated sensing and communication pada skenario NLoS site-specific, dengan kanal dari NVIDIA Sionna RT.

## Isi paket awal
- `docs/EXPERIMENT_DESIGN.md` — rancangan eksperimen lengkap (model sistem, MDP, baseline, eksperimen E0–E7, parameter).
- `docs/TASKS.md` — langkah implementasi per fase dengan kriteria lolos (gate).
- `CLAUDE.md` — aturan proyek untuk Claude Code.
- `configs/base.yaml` — semua parameter bawaan.

## Cara memulai dengan Claude Code
1. Ekstrak folder ini dan buka di terminal: `cd ris-isac-drl && git init`.
2. Jalankan `claude` di folder tersebut. Claude Code otomatis membaca `CLAUDE.md`.
3. Mulai dengan perintah seperti:
   > Baca docs/EXPERIMENT_DESIGN.md dan docs/TASKS.md, lalu kerjakan Fase 0. Laporkan hasil gate sebelum lanjut.
4. Ulangi per fase. Tinjau hasil setiap gate sebelum memberi izin lanjut.

## Kebutuhan
- GPU NVIDIA sangat disarankan untuk prakomputasi ray tracing dan pelatihan.
- Dua environment Python: utama (Sionna RT terbaru) dan validasi (Sionna 0.19.2).
