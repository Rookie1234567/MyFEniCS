from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pyvista


def _physical_grid(grid: pyvista.UnstructuredGrid) -> pyvista.UnstructuredGrid:
    """Return only air/substrate/grating cells, excluding top/bottom PML."""
    if "domain_tag" not in grid.cell_data:
        raise ValueError("The input VTU does not contain cell_data['domain_tag'].")
    return grid.threshold([0.5, 3.5], scalars="domain_tag", preference="cell")


def _field_clim(dataset, scalar: str, low_percentile: float, high_percentile: float) -> tuple[float, float]:
    if scalar in dataset.cell_data:
        values = np.asarray(dataset.cell_data[scalar], dtype=np.float64)
    else:
        values = np.asarray(dataset.point_data[scalar], dtype=np.float64)
    finite = values[np.isfinite(values)]
    if finite.size == 0:
        return 0.0, 1.0
    lo = float(np.percentile(finite, low_percentile))
    hi = float(np.percentile(finite, high_percentile))
    if not np.isfinite(lo) or not np.isfinite(hi) or hi <= lo:
        lo = float(np.nanmin(finite))
        hi = float(np.nanmax(finite))
    if hi <= lo:
        hi = lo + 1.0
    return lo, hi


def _plot_dataset(dataset, scalar: str, path: Path, *, view: str, title: str, clim: tuple[float, float]) -> None:
    pyvista.OFF_SCREEN = True
    plotter = pyvista.Plotter(off_screen=True, window_size=(1400, 850))
    plotter.set_background("white")
    plotter.add_mesh(
        dataset,
        scalars=scalar,
        preference="cell" if scalar in dataset.cell_data else "point",
        cmap="turbo",
        clim=clim,
        show_edges=False,
        show_scalar_bar=False,
        lighting=False,
        nan_color="white",
    )
    plotter.add_scalar_bar(
        title="|E| (V/m)",
        n_labels=6,
        vertical=True,
        position_x=0.86,
        position_y=0.14,
        width=0.08,
        height=0.76,
    )
    plotter.add_text(title, font_size=12, color="black")
    plotter.add_axes(line_width=2, labels_off=False)
    if view == "isometric":
        plotter.view_isometric()
    elif view == "yz":
        plotter.view_yz()
    elif view == "xz":
        plotter.view_xz()
    else:
        raise ValueError(f"Unsupported view {view!r}.")
    plotter.enable_parallel_projection()
    plotter.camera.zoom(1.15)
    path.parent.mkdir(parents=True, exist_ok=True)
    plotter.show(screenshot=str(path))
    plotter.close()


def _sample_points(source, scalar: str, points: np.ndarray) -> np.ndarray:
    probe = pyvista.PolyData(points)
    sampled = probe.sample(source)
    values = np.asarray(sampled.point_data[scalar], dtype=np.float64)
    if "vtkValidPointMask" in sampled.point_data:
        valid = np.asarray(sampled.point_data["vtkValidPointMask"], dtype=bool)
        values = values.copy()
        values[~valid] = np.nan
    return values


def _grating_bounds(physical) -> tuple[float, float, float, float, float, float] | None:
    if "domain_tag" not in physical.cell_data:
        return None
    grating = physical.threshold([2.5, 3.5], scalars="domain_tag", preference="cell")
    if grating.n_cells == 0:
        return None
    return tuple(float(value) for value in grating.bounds)


def _plot_regular_slice(
    physical,
    scalar: str,
    path: Path,
    *,
    plane: str,
    title: str,
    resolution: tuple[int, int] = (420, 720),
) -> dict[str, object]:
    bounds = physical.bounds
    grating_bounds = _grating_bounds(physical)
    horizontal_count, vertical_count = resolution
    if plane == "yz":
        x_mid = 0.5 * (bounds[0] + bounds[1])
        horizontal = np.linspace(bounds[2], bounds[3], horizontal_count)
        z_values = np.linspace(bounds[4], bounds[5], vertical_count)
        points = np.asarray([[x_mid, y, z] for z in z_values for y in horizontal], dtype=np.float64)
        xlabel = "y (nm)"
        rect = None
        if grating_bounds is not None and grating_bounds[0] <= x_mid <= grating_bounds[1]:
            rect = (grating_bounds[2], grating_bounds[4], grating_bounds[3] - grating_bounds[2], grating_bounds[5] - grating_bounds[4])
    elif plane == "xz":
        y_mid = 0.5 * (bounds[2] + bounds[3])
        horizontal = np.linspace(bounds[0], bounds[1], horizontal_count)
        z_values = np.linspace(bounds[4], bounds[5], vertical_count)
        points = np.asarray([[x, y_mid, z] for z in z_values for x in horizontal], dtype=np.float64)
        xlabel = "x (nm)"
        rect = None
        if grating_bounds is not None and grating_bounds[2] <= y_mid <= grating_bounds[3]:
            rect = (grating_bounds[0], grating_bounds[4], grating_bounds[1] - grating_bounds[0], grating_bounds[5] - grating_bounds[4])
    else:
        raise ValueError("plane must be 'yz' or 'xz'.")

    values = _sample_points(physical, scalar, points).reshape((vertical_count, horizontal_count))
    finite = values[np.isfinite(values)]
    if finite.size:
        clim = (float(np.percentile(finite, 0.5)), float(np.percentile(finite, 99.5)))
    else:
        clim = (0.0, 1.0)
    if clim[1] <= clim[0]:
        clim = (float(np.nanmin(values)), float(np.nanmax(values) + 1.0))

    fig, ax = plt.subplots(figsize=(8.5, 10.5), dpi=160)
    image = ax.imshow(
        values,
        extent=[horizontal[0], horizontal[-1], z_values[0], z_values[-1]],
        origin="lower",
        aspect="auto",
        cmap="turbo",
        vmin=clim[0],
        vmax=clim[1],
        interpolation="bilinear",
    )
    ax.axhline(0.0, color="black", linewidth=1.0)
    if rect is not None:
        from matplotlib.patches import Rectangle

        ax.add_patch(Rectangle((rect[0], rect[1]), rect[2], rect[3], fill=False, edgecolor="black", linewidth=1.2))
    ax.set_title(title)
    ax.set_xlabel(xlabel)
    ax.set_ylabel("z (nm)")
    colorbar = fig.colorbar(image, ax=ax, fraction=0.046, pad=0.04)
    colorbar.set_label("|E| (V/m)")
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path)
    plt.close(fig)
    return {
        "path": str(path),
        "color_min": clim[0],
        "color_max": clim[1],
        "num_points": int(points.shape[0]),
        "num_cells": None,
    }


def render_views(vtu_path: Path, output_dir: Path, scalar: str) -> dict[str, object]:
    grid = pyvista.read(vtu_path)
    if scalar not in grid.point_data:
        raise ValueError(f"The input VTU does not contain point_data[{scalar!r}].")
    physical = _physical_grid(grid)
    bounds = physical.bounds
    summary: dict[str, object] = {
        "vtu_path": str(vtu_path),
        "output_dir": str(output_dir),
        "scalar": scalar,
        "physical_bounds": list(bounds),
        "views": {},
    }
    surface = physical.extract_surface()
    if scalar in surface.point_data:
        surface = surface.point_data_to_cell_data(pass_point_data=True)
    surface_clim = _field_clim(surface, scalar, 0.5, 99.5)
    surface_path = output_dir / "stage4_comsol_like_outer_surface.png"
    _plot_dataset(surface, scalar, surface_path, view="isometric", title="physical outer surface", clim=surface_clim)
    summary["views"]["outer_surface"] = {
        "path": str(surface_path),
        "color_min": surface_clim[0],
        "color_max": surface_clim[1],
        "num_points": int(surface.n_points),
        "num_cells": int(surface.n_cells),
    }
    summary["views"]["slice_yz_x_mid"] = _plot_regular_slice(
        physical,
        scalar,
        output_dir / "stage4_comsol_like_slice_yz_x_mid.png",
        plane="yz",
        title=f"y-z slice at x={0.5 * (bounds[0] + bounds[1]):g} nm",
    )
    summary["views"]["slice_xz_y_mid"] = _plot_regular_slice(
        physical,
        scalar,
        output_dir / "stage4_comsol_like_slice_xz_y_mid.png",
        plane="xz",
        title=f"x-z slice at y={0.5 * (bounds[2] + bounds[3]):g} nm",
    )
    return summary


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Render COMSOL-like Stage-4 |E| comparison views from a 3D VTU file.")
    parser.add_argument("vtu_path", type=Path)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--scalar", default="E_tot_V_per_m_abs")
    args = parser.parse_args(argv)

    output_dir = args.output_dir or args.vtu_path.parent
    summary = render_views(args.vtu_path, output_dir, args.scalar)
    summary_path = output_dir / "stage4_comsol_like_views.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
