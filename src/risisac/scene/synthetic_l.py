"""Scene pengembangan berbentuk L: dua jalan tegak lurus dan gedung kotak.

docs/TASKS.md Fase 1, docs/EXPERIMENT_DESIGN.md §2.2 (baris "Pengembangan").

Tata letak (tampak atas, sumbu +x ke kanan, +y ke atas)::

      y
      ^            blok NW          |  jalan B  |   blok NE
      |                             |           |
      |   - - - - - - - - - - - - - +-----------+ - - - -   y = +w/2
      |            jalan A          : simpang   :
      |   - - - - - - - - - - - - - +-----------+ - - - -   y = -w/2
      |            blok SW          |           |   blok SE
      +--------------------------------------------------> x
                                 x=-w/2       x=+w/2

Jalan A memanjang ke arah -x (tempat BS), jalan B ke arah +y (area NLoS).
Keduanya selebar ``street_width_m`` dan bertemu di sebuah simpang di origin,
sehingga sudut blok NW adalah penghalang yang membuat jalan B NLoS dari BS.

Scene dibangun sebagai XML Mitsuba dengan primitif ``cube`` dan ``rectangle``,
bukan file mesh terpisah. Hasilnya satu string yang bisa langsung dimuat lewat
``sionna.rt.load_scene_from_string``, sehingga scene sepenuhnya ditentukan oleh
config dan tidak ada aset biner yang perlu ikut di-commit.

Catatan primitif Mitsuba: ``cube`` adalah kubus [-1,1]^3 dan ``rectangle``
adalah persegi [-1,1]^2 di bidang xy. Jadi ``scale(a,b,c)`` lalu
``translate(x,y,z)`` menghasilkan kotak berpusat di (x,y,z) dengan setengah
rusuk (a,b,c).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SyntheticLSpec:
    """Geometri scene sintetis, semuanya dari ``configs/*.yaml``."""

    street_width_m: float
    block_extent_m: float
    building_height_m: float
    building_material: str
    ground_material: str
    material_thickness_m: float

    @classmethod
    def from_config(cls, cfg: dict) -> "SyntheticLSpec":
        s = cfg["scene"]["synthetic_l"]
        return cls(
            street_width_m=float(s["street_width_m"]),
            block_extent_m=float(s["block_extent_m"]),
            building_height_m=float(s["building_height_m"]),
            building_material=str(s["building_material"]),
            ground_material=str(s["ground_material"]),
            material_thickness_m=float(s["material_thickness_m"]),
        )

    @property
    def half_width(self) -> float:
        """Setengah lebar jalan; tepi jalan ada di +/- nilai ini."""
        return self.street_width_m / 2.0

    @property
    def extent(self) -> float:
        """Setengah sisi scene secara keseluruhan [m]."""
        return self.half_width + self.block_extent_m

    def blocks(self) -> dict[str, tuple[float, float, float, float]]:
        """Empat blok gedung sebagai (xmin, xmax, ymin, ymax)."""
        w, e = self.half_width, self.extent
        return {
            "block_nw": (-e, -w, w, e),
            "block_ne": (w, e, w, e),
            "block_sw": (-e, -w, -e, -w),
            "block_se": (w, e, -e, -w),
        }


def _bsdf(material_id: str, itu_type: str, thickness: float) -> str:
    return (
        f'  <bsdf type="itu-radio-material" id="{material_id}">\n'
        f'    <string name="type" value="{itu_type}"/>\n'
        f'    <float name="thickness" value="{thickness}"/>\n'
        f"  </bsdf>\n"
    )


def _box(name: str, material_id: str,
         xmin: float, xmax: float, ymin: float, ymax: float,
         zmin: float, zmax: float) -> str:
    sx, sy, sz = (xmax - xmin) / 2.0, (ymax - ymin) / 2.0, (zmax - zmin) / 2.0
    cx, cy, cz = (xmax + xmin) / 2.0, (ymax + ymin) / 2.0, (zmax + zmin) / 2.0
    return (
        f'  <shape type="cube" id="mesh-{name}">\n'
        f'    <ref id="{material_id}" name="bsdf"/>\n'
        f'    <transform name="to_world">\n'
        f'      <scale x="{sx}" y="{sy}" z="{sz}"/>\n'
        f'      <translate x="{cx}" y="{cy}" z="{cz}"/>\n'
        f"    </transform>\n"
        f"  </shape>\n"
    )


def build_xml(spec: SyntheticLSpec) -> str:
    """Bangun XML Mitsuba lengkap untuk scene sintetis."""
    # Nama id material dibuat berbeda dari nama tipe ITU agar tidak tertukar.
    mats = {spec.ground_material: "mat_ground",
            spec.building_material: "mat_building"}

    parts = ['<scene version="2.1.0">\n\n  <!-- Material -->\n']
    for itu_type, mat_id in mats.items():
        parts.append(_bsdf(mat_id, itu_type, spec.material_thickness_m))

    parts.append("\n  <!-- Tanah -->\n")
    e = spec.extent
    parts.append(
        f'  <shape type="rectangle" id="mesh-ground">\n'
        f'    <ref id="{mats[spec.ground_material]}" name="bsdf"/>\n'
        f'    <transform name="to_world">\n'
        f'      <scale x="{e}" y="{e}" z="1"/>\n'
        f"    </transform>\n"
        f"  </shape>\n"
    )

    parts.append("\n  <!-- Blok gedung -->\n")
    for name, (xmin, xmax, ymin, ymax) in spec.blocks().items():
        parts.append(_box(name, mats[spec.building_material],
                          xmin, xmax, ymin, ymax, 0.0, spec.building_height_m))

    parts.append("</scene>\n")
    return "".join(parts)


def write_xml(spec: SyntheticLSpec, path: str | Path) -> Path:
    """Tulis XML ke disk (untuk inspeksi manual atau dibuka di Mitsuba)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(build_xml(spec), encoding="utf-8")
    return path


def load_synthetic_l(spec: SyntheticLSpec, merge_shapes: bool = True):
    """Muat scene sintetis sebagai ``sionna.rt.Scene``.

    Impor Sionna sengaja ditunda ke dalam fungsi: modul ini dipakai juga oleh
    tes yang hanya memeriksa XML, dan impor Sionna mahal.
    """
    import sionna.rt as rt

    return rt.load_scene_from_string(build_xml(spec), merge_shapes=merge_shapes)
