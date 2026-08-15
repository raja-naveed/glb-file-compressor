"""Progressive compression passes ordered from highest quality to most aggressive."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CompressionPass:
    """One compression recipe. Earlier passes preserve more visual fidelity."""

    name: str
    texture_size: int
    webp_quality: int  # texture encoder quality 1-100 (WebP or JPEG)
    simplify_ratio: float  # 1.0 = keep all geometry
    simplify_error: float
    use_draco: bool = True
    near_lossless: bool = False
    texture_format: str = "webp"  # "webp" | "jpeg"
    use_quantize: bool = False  # KHR_mesh_quantization (native in THREE.GLTFLoader)
    use_meshopt: bool = False  # EXT_meshopt_compression (needs MeshoptDecoder)
    lock_border: bool = True
    join_meshes: bool = False  # Can inflate size on shared/reused meshes


QUALITY_LADDER: list[CompressionPass] = [
    CompressionPass(
        name="archive-near-lossless",
        texture_size=4096,
        webp_quality=95,
        simplify_ratio=1.0,
        simplify_error=0.0001,
        near_lossless=True,
    ),
    CompressionPass(
        name="ultra",
        texture_size=2048,
        webp_quality=92,
        simplify_ratio=1.0,
        simplify_error=0.0001,
    ),
    CompressionPass(
        name="excellent",
        texture_size=2048,
        webp_quality=88,
        simplify_ratio=0.95,
        simplify_error=0.0005,
    ),
    CompressionPass(
        name="high",
        texture_size=1536,
        webp_quality=85,
        simplify_ratio=0.90,
        simplify_error=0.001,
    ),
    CompressionPass(
        name="balanced",
        texture_size=1024,
        webp_quality=82,
        simplify_ratio=0.80,
        simplify_error=0.002,
    ),
    CompressionPass(
        name="compact",
        texture_size=1024,
        webp_quality=76,
        simplify_ratio=0.70,
        simplify_error=0.005,
    ),
    CompressionPass(
        name="tight",
        texture_size=768,
        webp_quality=72,
        simplify_ratio=0.55,
        simplify_error=0.01,
    ),
    CompressionPass(
        name="small",
        texture_size=512,
        webp_quality=68,
        simplify_ratio=0.45,
        simplify_error=0.015,
    ),
    CompressionPass(
        name="tiny",
        texture_size=512,
        webp_quality=60,
        simplify_ratio=0.35,
        simplify_error=0.02,
    ),
    CompressionPass(
        name="minimum",
        texture_size=256,
        webp_quality=55,
        simplify_ratio=0.25,
        simplify_error=0.03,
    ),
]


# Salesforce: no Draco. Meshopt gets geometry-heavy reused-mesh models under 5 MB.
# THREE.GLTFLoader needs: loader.setMeshoptDecoder(MeshoptDecoder)
SALESFORCE_LADDER: list[CompressionPass] = [
    CompressionPass(
        name="sf-ultra",
        texture_size=1024,
        webp_quality=85,
        simplify_ratio=0.85,
        simplify_error=0.01,
        use_draco=False,
        use_meshopt=True,
        texture_format="webp",
        lock_border=False,
        join_meshes=False,
    ),
    CompressionPass(
        name="sf-high",
        texture_size=1024,
        webp_quality=80,
        simplify_ratio=0.70,
        simplify_error=0.02,
        use_draco=False,
        use_meshopt=True,
        texture_format="webp",
        lock_border=False,
        join_meshes=False,
    ),
    CompressionPass(
        name="sf-balanced",
        texture_size=896,
        webp_quality=75,
        simplify_ratio=0.55,
        simplify_error=0.04,
        use_draco=False,
        use_meshopt=True,
        texture_format="webp",
        lock_border=False,
        join_meshes=False,
    ),
    CompressionPass(
        name="sf-compact",
        texture_size=768,
        webp_quality=70,
        simplify_ratio=0.40,
        simplify_error=0.06,
        use_draco=False,
        use_meshopt=True,
        texture_format="webp",
        lock_border=False,
        join_meshes=False,
    ),
    CompressionPass(
        name="sf-tight",
        texture_size=640,
        webp_quality=65,
        simplify_ratio=0.30,
        simplify_error=0.10,
        use_draco=False,
        use_meshopt=True,
        texture_format="webp",
        lock_border=False,
        join_meshes=False,
    ),
    CompressionPass(
        name="sf-force",
        texture_size=512,
        webp_quality=58,
        simplify_ratio=0.20,
        simplify_error=0.20,
        use_draco=False,
        use_meshopt=True,
        texture_format="webp",
        lock_border=False,
        join_meshes=False,
    ),
]
