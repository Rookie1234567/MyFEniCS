"""Single material-region inventory shared by 3D forms and diagnostics.

Layered pillars are opt-in. Legacy configurations retain the original three
regions and their order. Coordinates/wavelengths are in nm; n uses exp(-i wt).
"""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite


@dataclass(frozen=True)
class MaterialRegion3D:
    name: str
    tag: int
    refractive_index: complex
    label: str | None
    role: str

    @property
    def epsilon_r(self) -> complex:
        return self.refractive_index ** 2


def grating_layers(cfg) -> tuple[tuple[float, float, MaterialRegion3D], ...]:
    thicknesses = getattr(cfg, "grating_layer_thicknesses_nm", None)
    indices = getattr(cfg, "grating_layer_indices", None)
    labels = getattr(cfg, "grating_layer_labels", None)
    if thicknesses is None and indices is None and labels is None:
        return ()
    if thicknesses is None or indices is None or labels is None:
        raise ValueError("layer thicknesses, refractive indices and labels are required together")
    if not thicknesses or not (len(thicknesses) == len(indices) == len(labels)):
        raise ValueError("layer lists must have the same nonzero length")
    if cfg.geometry_kind != "rectangular_block_grating" or not cfg.has_grating_block:
        raise ValueError("layers require a finite rectangular grating block")
    z = float(cfg.interface_z)
    layers = []
    for i, (thickness, index, label) in enumerate(zip(thicknesses, indices, labels)):
        if isinstance(thickness, bool) or not isfinite(float(thickness)) or thickness <= 0:
            raise ValueError("each layer thickness must be finite and positive")
        n = complex(index)
        if not all(isfinite(v) for v in (n.real, n.imag)) or n.real <= 0 or n.imag < 0:
            raise ValueError("layer n must be finite, Re(n)>0 and passive Im(n)>=0")
        if not isinstance(label, str) or not label:
            raise ValueError("each layer needs an explicit material label")
        end = z + float(thickness)
        layers.append((z, end, MaterialRegion3D(f"layer_{i+1}", 21+i, n, label, "grating")))
        z = end
    if abs(z - cfg.grating_z_max) > 1e-12 * max(1.0, abs(z)):
        raise ValueError("layer thickness sum must equal the independent grating height")
    tags = [row[2].tag for row in layers]
    if set(tags) & {cfg.tags.air, cfg.tags.substrate, cfg.tags.grating, cfg.tags.top_pml, cfg.tags.bottom_pml}:
        raise ValueError("layer tags collide with existing volume tags")
    return tuple(layers)


def material_regions(cfg) -> tuple[MaterialRegion3D, ...]:
    common = (
        MaterialRegion3D("air", cfg.tags.air, complex(cfg.n_air), "air", "air"),
        MaterialRegion3D("substrate", cfg.tags.substrate, cfg.substrate_index,
                         cfg.substrate_material_label, "substrate"),
    )
    layers = grating_layers(cfg)
    if layers:
        return common + tuple(row[2] for row in layers)
    return common + (MaterialRegion3D("grating", cfg.tags.grating, cfg.grating_index,
                                    cfg.grating_material_label, "grating"),)
