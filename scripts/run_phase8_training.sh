#!/usr/bin/env bash
# Antrean 9 run pelatihan Fase 8 (docs/TASKS.md, disetujui 2026-11-12).
#
#   JOBS=3 bash scripts/run_phase8_training.sh
#
# Rincian:
#   A1-FullCSI (ppo_full_absolute) x 3 seed pada config base, 1e6 langkah
#       -> ablasi OBSERVASI pada metode utama: A1 berbeda dari ini HANYA pada
#          mode observasi, sehingga selisihnya benar-benar harga observasi
#          parsial dan bukan campuran dengan mode fasa.
#   A1 (ppo_po_absolute) x 3 seed pada Gamma = 10 dan 16 dB, 1e6 langkah
#       -> F8 membandingkan METODE UTAMA pada tiga Gamma, bukan M1 saja.
#
# **1e6 langkah, bukan 2e6.** configs/gamma10.yaml dan gamma16.yaml menyetel
# total_timesteps = 2e6 karena kurva val M1 di situ masih menanjak pada 1e6.
# A1 tidak punya masalah itu: ketiga seed A1 pada Gamma = 13 memuncak di
# 350-450 ribu langkah lalu TURUN, jadi 2e6 hanya akan menambah 1e6 langkah di
# wilayah yang sudah lewat puncak. Anggarannya diberikan lewat --steps supaya
# config kedua Gamma tidak perlu diubah dan hasil M1 yang sudah ada tetap sah.
# Bila kurva val A1 ternyata masih menanjak di akhir, itu DICATAT dan
# dilaporkan, bukan diperpanjang diam-diam (instruksi Fase 8).
#
# Berlaku semua peringatan scripts/run_all_training.sh: JOBS=4 GAGAL di mesin
# ini ("The paging file is too small") dan meninggalkan proses yatim yang
# meracuni antrean berikutnya; JANGAN menyunting berkas ini selagi berjalan
# (bash membacanya per offset byte). Tiap run menulis done.json dan dilewati
# pada pemanggilan ulang, jadi antrean aman dihentikan di tengah.
set -u

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${PYTHON:-python}"
JOBS="${JOBS:-2}"
export PYTHONPATH="$REPO/src${PYTHONPATH:+:$PYTHONPATH}"

LOG_DIR="$REPO/results/train/logs"
mkdir -p "$LOG_DIR"

# config|method|seed|steps
queue=()
for seed in 0 1 2; do
    queue+=("base|ppo_full_absolute|$seed|1000000")
done
for config in gamma10 gamma16; do
    for seed in 0 1 2; do
        queue+=("$config|ppo_po_absolute|$seed|1000000")
    done
done

echo "Antrean ${#queue[@]} run Fase 8 | JOBS=$JOBS | log: $LOG_DIR"
start_all=$(date +%s)

launch() {
    local config="$1" method="$2" seed="$3" steps="$4"
    local log="$LOG_DIR/${config}_${method}_seed${seed}.log"
    echo "[mulai] $config $method seed $seed ($steps langkah) -> $log"
    "$PYTHON" -m risisac.train.train --config "$config" --method "$method" \
        --seed "$seed" --steps "$steps" --torch-threads 1 > "$log" 2>&1
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
    IFS='|' read -r config method seed steps <<< "$item"
    launch "$config" "$method" "$seed" "$steps" &
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
exit $(( failed > 0 ))
