"""Pemuatan config dan pembagian hash kanal (src/risisac/config.py)."""

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from risisac.config import (CHANNEL_RADIO_FIELDS,                    # noqa: E402
                            CHANNEL_SECTIONS, NON_CHANNEL_SECTIONS,
                            channel_config_hash, channel_config_subset,
                            config_hash, load_config)


@pytest.fixture(scope="module")
def cfg():
    return load_config("base")


def test_setiap_kunci_tingkat_atas_terklasifikasi(cfg):
    """Kunci baru harus dinyatakan memengaruhi kanal atau tidak.

    Tanpa uji ini, kunci yang ditambahkan belakangan diam-diam masuk ke
    kelompok "tidak memengaruhi kanal" dan basis data basi akan dipakai ulang
    tanpa peringatan apa pun -- kegagalan yang jauh lebih mahal daripada
    menghitung ulang.
    """
    classified = set(CHANNEL_SECTIONS) | set(NON_CHANNEL_SECTIONS) | {"radio"}
    unknown = set(cfg) - classified
    assert not unknown, (
        f"kunci config belum diklasifikasikan: {sorted(unknown)}. Tambahkan ke "
        "CHANNEL_SECTIONS atau NON_CHANNEL_SECTIONS di src/risisac/config.py.")


def test_bagian_kanal_dan_bukan_kanal_tidak_tumpang_tindih():
    assert not set(CHANNEL_SECTIONS) & set(NON_CHANNEL_SECTIONS)


def test_hash_kanal_tidak_berubah_oleh_ambang_gate(cfg):
    """Mengubah ambang gate tidak boleh memaksa ray tracing ulang."""
    before = channel_config_hash(cfg)
    changed = {**cfg, "gate1": {**cfg["gate1"], "ris_gain_threshold_db": 99.0}}
    assert channel_config_hash(changed) == before
    assert config_hash(changed) != config_hash(cfg)


def test_hash_kanal_tidak_berubah_oleh_reward_atau_training(cfg):
    for section, key, value in (("reward", "lambda", 7.0),
                                ("training", "num_seeds", 11),
                                ("sensing", "scnr_threshold_db", 20.0)):
        changed = {**cfg, section: {**cfg[section], key: value}}
        assert channel_config_hash(changed) == channel_config_hash(cfg), section


def test_hash_kanal_tidak_berubah_oleh_calibration_db(cfg):
    """calibration_db diisi dari hasil E0 dan tidak diterapkan ke kanal."""
    radio = {**cfg["radio"], "ris": {**cfg["radio"]["ris"], "calibration_db": 9.9}}
    assert channel_config_hash({**cfg, "radio": radio}) == channel_config_hash(cfg)


@pytest.mark.parametrize("section,key,value", [
    ("ray_tracing", "max_depth", 9),
    ("ray_tracing", "deterministic", True),
    ("ray_tracing", "refraction", True),
    ("mobility", "episode_steps", 77),
])
def test_hash_kanal_berubah_oleh_parameter_kanal(cfg, section, key, value):
    changed = {**cfg, section: {**cfg[section], key: value}}
    assert channel_config_hash(changed) != channel_config_hash(cfg)


def test_hash_kanal_berubah_oleh_geometri(cfg):
    scene = {**cfg["scene"], "bs_position": [0.0, 0.0, 10.0]}
    assert channel_config_hash({**cfg, "scene": scene}) != channel_config_hash(cfg)


def test_hash_kanal_berubah_oleh_jumlah_elemen_ris(cfg):
    radio = {**cfg["radio"], "ris": {**cfg["radio"]["ris"], "num_rows": 16}}
    assert channel_config_hash({**cfg, "radio": radio}) != channel_config_hash(cfg)


def test_subset_memuat_bagian_yang_diharapkan(cfg):
    subset = channel_config_subset(cfg)
    assert set(subset) == set(CHANNEL_SECTIONS) | {"radio"}
    assert set(subset["radio"]) == set(CHANNEL_RADIO_FIELDS)
    assert "p_max_dbm" not in subset["radio"]
    assert "calibration_db" not in subset["radio"]["ris"]


def test_notasi_eksponen_tanpa_tanda_ditolak(tmp_path):
    """Guard YAML 1.1: 3.5e9 ter-parse sebagai string, bukan angka."""
    bad = tmp_path / "bad.yaml"
    bad.write_text("radio:\n  carrier_frequency_hz: 3.5e9\n", encoding="utf-8")
    with pytest.raises(ValueError, match="string"):
        load_config(bad)
