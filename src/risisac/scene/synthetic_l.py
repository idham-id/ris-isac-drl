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
    # Keteraturan fasad. Dengan setback dan variasi tinggi = 0, tiap blok
    # kembali menjadi satu kotak utuh (scene Fase 1 versi pertama).
    facade_depth_m: float = 0.0
    facade_segment_m: float = 0.0
    facade_setback_m: float = 0.0
    facade_height_var_m: float = 0.0
    facade_seed: int = 1

    @classmethod
    def from_config(cls, cfg: dict) -> "SyntheticLSpec":
        s = cfg["scene"]["synthetic_l"]
        f = s.get("facade", {}) or {}
        return cls(
            street_width_m=float(s["street_width_m"]),
            block_extent_m=float(s["block_extent_m"]),
            building_height_m=float(s["building_height_m"]),
            building_material=str(s["building_material"]),
            ground_material=str(s["ground_material"]),
            material_thickness_m=float(s["material_thickness_m"]),
            facade_depth_m=float(f.get("depth_m", 0.0)),
            facade_segment_m=float(f.get("segment_m", 0.0)),
            facade_setback_m=float(f.get("setback_m", 0.0)),
            facade_height_var_m=float(f.get("height_var_m", 0.0)),
            facade_seed=int(f.get("seed", 1)),
        )

    @property
    def irregular_facades(self) -> bool:
        return (self.facade_segment_m > 0.0
                and (self.facade_setback_m > 0.0 or self.facade_height_var_m > 0.0))

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
    mat = mats[spec.building_material]
    if not spec.irregular_facades:
        for name, (xmin, xmax, ymin, ymax) in spec.blocks().items():
            parts.append(_box(name, mat, xmin, xmax, ymin, ymax,
                              0.0, spec.building_height_m))
    else:
        for name, box in _irregular_boxes(spec):
            parts.append(_box(name, mat, *box))

    parts.append("</scene>\n")
    return "".join(parts)


def _street_sides(spec: SyntheticLSpec) -> dict[str, list[tuple[str, float, float]]]:
    """Sisi tiap blok yang menghadap jalan.

    Tiap entri ``(axis, edge, inward)``: bidang fasad tegak lurus ``axis`` pada
    koordinat ``edge``, dan ``inward`` (+1/-1) arah masuk ke dalam blok.
    """
    w, e = spec.half_width, spec.extent
    return {
        "block_nw": [("y", w, +1.0), ("x", -w, -1.0)],
        "block_ne": [("y", w, +1.0), ("x", w, +1.0)],
        "block_sw": [("y", -w, -1.0), ("x", -w, -1.0)],
        "block_se": [("y", -w, -1.0), ("x", w, +1.0)],
    }


def _segments(rng, lo: float, hi: float, nominal: float) -> list[tuple[float, float]]:
    """Bagi [lo, hi] menjadi segmen dengan panjang acak di sekitar ``nominal``."""
    out: list[tuple[float, float]] = []
    pos = lo
    while hi - pos > 1e-9:
        length = nominal * float(rng.uniform(0.6, 1.4))
        nxt = min(pos + length, hi)
        if hi - nxt < 0.35 * nominal:      # jangan sisakan potongan kerdil
            nxt = hi
        out.append((pos, nxt))
        pos = nxt
    return out


def _irregular_boxes(spec: SyntheticLSpec):
    """Kotak-kotak pembentuk blok dengan fasad bersegmen.

    Tiap blok terdiri dari satu inti pejal yang ditarik mundur sejauh
    ``facade_depth_m`` dari sisi yang menghadap jalan, ditambah deretan kotak
    fasad di tiap sisi itu. Tiap segmen fasad punya setback dan tinggi sendiri,
    sehingga dindingnya berundak, bukan satu cermin datar sepanjang blok.

    Kotak fasad sengaja menembus jauh ke dalam inti (``+2 m``) supaya tidak
    pernah ada celah di antaranya; tumpang tindih tidak jadi masalah bagi ray
    tracing, sedangkan celah akan membuat sinar masuk ke dalam gedung.
    """
    import numpy as np

    rng = np.random.default_rng(spec.facade_seed)
    depth = spec.facade_depth_m
    h0, hv = spec.building_height_m, spec.facade_height_var_m
    sides = _street_sides(spec)

    for name, (xmin, xmax, ymin, ymax) in spec.blocks().items():
        core = [xmin, xmax, ymin, ymax]
        for axis, edge, inward in sides[name]:
            if axis == "x":
                if inward > 0:
                    core[0] = max(core[0], edge + depth)
                else:
                    core[1] = min(core[1], edge - depth)
            else:
                if inward > 0:
                    core[2] = max(core[2], edge + depth)
                else:
                    core[3] = min(core[3], edge - depth)
        yield f"{name}_core", (core[0], core[1], core[2], core[3], 0.0, h0)

        for axis, edge, inward in sides[name]:
            lo, hi = (ymin, ymax) if axis == "x" else (xmin, xmax)
            for i, (a0, a1) in enumerate(_segments(rng, lo, hi, spec.facade_segment_m)):
                setback = float(rng.uniform(0.0, spec.facade_setback_m))
                height = max(4.0, h0 + float(rng.uniform(-hv, hv)))
                near = edge + inward * setback
                far = edge + inward * (depth + 2.0)
                b0, b1 = (near, far) if near <= far else (far, near)
                if axis == "x":
                    box = (b0, b1, a0, a1, 0.0, height)
                else:
                    box = (a0, a1, b0, b1, 0.0, height)
                yield f"{name}_{'x' if axis == 'x' else 'y'}{i}", box


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
