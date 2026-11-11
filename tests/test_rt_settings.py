"""Anggaran jalur ray tracing (docs/EXPERIMENT_DESIGN.md §4.2).

Yang dibatasi VRAM adalah HASIL KALI ``max_num_paths_per_src * jumlah_sumber``,
karena buffer image-method berukuran hasil kali itu dikali 16 B dan tidak
mengecil bila ``rx_batch_size`` diturunkan. Pemotongan jalur tidak memunculkan
error apa pun dan pernah menjatuhkan daya sampai 58 dB, jadi perilaku
penurunan anggarannya diuji di sini, bukan diandaikan.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from risisac.channels.rt_extract import RayTracingSettings      # noqa: E402

BYTES_PER_PATH = 16


def make(per_src: int, total: int) -> RayTracingSettings:
    return RayTracingSettings(
        max_depth=5, samples_per_src=100_000, max_num_paths_per_src=per_src,
        max_paths_total=total, specular_reflection=True,
        diffuse_reflection=True, diffraction=True, refraction=False,
        synthetic_array=False, rx_batch_size=128)


def test_budget_tidak_pernah_melebihi_nilai_per_sumber():
    st = make(1_000_000, 8_000_000)
    assert st.paths_budget(1) == 1_000_000
    assert st.paths_budget(8) == 1_000_000


def test_budget_mengecil_untuk_sumber_banyak():
    """64 sumber: 1e6 per sumber = 1 GiB per buffer, yang OOM di GPU 12 GB."""
    st = make(1_000_000, 8_000_000)
    assert st.paths_budget(64) == 125_000
    assert st.paths_budget(64) * 64 * BYTES_PER_PATH == 128_000_000


def test_buffer_konstan_di_seluruh_jumlah_sumber():
    st = make(1_000_000, 8_000_000)
    for n in (8, 16, 32, 64, 128):
        assert st.paths_budget(n) * n <= st.max_paths_total


def test_total_nol_mematikan_mekanisme():
    st = make(100_000, 0)
    assert st.paths_budget(64) == 100_000


def test_budget_minimal_satu():
    st = make(1_000_000, 10)
    assert st.paths_budget(1_000) == 1


@pytest.mark.parametrize("n", [0, -1])
def test_jumlah_sumber_tak_masuk_akal_tidak_membagi_nol(n):
    st = make(1_000_000, 8_000_000)
    assert st.paths_budget(n) == 1_000_000


def test_from_config_default_total_nol():
    """Config lama tanpa max_paths_total harus tetap berjalan apa adanya."""
    cfg = {"ray_tracing": {
        "max_depth": 5, "samples_per_src": 100_000,
        "max_num_paths_per_src": 100_000, "specular_reflection": True,
        "diffuse_reflection": True, "diffraction": True,
        "ris_per_element": True, "rx_batch_size": 128}}
    st = RayTracingSettings.from_config(cfg)
    assert st.max_paths_total == 0
    assert st.paths_budget(64) == 100_000
