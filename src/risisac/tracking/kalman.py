"""Filter Kalman kecepatan-konstan 2D (docs/EXPERIMENT_DESIGN.md §5.2).

State x = [px, py, vx, vy]^T, pengukuran = posisi saja.

    F = [[1,0,dt,0],[0,1,0,dt],[0,0,1,0],[0,0,0,1]],   H = [[1,0,0,0],[0,1,0,0]]

Derau proses memakai model **percepatan diskret** (piecewise-constant white
acceleration): percepatan dianggap konstan selama satu langkah dan diacak
antar-langkah dengan simpangan baku ``sigma_a``, sehingga

    Q = sigma_a^2 * [[dt^4/4 I, dt^3/2 I], [dt^3/2 I, dt^2 I]].

Model ini dipilih, bukan derau diagonal sembarang, karena korelasi
posisi-kecepatan di dalamnya memang yang dihasilkan percepatan -- dan gerakan
target di sini (perubahan lajur yang mulus, §2.3) persis berbentuk itu.

**Galat pengukuran bergantung SCNR** (§5.2):

    sigma_pos = sigma_ref * sqrt(Gamma_lin / SCNR_lin),  dibatasi sigma_max.

Inilah yang membuat masalahnya sekuensial: iluminasi sekarang menentukan SCNR,
SCNR menentukan ketepatan pengukuran, pengukuran menentukan estimasi posisi,
dan estimasi itu menentukan beam sensing berikutnya. Bila target tidak
terdeteksi, filter **hanya memprediksi** -- tidak ada langkah koreksi.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


def measurement_std(scnr_db: float, threshold_db: float, sigma_ref_m: float,
                    sigma_max_m: float) -> float:
    """sigma_pos = sigma_ref sqrt(Gamma_lin / SCNR_lin), dibatasi sigma_max.

    SCNR tepat di ambang memberi sigma_ref; SCNR 20 dB di atas ambang memberi
    sigma_ref/10. Pembatasan atas mencegah SCNR sangat rendah menghasilkan
    pengukuran tak berhingga buruk yang meledakkan filter.
    """
    ratio_db = float(threshold_db) - float(scnr_db)
    sigma = float(sigma_ref_m) * 10.0 ** (ratio_db / 20.0)
    return float(min(sigma, float(sigma_max_m)))


@dataclass
class ConstantVelocityKalman:
    """Filter Kalman kecepatan-konstan 2D untuk satu target.

    :param dt_s: langkah waktu
    :param process_noise_std_mps2: sigma_a percepatan
    """

    dt_s: float
    process_noise_std_mps2: float
    state: np.ndarray = field(default_factory=lambda: np.zeros(4))
    covariance: np.ndarray = field(default_factory=lambda: np.eye(4))

    def __post_init__(self) -> None:
        dt = float(self.dt_s)
        self._F = np.array([[1.0, 0.0, dt, 0.0],
                            [0.0, 1.0, 0.0, dt],
                            [0.0, 0.0, 1.0, 0.0],
                            [0.0, 0.0, 0.0, 1.0]])
        self._H = np.array([[1.0, 0.0, 0.0, 0.0],
                            [0.0, 1.0, 0.0, 0.0]])
        q = float(self.process_noise_std_mps2) ** 2
        eye = np.eye(2)
        self._Q = q * np.block([
            [dt ** 4 / 4.0 * eye, dt ** 3 / 2.0 * eye],
            [dt ** 3 / 2.0 * eye, dt ** 2 * eye],
        ])

    # ------------------------------------------------------------------ init
    def initialize(self, position_xy, velocity_xy=(0.0, 0.0),
                   position_std_m: float = 0.5,
                   velocity_std_mps: float = 5.0) -> "ConstantVelocityKalman":
        """Set state awal (§5.5: posisi awal + noise).

        Simpangan baku kecepatan awal dibuat lebar karena arah dan laju target
        memang belum diketahui saat episode mulai.
        """
        self.state = np.concatenate([np.asarray(position_xy, float).reshape(2),
                                     np.asarray(velocity_xy, float).reshape(2)])
        self.covariance = np.diag([position_std_m ** 2, position_std_m ** 2,
                                   velocity_std_mps ** 2, velocity_std_mps ** 2])
        return self

    # --------------------------------------------------------------- langkah
    def predict(self) -> np.ndarray:
        """Propagasi satu langkah. Dipanggil juga saat target tidak terdeteksi."""
        self.state = self._F @ self.state
        self.covariance = self._F @ self.covariance @ self._F.T + self._Q
        return self.state

    def update(self, measurement_xy, measurement_std_m: float) -> np.ndarray:
        """Koreksi dengan satu pengukuran posisi."""
        z = np.asarray(measurement_xy, float).reshape(2)
        r = float(measurement_std_m) ** 2 * np.eye(2)
        innovation = z - self._H @ self.state
        s = self._H @ self.covariance @ self._H.T + r
        gain = np.linalg.solve(s.T, (self.covariance @ self._H.T).T).T
        self.state = self.state + gain @ innovation
        # Bentuk Joseph: tetap simetris dan positif semidefinit meski gain
        # dihitung dengan presisi terbatas.
        ikh = np.eye(4) - gain @ self._H
        self.covariance = ikh @ self.covariance @ ikh.T + gain @ r @ gain.T
        return self.state

    def step(self, detected: bool, measurement_xy=None,
             measurement_std_m: float = 1.0) -> np.ndarray:
        """Satu langkah penuh: prediksi, lalu koreksi bila terdeteksi."""
        self.predict()
        if detected:
            if measurement_xy is None:
                raise ValueError("step(detected=True) butuh measurement_xy.")
            self.update(measurement_xy, measurement_std_m)
        return self.state

    # --------------------------------------------------------------- keluaran
    @property
    def position(self) -> np.ndarray:
        return self.state[:2].copy()

    @property
    def velocity(self) -> np.ndarray:
        return self.state[2:].copy()

    @property
    def position_std(self) -> np.ndarray:
        return np.sqrt(np.maximum(np.diag(self.covariance)[:2], 0.0))
