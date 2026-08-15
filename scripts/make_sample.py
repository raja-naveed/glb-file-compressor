"""Create a large textured GLB for compressor smoke tests."""

from __future__ import annotations

import io
from pathlib import Path

import numpy as np
import trimesh
from PIL import Image, ImageDraw


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    samples = root / "samples"
    samples.mkdir(exist_ok=True)

    # Uncompressed-looking PNG textures dominate real-world GLB size.
    size = 4096
    img = Image.new("RGB", (size, size), (30, 40, 60))
    draw = ImageDraw.Draw(img)
    rng = np.random.default_rng(42)
    noise = (rng.random((size, size, 3)) * 255).astype(np.uint8)
    img = Image.fromarray(noise, mode="RGB")
    draw = ImageDraw.Draw(img)
    for i in range(0, size, 64):
        draw.rectangle(
            [i, i, i + 48, i + 48],
            fill=(i % 255, (i * 3) % 255, (255 - i) % 255),
        )
        draw.ellipse(
            [size - i - 80, i, size - i, i + 80],
            fill=((i * 7) % 255, 120, (i * 2) % 255),
        )
    buf = io.BytesIO()
    img.save(buf, format="PNG", compress_level=0)
    buf.seek(0)
    tex = Image.open(buf)

    # Second large map (normal-ish) to inflate binary further
    nrm = Image.fromarray(
        (rng.random((size, size, 3)) * 255).astype(np.uint8), mode="RGB"
    )

    mesh = trimesh.creation.icosphere(subdivisions=7)
    x, y, z = mesh.vertices[:, 0], mesh.vertices[:, 1], mesh.vertices[:, 2]
    norms = np.linalg.norm(mesh.vertices, axis=1)
    u = 0.5 + np.arctan2(z, x) / (2 * np.pi)
    v = 0.5 + np.arcsin(np.clip(y / norms, -1, 1)) / np.pi
    uvs = np.column_stack([u, v])

    material = trimesh.visual.material.PBRMaterial(
        baseColorTexture=tex,
        normalTexture=nrm,
        metallicFactor=0.1,
        roughnessFactor=0.7,
    )
    mesh.visual = trimesh.visual.TextureVisuals(uv=uvs, material=material)

    out = samples / "big_test.glb"
    out.write_bytes(mesh.export(file_type="glb"))
    print(
        f"wrote {out} size={out.stat().st_size / 1024 / 1024:.2f} MB "
        f"faces={len(mesh.faces)}"
    )


if __name__ == "__main__":
    main()
