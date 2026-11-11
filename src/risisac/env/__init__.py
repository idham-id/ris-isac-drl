"""Environment RL (docs/EXPERIMENT_DESIGN.md §5).

Modul ini **tidak boleh mengimpor Sionna** (CLAUDE.md): environment hanya
membaca basis data kanal HDF5 yang sudah diprakomputasi di Fase 2.
"""

from .ris_isac_env import EnvConfig, RisIsacEnv, TrajectoryStore

__all__ = ["EnvConfig", "RisIsacEnv", "TrajectoryStore"]
