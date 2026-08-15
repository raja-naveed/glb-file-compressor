#!/usr/bin/env python3
"""CLI for high-quality GLB compression to a target size (default 5 MB)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from glb_compressor.pipeline import compress_glb


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Compress GLB/GLTF files to a target size (default 5 MB) "
            "while preserving the best practical visual quality."
        )
    )
    parser.add_argument(
        "input",
        nargs="?",
        help="Input .glb/.gltf file (or folder with --batch)",
    )
    parser.add_argument(
        "-o",
        "--output",
        help="Output .glb path (or output folder with --batch)",
    )
    parser.add_argument(
        "-t",
        "--target-mb",
        type=float,
        default=5.0,
        help="Maximum output size in megabytes (default: 5)",
    )
    parser.add_argument(
        "--backend",
        choices=("auto", "transform", "python"),
        default="auto",
        help="Compression engine (default: auto)",
    )
    parser.add_argument(
        "--batch",
        action="store_true",
        help="Compress every .glb/.gltf in the input folder",
    )
    parser.add_argument(
        "--no-draco",
        action="store_true",
        help=(
            "Disable Draco mesh compression so plain THREE.GLTFLoader "
            "can load the file without DRACOLoader"
        ),
    )
    parser.add_argument(
        "--salesforce",
        action="store_true",
        help=(
            "Salesforce preset: <=4.5 MB using Meshopt + WebP (no Draco). "
            "Requires MeshoptDecoder in Three.js / LWC"
        ),
    )
    parser.add_argument(
        "--texture-format",
        choices=("webp", "jpeg"),
        default=None,
        help="Texture format (default: webp)",
    )
    parser.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="Less console output",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if not args.input:
        parser.print_help()
        print("\nExamples:")
        print("  python compress.py model.glb --salesforce")
        print("  python compress.py model.glb -o model_5mb.glb --target-mb 5")
        print("  python compress.py model.glb --no-draco")
        print("  python compress.py ./models --batch -o ./compressed")
        return 1

    input_path = Path(args.input)
    if args.target_mb <= 0:
        print("Error: --target-mb must be > 0", file=sys.stderr)
        return 2

    try:
        if args.batch:
            if not input_path.is_dir():
                print("Error: --batch requires an input folder", file=sys.stderr)
                return 2
            files = sorted(
                [
                    *input_path.glob("*.glb"),
                    *input_path.glob("*.gltf"),
                    *input_path.glob("*.GLB"),
                    *input_path.glob("*.GLTF"),
                ]
            )
            # de-dupe case variants on Windows
            uniq: dict[str, Path] = {}
            for f in files:
                uniq[str(f.resolve()).lower()] = f
            files = list(uniq.values())
            if not files:
                print(f"No GLB/GLTF files found in {input_path}")
                return 1

            out_dir = Path(args.output) if args.output else input_path / "compressed"
            out_dir.mkdir(parents=True, exist_ok=True)
            target_mb = args.target_mb
            if args.salesforce and args.target_mb >= 5.0:
                target_mb = 4.5
            failures = 0
            for f in files:
                print(f"\n======== {f.name} ========")
                try:
                    compress_glb(
                        f,
                        out_dir / f"{f.stem}_compressed.glb",
                        target_mb=target_mb,
                        backend=args.backend,
                        verbose=not args.quiet,
                        use_draco=not args.no_draco,
                        texture_format=args.texture_format or "webp",
                        salesforce=args.salesforce,
                    )
                except Exception as exc:
                    failures += 1
                    print(f"Failed: {exc}", file=sys.stderr)
            return 1 if failures else 0

        # Salesforce always aims at 4.5 MB unless user sets a lower --target-mb
        target_mb = args.target_mb
        if args.salesforce and args.target_mb >= 5.0:
            target_mb = 4.5

        result = compress_glb(
            input_path,
            args.output,
            target_mb=target_mb,
            backend=args.backend,
            verbose=not args.quiet,
            use_draco=not args.no_draco,
            texture_format=args.texture_format or "webp",
            salesforce=args.salesforce,
        )
        return 0 if result.hit_target else 3
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
