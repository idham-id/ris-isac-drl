# RIS-ISAC-DRL (versi ramping)

Deep reinforcement learning untuk RIS-assisted integrated sensing and communication pada skenario NLoS site-specific, dengan kanal dari NVIDIA Sionna RT. Dirancang untuk selesai dalam ±8 minggu di PC dengan GPU 12 GB.

## Isi paket awal
- `docs/EXPERIMENT_DESIGN.md` — rancangan eksperimen v0.2-lean: model sistem, MDP, baseline, eksperimen E0–E8 dengan prioritas, parameter, link budget.
- `docs/TASKS.md` — jadwal 8 minggu, fase, gate, dan titik keputusan.
- `CLAUDE.md` — aturan proyek untuk Claude Code.
- `configs/base.yaml` — semua parameter bawaan.
- `scripts/link_budget.py` — hitungan link budget kasar untuk memilih geometri.

## Cara memulai dengan Claude Code
1. Ekstrak, lalu `cd ris-isac-drl && git init`.
2. Jalankan `claude` di folder tersebut. `CLAUDE.md` dibaca otomatis.
3. Perintah pertama yang disarankan:
   > Baca docs/EXPERIMENT_DESIGN.md dan docs/TASKS.md, lalu kerjakan Fase 0 dan Fase 1. Laporkan hasil Gate 0 dan Gate 1 beserta peta F2 sebelum lanjut.
4. Ulangi per fase. Tinjau setiap gate sebelum memberi izin lanjut.

## Kebutuhan
- GPU NVIDIA (12 GB cukup dengan pengaturan batch di config) untuk prakomputasi ray tracing.
- CPU multi-core untuk pelatihan PPO.
- Satu environment Python (Sionna RT versi terbaru).
