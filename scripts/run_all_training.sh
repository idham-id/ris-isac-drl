#!/usr/bin/env bash
# Antrean 15 run pelatihan Fase 5 (docs/TASKS.md).
#
#   bash scripts/run_all_training.sh              # semua 15 run
#   JOBS=3 bash scripts/run_all_training.sh       # 3 run paralel
#   bash scripts/run_all_training.sh base         # hanya config base (9 run)
#
# Rincian: (M1, M2, A1) x 3 seed pada config base, lalu M1 x 3 seed pada
# Gamma = 10 dan 16 (E4b). Jumlahnya 9 + 6 = 15 run x 1e6 langkah.
#
# **Bisa dilanjutkan.** Tiap run menulis ``done.json`` saat selesai dan
# dilewati pada pemanggilan berikutnya, jadi skrip ini aman dijalankan ulang
# setelah berhenti di tengah. Untuk melatih ulang, hapus direktori run-nya.
#
# Pelatihan di CPU (CLAUDE.md). Tiap run memakai 8 env paralel + 1 thread
# torch, jadi JOBS=n berarti n*9 proses Python yang masing-masing mengimpor
# torch (impor submodul SB3 apa pun menarik `stable_baselines3/__init__.py`,
# dan itu menarik torch beserta DLL CUDA-nya).
#
# TERUKUR di mesin ini (i5-13600KF, 32 GB, 100 ribu langkah per run):
#   JOBS=1  2.069 langkah/detik
#   JOBS=3  1.704 langkah/detik per run  = 5.112 agregat (2,5x)
#   JOBS=4  GAGAL -- keempatnya mati dengan "The paging file is too small"
#           / MemoryError saat mengimpor torch (36 proses sekaligus).
# Batasnya karena itu memori commit Windows, bukan jumlah core.
#
# JOBS=4 juga MERACUNI percobaan berikutnya: yang mati adalah proses PEKERJA
# (stderr-nya ikut ke log induk, jadi tracebacknya tampak seperti milik
# induk), dan induk lalu menggantung menunggu pipa pekerja yang tidak pernah
# menjawab. Terukur 29 proses yatim bertahan memegang 16 GB, sehingga antrean
# JOBS=3 berikutnya ikut gagal walau sendirian ia berjalan mulus. Bila sebuah
# run gagal dengan MemoryError / "paging file", PERIKSA proses yatim dan
# matikan sebelum mencoba lagi:
#
#   Get-Process python* | Select-Object Id, StartTime, WorkingSet64
#
# Default JOBS=2 (18 proses, sekitar 10 GB) memberi margin; 3 terukur mampu
# di mesin bersih dan memberi 2,5x, tetapi tanpa sisa ruang.
# JANGAN MENYUNTING BERKAS INI SELAGI IA BERJALAN. bash membaca skrip secara
# malas berdasarkan OFFSET BYTE, jadi menambah baris di tengah jalan membuat
# ia melanjutkan di posisi yang bergeser. Terukur 2026-11-11: antrean berjalan
# normal sampai run ke-13 lalu mati dengan "log: unbound variable" dan
# "local: can only be used in a function" -- bash sedang membaca potongan
# tengah fungsi launch() sebagai kode tingkat atas. Run yang sudah jalan tidak
# terpengaruh (ketiganya selesai), tetapi antreannya berhenti di situ.
set -u

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${PYTHON:-python}"
JOBS="${JOBS:-2}"
STEPS="${STEPS:-}"
export PYTHONPATH="$REPO/src${PYTHONPATH:+:$PYTHONPATH}"

CONFIGS=("$@")
if [ ${#CONFIGS[@]} -eq 0 ]; then
    CONFIGS=(base gamma10 gamma16)
fi

LOG_DIR="$REPO/results/train/logs"
mkdir -p "$LOG_DIR"

queue=()
for config in "${CONFIGS[@]}"; do
    # Gamma = 10 dan 16 hanya untuk M1 (E4b); M2 dan A1 hanya di config utama.
    if [ "$config" = "base" ]; then
        methods=(ppo_po ppo_full ppo_po_absolute)
    else
        methods=(ppo_po)
    fi
    for method in "${methods[@]}"; do
        for seed in 0 1 2; do
            queue+=("$config|$method|$seed")
        done
    done
done

echo "Antrean ${#queue[@]} run | JOBS=$JOBS | log: $LOG_DIR"
start_all=$(date +%s)

launch() {
    local config="$1" method="$2" seed="$3"
    local log="$LOG_DIR/${config}_${method}_seed${seed}.log"
    local args=(--config "$config" --method "$method" --seed "$seed"
                --torch-threads 1)
    [ -n "$STEPS" ] && args+=(--steps "$STEPS")
    echo "[mulai] $config $method seed $seed -> $log"
    "$PYTHON" -m risisac.train.train "${args[@]}" > "$log" 2>&1
    local code=$?
    if [ $code -ne 0 ]; then
        echo "[GAGAL] $config $method seed $seed (kode $code); lihat $log"
    else
        echo "[selesai] $config $method seed $seed: $(grep -o 'selesai dalam.*' "$log" | tail -1)"
    fi
    return $code
}

failed=0
running=0
for item in "${queue[@]}"; do
    IFS='|' read -r config method seed <<< "$item"
    launch "$config" "$method" "$seed" &
    running=$((running + 1))
    if [ "$running" -ge "$JOBS" ]; then
        wait -n || failed=$((failed + 1))
        running=$((running - 1))
    fi
done
while [ "$running" -gt 0 ]; do
    wait -n || failed=$((failed + 1))
    running=$((running - 1))
done

elapsed=$(( $(date +%s) - start_all ))
printf 'Total %d run dalam %d menit; gagal: %d\n' \
    "${#queue[@]}" "$((elapsed / 60))" "$failed"
echo "Lanjutkan dengan: python scripts/run_gate5_check.py --config base"
exit $(( failed > 0 ))
