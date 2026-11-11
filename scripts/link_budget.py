"""Link budget kasar ruang bebas untuk RIS-ISAC (EXPERIMENT_DESIGN.md §3.8).

Asumsi: Friis per hop, fokus RIS ideal (penjumlahan koheren M elemen),
pola elemen RIS dengan gain pi (elemen lambda/2), gain array BS = N,
seluruh daya untuk satu fungsi (rho = 1), tanpa clutter.
Hanya untuk memilih geometri awal; angka sebenarnya dari ray tracing (E1).

Contoh: python scripts/link_budget.py --d-bs-ris 20 --m 64 --L 4096
"""
import argparse
import numpy as np


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fc", type=float, default=3.5e9)
    ap.add_argument("--bw", type=float, default=20e6)
    ap.add_argument("--nf-db", type=float, default=7.0)
    ap.add_argument("--p-dbm", type=float, default=30.0)
    ap.add_argument("--nt", type=int, default=8)
    ap.add_argument("--nr", type=int, default=8)
    ap.add_argument("--rcs", type=float, default=1.0)
    ap.add_argument("--d-bs-ris", type=float, nargs="+", default=[20.0, 30.0])
    ap.add_argument("--m", type=int, nargs="+", default=[64, 144])
    ap.add_argument("--d-ris-tgt", type=float, nargs="+", default=[10.0, 20.0, 30.0])
    ap.add_argument("--L", type=int, nargs="+", default=[256, 4096, 16384])
    a = ap.parse_args()

    lam = 3e8 / a.fc
    noise_dbm = -174 + 10 * np.log10(a.bw) + a.nf_db
    ge_db = 20 * np.log10(np.pi)  # gain elemen RIS pada dua hop (pi * pi)
    eta_db = 10 * np.log10(4 * np.pi * a.rcs / lam**2)  # (E6)

    def hop_db(d):
        return 20 * np.log10(lam / (4 * np.pi * d))

    def cascade_db(d1, d2, m):
        return hop_db(d1) + hop_db(d2) + 20 * np.log10(m) + ge_db

    print(f"lambda={lam:.4f} m, noise={noise_dbm:.1f} dBm, eta={eta_db:.1f} dB")
    print("d_bs_ris  M  d_ris_tgt | SNR_comm | " + " ".join(f"SNR_radar(L={L})" for L in a.L))
    for d1 in a.d_bs_ris:
        for m in a.m:
            for d2 in a.d_ris_tgt:
                tx = a.p_dbm + 10 * np.log10(a.nt)
                comm = tx + cascade_db(d1, d2, m) - noise_dbm
                echo = tx + cascade_db(d1, d2, m) + eta_db + cascade_db(d2, d1, m) + 10 * np.log10(a.nr)
                radar = [echo + 10 * np.log10(L) - noise_dbm for L in a.L]
                print(f"{d1:7.0f} {m:4d} {d2:9.0f} | {comm:8.1f} | " + " ".join(f"{r:16.1f}" for r in radar))


if __name__ == "__main__":
    main()
