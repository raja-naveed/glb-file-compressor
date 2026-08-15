"""Industry-standard geometry compression via @gltf-transform/cli (Node)."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from .quality_ladder import CompressionPass


def _resolve_npx() -> str | None:
    """Resolve npx in a Windows-friendly way (.cmd shims need a full path)."""
    for name in ("npx.cmd", "npx.CMD", "npx"):
        path = shutil.which(name)
        if path:
            return path
    for candidate in (
        Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "nodejs" / "npx.cmd",
        Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"))
        / "nodejs"
        / "npx.cmd",
    ):
        if candidate.exists():
            return str(candidate)
    return None


def gltf_transform_available() -> bool:
    return _resolve_npx() is not None


def _run_cli(args: list[str], verbose: bool = False) -> None:
    npx = _resolve_npx()
    if not npx:
        raise RuntimeError("npx was not found (install Node.js)")

    cmd = [npx, "--yes", "@gltf-transform/cli", *args]
    if verbose:
        print("  $", " ".join(cmd))

    use_shell = os.name == "nt"
    result = subprocess.run(
        cmd if not use_shell else subprocess.list2cmdline(cmd),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        shell=use_shell,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        lines = [
            ln
            for ln in detail.splitlines()
            if ln.strip() and "npm warn" not in ln.lower()
        ]
        raise RuntimeError(
            f"gltf-transform failed ({args[0]}): "
            + (" | ".join(lines[-6:]) if lines else detail)
        )


def _step(
    name: str,
    args: list[str],
    output: Path,
    current: Path,
    verbose: bool,
    optional: bool = False,
) -> Path:
    if verbose:
        print(f"  -> {name}")
    try:
        _run_cli(args, verbose=verbose)
        if not output.exists():
            raise RuntimeError(f"{name} produced no output")
        return output
    except Exception as exc:
        if optional:
            if verbose:
                print(f"  ! {name} skipped ({exc})")
            if current.resolve() != output.resolve():
                shutil.copy2(current, output)
            return output
        raise


def compress_with_gltf_transform(
    input_path: Path,
    output_path: Path,
    pass_cfg: CompressionPass,
    verbose: bool = False,
) -> Path:
    """
    Geometry-focused glTF Transform pipeline.

    For many-mesh models, flatten+join first so simplify can actually reduce
    triangle counts (tiny separate meshes often refuse to decimate).
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="glb_tf_") as tmp:
        tmp_dir = Path(tmp)
        current = input_path

        # Optional flatten+join. Off by default: on mesh-reused scenes join
        # duplicates geometry and can inflate size a lot.
        if pass_cfg.join_meshes:
            current = _step(
                "flatten",
                ["flatten", str(current), str(tmp_dir / "00_flatten.glb")],
                tmp_dir / "00_flatten.glb",
                current,
                verbose,
                optional=True,
            )
            current = _step(
                "join",
                [
                    "join",
                    str(current),
                    str(tmp_dir / "00_join.glb"),
                    "--keepNamed",
                    "false",
                    "--keepMeshes",
                    "false",
                ],
                tmp_dir / "00_join.glb",
                current,
                verbose,
                optional=True,
            )

        current = _step(
            "dedup",
            ["dedup", str(current), str(tmp_dir / "01_dedup.glb")],
            tmp_dir / "01_dedup.glb",
            current,
            verbose,
            optional=True,
        )
        current = _step(
            "prune",
            ["prune", str(current), str(tmp_dir / "02_prune.glb")],
            tmp_dir / "02_prune.glb",
            current,
            verbose,
            optional=True,
        )
        current = _step(
            "weld",
            ["weld", str(current), str(tmp_dir / "03_weld.glb")],
            tmp_dir / "03_weld.glb",
            current,
            verbose,
            optional=True,
        )

        if pass_cfg.simplify_ratio < 0.999:
            current = _step(
                "simplify",
                [
                    "simplify",
                    str(current),
                    str(tmp_dir / "04_simplify.glb"),
                    "--ratio",
                    str(pass_cfg.simplify_ratio),
                    "--error",
                    str(pass_cfg.simplify_error),
                    "--lock-border",
                    "true" if pass_cfg.lock_border else "false",
                ],
                tmp_dir / "04_simplify.glb",
                current,
                verbose,
                optional=True,
            )

        # Compression extensions (pick one):
        # - Draco: smallest, needs DRACOLoader
        # - Meshopt: Salesforce-friendly under 5 MB, needs MeshoptDecoder
        # - Quantize: no extra loader, much weaker size reduction
        if pass_cfg.use_draco:
            current = _step(
                "draco",
                [
                    "draco",
                    str(current),
                    str(tmp_dir / "05_draco.glb"),
                    "--method",
                    "edgebreaker",
                    "--encode-speed",
                    "5",
                    "--decode-speed",
                    "5",
                    "--quantize-position",
                    "14",
                    "--quantize-normal",
                    "10",
                    "--quantize-texcoord",
                    "12",
                    "--quantize-color",
                    "8",
                    "--quantize-generic",
                    "12",
                ],
                tmp_dir / "05_draco.glb",
                current,
                verbose,
                optional=True,
            )
        elif pass_cfg.use_meshopt:
            current = _step(
                "meshopt",
                [
                    "meshopt",
                    str(current),
                    str(tmp_dir / "05_meshopt.glb"),
                    "--level",
                    "high",
                ],
                tmp_dir / "05_meshopt.glb",
                current,
                verbose,
                optional=True,
            )
        elif pass_cfg.use_quantize:
            current = _step(
                "quantize",
                [
                    "quantize",
                    str(current),
                    str(tmp_dir / "05_quantize.glb"),
                    "--quantize-position",
                    "12",
                    "--quantize-normal",
                    "8",
                    "--quantize-texcoord",
                    "10",
                    "--quantize-color",
                    "8",
                ],
                tmp_dir / "05_quantize.glb",
                current,
                verbose,
                optional=True,
            )

        shutil.copy2(current, output_path)

    return output_path
