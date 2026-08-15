"""Progressive compressor that hits a size target with the best possible quality."""

from __future__ import annotations

import shutil
import tempfile
from dataclasses import dataclass, replace
from pathlib import Path

from .quality_ladder import QUALITY_LADDER, SALESFORCE_LADDER, CompressionPass
from .python_backend import compress_with_python
from .texture_prep import prepare_textures
from .transform_backend import compress_with_gltf_transform, gltf_transform_available


@dataclass
class CompressResult:
    input_path: Path
    output_path: Path
    input_bytes: int
    output_bytes: int
    target_bytes: int
    pass_name: str
    backend: str
    hit_target: bool

    @property
    def input_mb(self) -> float:
        return self.input_bytes / (1024 * 1024)

    @property
    def output_mb(self) -> float:
        return self.output_bytes / (1024 * 1024)

    @property
    def saved_percent(self) -> float:
        if self.input_bytes <= 0:
            return 0.0
        return (1.0 - self.output_bytes / self.input_bytes) * 100.0


def _file_size(path: Path) -> int:
    return path.stat().st_size


def _format_mb(num_bytes: int) -> str:
    return f"{num_bytes / (1024 * 1024):.2f} MB"


def compress_glb(
    input_path: str | Path,
    output_path: str | Path | None = None,
    target_mb: float = 5.0,
    backend: str = "auto",
    verbose: bool = True,
    use_draco: bool = True,
    texture_format: str = "webp",
    salesforce: bool = False,
) -> CompressResult:
    """
    Compress a GLB to <= target_mb while preserving the highest practical quality.

    backend:
      - "auto": prefer gltf-transform (best), else pure Python
      - "transform": require @gltf-transform/cli via npx
      - "python": trimesh + Pillow

    salesforce:
      Optimized for Salesforce static resources (<=4.5 MB).
      Uses Meshopt (NOT Draco). Wire MeshoptDecoder in Three.js / LWC.
    """
    if salesforce:
        # Hard Salesforce static-resource budget with headroom.
        target_mb = min(float(target_mb), 4.5)
        # No Draco — Meshopt is used by the Salesforce ladder instead.
        use_draco = False
        if texture_format in (None, "", "webp"):
            texture_format = "webp"

    texture_format = (texture_format or "webp").lower()
    if texture_format not in {"webp", "jpeg"}:
        raise ValueError("texture_format must be 'webp' or 'jpeg'")

    input_path = Path(input_path).expanduser().resolve()
    if not input_path.exists():
        raise FileNotFoundError(f"Input not found: {input_path}")
    if input_path.suffix.lower() not in {".glb", ".gltf"}:
        raise ValueError("Input must be a .glb or .gltf file")

    if output_path is None:
        suffix = "_salesforce.glb" if salesforce else "_compressed.glb"
        output_path = input_path.with_name(f"{input_path.stem}{suffix}")
    else:
        output_path = Path(output_path).expanduser().resolve()
        if output_path.is_dir():
            suffix = "_salesforce.glb" if salesforce else "_compressed.glb"
            output_path = output_path / f"{input_path.stem}{suffix}"
        elif output_path.suffix.lower() != ".glb":
            output_path = output_path.with_suffix(".glb")

    target_bytes = int(target_mb * 1024 * 1024)
    input_bytes = _file_size(input_path)

    if backend == "auto":
        use_transform = gltf_transform_available()
        chosen = "transform" if use_transform else "python"
    elif backend == "transform":
        if not gltf_transform_available():
            raise RuntimeError(
                "gltf-transform backend requested but npx/Node.js was not found"
            )
        chosen = "transform"
    elif backend == "python":
        chosen = "python"
    else:
        raise ValueError("backend must be one of: auto, transform, python")

    if verbose:
        print(f"Input : {input_path.name} ({_format_mb(input_bytes)})")
        print(f"Target: <= {_format_mb(target_bytes)}")  # ASCII-safe for Windows consoles
        print(f"Engine: {chosen}")
        print(f"Draco : {'on' if use_draco else 'off'}")
        print(f"Tex   : {texture_format}")
        if salesforce:
            print("Preset: Salesforce (<=4.5 MB, Meshopt + WebP, no Draco)")
            print("  NOTE: Load with MeshoptDecoder (1 line). See README.")

    # Already under target -> still apply a gentle high-quality pass for cleanup
    if salesforce:
        ladder = list(SALESFORCE_LADDER)
    else:
        ladder = list(QUALITY_LADDER)
        if input_bytes <= target_bytes:
            ladder = [QUALITY_LADDER[0], QUALITY_LADDER[1]]

    ladder = [
        replace(
            p,
            use_draco=False if salesforce else (use_draco and p.use_draco),
            use_meshopt=True if salesforce else p.use_meshopt,
            use_quantize=False if salesforce else (
                False if use_draco else p.use_quantize
            ),
            texture_format=texture_format,
            near_lossless=p.near_lossless if texture_format == "webp" else False,
        )
        for p in ladder
    ]

    best_path: Path | None = None
    best_size = 1 << 62
    best_pass = ladder[0].name

    with tempfile.TemporaryDirectory(prefix="glb_compress_") as tmp:
        tmp_dir = Path(tmp)

        for idx, pass_cfg in enumerate(ladder, start=1):
            candidate = tmp_dir / f"pass_{idx:02d}_{pass_cfg.name}.glb"
            if verbose:
                print(
                    f"\n[{idx}/{len(ladder)}] {pass_cfg.name} "
                    f"(tex<={pass_cfg.texture_size}px, webp={pass_cfg.webp_quality}, "
                    f"keep={pass_cfg.simplify_ratio:.0%} geom)"
                )

            try:
                if chosen == "transform":
                    textured = tmp_dir / f"pass_{idx:02d}_{pass_cfg.name}_tex.glb"
                    if verbose:
                        print(f"  -> textures (Pillow {pass_cfg.texture_format})")
                    prepare_textures(
                        input_path,
                        textured,
                        max_size=pass_cfg.texture_size,
                        webp_quality=pass_cfg.webp_quality,
                        near_lossless=pass_cfg.near_lossless,
                        verbose=verbose,
                        texture_format=pass_cfg.texture_format,
                    )
                    compress_with_gltf_transform(
                        textured, candidate, pass_cfg, verbose=verbose
                    )
                else:
                    compress_with_python(
                        input_path, candidate, pass_cfg, verbose=verbose
                    )
            except Exception as exc:
                if verbose:
                    print(f"  ! pass failed: {exc}")
                # If transform fails, switch to Python for this and later passes
                if chosen == "transform":
                    if verbose:
                        print("  -> switching to Python engine")
                    chosen = "python"
                    try:
                        compress_with_python(
                            input_path, candidate, pass_cfg, verbose=verbose
                        )
                    except Exception as exc2:
                        if verbose:
                            print(f"  ! python fallback failed: {exc2}")
                        continue
                else:
                    continue

            size = _file_size(candidate)
            if verbose:
                status = "OK under target" if size <= target_bytes else "still large"
                print(f"  size: {_format_mb(size)} -- {status}")

            if size < best_size:
                best_size = size
                best_pass = pass_cfg.name
                best_path = tmp_dir / f"best_{pass_cfg.name}.glb"
                shutil.copy2(candidate, best_path)

            if size <= target_bytes:
                break

        if best_path is None or not best_path.exists():
            raise RuntimeError("Compression failed: no usable output was produced")

        output_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(best_path, output_path)

    output_bytes = _file_size(output_path)
    result = CompressResult(
        input_path=input_path,
        output_path=output_path,
        input_bytes=input_bytes,
        output_bytes=output_bytes,
        target_bytes=target_bytes,
        pass_name=best_pass,
        backend=chosen,
        hit_target=output_bytes <= target_bytes,
    )

    if verbose:
        print("\nDone")
        print(f"  Output : {output_path}")
        print(f"  Size   : {_format_mb(output_bytes)} (was {_format_mb(input_bytes)})")
        print(f"  Saved  : {result.saved_percent:.1f}%")
        print(f"  Pass   : {best_pass}")
        if not result.hit_target:
            print(
                "  Warning: could not reach the target size while keeping a valid model. "
                "The smallest best-effort result was written."
            )

    return result
