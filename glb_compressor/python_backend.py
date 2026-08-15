"""Pure-Python GLB compression fallback (trimesh simplify + Pillow WebP)."""

from __future__ import annotations

from pathlib import Path

import trimesh

from .quality_ladder import CompressionPass
from .texture_prep import prepare_textures


def _as_scene(loaded) -> trimesh.Scene:
    if isinstance(loaded, trimesh.Scene):
        return loaded
    return trimesh.Scene(loaded)


def _iter_meshes(scene: trimesh.Scene):
    for name, geom in scene.geometry.items():
        if isinstance(geom, trimesh.Trimesh):
            yield name, geom


def _simplify_mesh(mesh: trimesh.Trimesh, ratio: float, verbose: bool = False) -> None:
    if ratio >= 0.999:
        return
    face_count = len(mesh.faces)
    if face_count < 32:
        return
    target = max(16, int(face_count * ratio))
    if target >= face_count:
        return
    try:
        simplified = mesh.simplify_quadric_decimation(face_count=target)
        if simplified is not None and len(simplified.faces) > 0:
            mesh.vertices = simplified.vertices
            mesh.faces = simplified.faces
            if hasattr(simplified, "visual"):
                mesh.visual = simplified.visual
            if verbose:
                print(f"    faces {face_count} -> {len(mesh.faces)}")
    except Exception as exc:
        if verbose:
            print(f"    simplify skipped: {exc}")


def compress_with_python(
    input_path: Path,
    output_path: Path,
    pass_cfg: CompressionPass,
    verbose: bool = False,
) -> Path:
    """Simplify geometry with trimesh, then rewrite textures as compact WebP."""
    loaded = trimesh.load(str(input_path), force="scene")
    scene = _as_scene(loaded)

    for name, mesh in _iter_meshes(scene):
        if verbose:
            print(f"  -> mesh '{name}'")
        _simplify_mesh(mesh, pass_cfg.simplify_ratio, verbose=verbose)
        try:
            mesh.fix_normals()
        except Exception:
            pass

    output_path.parent.mkdir(parents=True, exist_ok=True)
    interim = output_path.with_suffix(".interim.glb")

    data = scene.export(file_type="glb", include_normals=True)
    if isinstance(data, bytes):
        interim.write_bytes(data)
    else:
        scene.export(file_obj=str(interim), file_type="glb", include_normals=True)

    if verbose:
        print("  -> textures (Pillow WebP)")
    prepare_textures(
        interim,
        output_path,
        max_size=pass_cfg.texture_size,
        webp_quality=pass_cfg.webp_quality,
        near_lossless=pass_cfg.near_lossless,
        verbose=verbose,
        texture_format=pass_cfg.texture_format,
    )
    try:
        interim.unlink(missing_ok=True)
    except Exception:
        pass

    return output_path
