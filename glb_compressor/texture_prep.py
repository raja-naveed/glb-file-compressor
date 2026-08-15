"""Normalize and shrink embedded GLB textures with Pillow."""

from __future__ import annotations

import base64
import io
from pathlib import Path

from PIL import Image
from pygltflib import GLTF2, Buffer, BufferView


def _align4(buf: bytearray) -> None:
    pad = (4 - (len(buf) % 4)) % 4
    if pad:
        buf.extend(b"\x00" * pad)


def _read_image_bytes(gltf: GLTF2, image, blob: bytes) -> bytes | None:
    if image.uri and isinstance(image.uri, str):
        if image.uri.startswith("data:"):
            try:
                return base64.b64decode(image.uri.split(",", 1)[1])
            except Exception:
                return None
        return None

    if image.bufferView is None or not blob:
        return None

    view = gltf.bufferViews[image.bufferView]
    start = view.byteOffset or 0
    return bytes(blob[start : start + view.byteLength])


def _encode_texture(
    raw: bytes,
    max_size: int,
    quality: int,
    near_lossless: bool,
    texture_format: str,
) -> tuple[bytes, tuple[int, int], tuple[int, int], str]:
    img = Image.open(io.BytesIO(raw))
    src_size = img.size
    w, h = img.size
    scale = min(1.0, max_size / max(w, h))
    if scale < 1.0:
        img = img.resize(
            (max(1, int(w * scale)), max(1, int(h * scale))),
            Image.Resampling.LANCZOS,
        )

    fmt = (texture_format or "webp").lower()
    out = io.BytesIO()

    if fmt == "jpeg":
        # JPEG has no alpha — composite onto white for opaque product shots
        rgba = img.convert("RGBA")
        background = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
        composited = Image.alpha_composite(background, rgba).convert("RGB")
        composited.save(out, format="JPEG", quality=int(quality), optimize=True)
        mime = "image/jpeg"
    else:
        rgba = img.convert("RGBA")
        kwargs = {"format": "WEBP", "quality": int(quality), "method": 6}
        if near_lossless:
            kwargs["near_lossless"] = True
        rgba.save(out, **kwargs)
        mime = "image/webp"

    return out.getvalue(), src_size, img.size, mime


def prepare_textures(
    input_path: Path,
    output_path: Path,
    max_size: int,
    webp_quality: int,
    near_lossless: bool = False,
    verbose: bool = False,
    texture_format: str = "webp",
) -> Path:
    """
    Rebuild a GLB with resized textures using Pillow.

    Non-image buffer data is preserved; old image bytes are discarded so the
    file actually shrinks.
    """
    input_path = Path(input_path)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    gltf = GLTF2().load(str(input_path))
    if not gltf.images:
        if input_path.resolve() != output_path.resolve():
            output_path.write_bytes(input_path.read_bytes())
        return output_path

    old_blob = bytes(gltf.binary_blob() or b"")
    buffer_views = list(gltf.bufferViews or [])

    encoded: list[tuple[bytes, str]] = []
    for idx, image in enumerate(gltf.images):
        raw = _read_image_bytes(gltf, image, old_blob)
        if not raw:
            raise RuntimeError(f"Could not read texture #{idx} from {input_path.name}")
        try:
            data, src_size, dst_size, mime = _encode_texture(
                raw, max_size, webp_quality, near_lossless, texture_format
            )
        except Exception as exc:
            raise RuntimeError(f"Texture #{idx} encode failed: {exc}") from exc
        encoded.append((data, mime))
        if verbose:
            print(
                f"  texture {idx}: {src_size[0]}x{src_size[1]} -> "
                f"{dst_size[0]}x{dst_size[1]} {mime} q={webp_quality} "
                f"({len(raw)} -> {len(data)} bytes)"
            )

    image_view_indices = {
        img.bufferView for img in gltf.images if img.bufferView is not None
    }

    new_blob = bytearray()
    new_views: list[BufferView] = []
    view_remap: dict[int, int] = {}

    for old_index, view in enumerate(buffer_views):
        if old_index in image_view_indices:
            continue
        start = view.byteOffset or 0
        length = view.byteLength or 0
        chunk = old_blob[start : start + length]
        _align4(new_blob)
        new_offset = len(new_blob)
        new_blob.extend(chunk)
        _align4(new_blob)
        view_remap[old_index] = len(new_views)
        new_views.append(
            BufferView(
                buffer=0,
                byteOffset=new_offset,
                byteLength=length,
                byteStride=getattr(view, "byteStride", None),
                target=getattr(view, "target", None),
            )
        )

    if gltf.accessors:
        for accessor in gltf.accessors:
            if accessor.bufferView is not None and accessor.bufferView in view_remap:
                accessor.bufferView = view_remap[accessor.bufferView]
            sparse = getattr(accessor, "sparse", None)
            if sparse is None:
                continue
            for part_name in ("indices", "values"):
                part = getattr(sparse, part_name, None)
                if (
                    part is not None
                    and getattr(part, "bufferView", None) is not None
                    and part.bufferView in view_remap
                ):
                    part.bufferView = view_remap[part.bufferView]

    for image, (data, mime) in zip(gltf.images, encoded):
        _align4(new_blob)
        new_offset = len(new_blob)
        new_blob.extend(data)
        _align4(new_blob)
        image.bufferView = len(new_views)
        image.mimeType = mime
        image.uri = None
        new_views.append(
            BufferView(buffer=0, byteOffset=new_offset, byteLength=len(data))
        )

    # Drop WebP extension requirement when we rewrote to JPEG
    if texture_format.lower() == "jpeg" and gltf.extensionsUsed:
        gltf.extensionsUsed = [
            e for e in gltf.extensionsUsed if e != "EXT_texture_webp"
        ]
    if texture_format.lower() == "jpeg" and gltf.extensionsRequired:
        gltf.extensionsRequired = [
            e for e in gltf.extensionsRequired if e != "EXT_texture_webp"
        ]

    gltf.bufferViews = new_views
    if not gltf.buffers:
        gltf.buffers = [Buffer(byteLength=len(new_blob))]
    else:
        gltf.buffers[0].byteLength = len(new_blob)
        gltf.buffers[0].uri = None

    gltf.set_binary_blob(bytes(new_blob))
    gltf.save_binary(str(output_path))
    return output_path
