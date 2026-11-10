"""Pola antena tambahan: elemen kosinus untuk RIS.

``configs/base.yaml`` meminta ``ris.element_pattern: cosine``, sedangkan Sionna
RT 2.2 hanya mendaftarkan ``iso``, ``dipole``, ``hw_dipole``, dan ``tr38901``.
docs/EXPERIMENT_DESIGN.md §4.2 membolehkan "pola elemen kosinus atau pola bawaan
yang mendekati"; modul ini menyediakan yang pertama.

Model elemen:

    G(theta_e) = 4 cos(theta_e),   theta_e dalam [0, pi/2], 0 di belakang panel

dengan ``theta_e`` sudut dari normal elemen. Faktor 4 membuatnya ternormalisasi:
integral cos(theta) atas setengah bola sama dengan pi, sehingga
integral G dOmega = 4 pi. Pola medannya adalah akar dari pola daya.

Konvensi sudut Sionna: ``theta`` adalah sudut zenit dari +z lokal dan ``phi``
azimut dari +x lokal, sedangkan boresight array adalah +x lokal. Jadi kosinus
terhadap normal panel adalah ``sin(theta) cos(phi)``, bukan ``cos(theta)``.
"""

from __future__ import annotations


def register_cosine_pattern() -> None:
    """Daftarkan pola "cosine". Aman dipanggil berkali-kali."""
    import drjit as dr
    import mitsuba as mi
    import sionna.rt as rt
    from sionna.rt.antenna_pattern import (PolarizedAntennaPattern,
                                           antenna_pattern_registry)

    if "cosine" in antenna_pattern_registry.list():
        return

    def v_cosine_pattern(theta: "mi.Float", phi: "mi.Float") -> "mi.Complex2f":
        # Kosinus terhadap normal panel (+x lokal).
        cos_e = dr.sin(theta) * dr.cos(phi)
        cos_e = dr.maximum(cos_e, 0.0)          # nol di belakang panel
        c_theta = dr.sqrt(4.0 * cos_e)          # pola medan = sqrt(pola daya)
        return mi.Complex2f(c_theta, 0)

    def factory(*, polarization, polarization_model="tr38901_2"):
        return PolarizedAntennaPattern(v_pattern=v_cosine_pattern,
                                       polarization=polarization,
                                       polarization_model=polarization_model)

    rt.register_antenna_pattern("cosine", factory)
