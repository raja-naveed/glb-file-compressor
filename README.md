# GLB File Compressor

High-quality **GLB/GLTF compressor** that targets **5 MB or less** while keeping the best practical visual quality.

It tries gentle passes first (cleanup + high-quality WebP + Draco), then only increases texture downscaling / mesh simplification if the file is still too large.

## Features

- Target any size (default **5 MB**)
- Quality-first progressive ladder (stops at the first pass that fits)
- **gltf-transform** engine (Draco + WebP + meshoptimizer simplify) when Node.js is available
- Pure **Python** fallback (`trimesh` + `Pillow` + optional Draco)
- Single-file and batch folder modes

## Setup

```bash
pip install -r requirements.txt
```
    
For the best results, also install [Node.js](https://nodejs.org/) (the tool uses `npx @gltf-transform/cli` automatically).

Optional Draco helper for the Python backend:

```bash
pip install dracox
```

## Usage

```bash
# BEST for Salesforce (LWC / static resource / plain GLTFLoader)
python compress.py model.glb --salesforce

# Compress to <= 5 MB (default, may use Draco + WebP)
python compress.py model.glb

# Custom output + target
python compress.py model.glb -o model_5mb.glb --target-mb 5

# Three.js-friendly (no Draco only)
python compress.py model.glb --no-draco

# Batch a folder
python compress.py ./models --batch -o ./compressed
```

## Salesforce (recommended)

Salesforce **static resources max out at 5 MB**, and LWC/Locker often breaks Draco WASM decoders.

`--salesforce` applies the safe preset:

- target **≤ 4.5 MB** (headroom under the 5 MB static-resource limit)
- **no Draco** (plain `THREE.GLTFLoader` works — no DRACOLoader)
- **WebP textures** + **mesh quantization** (keeps size down without Draco)

```bash
python compress.py your_model.glb --salesforce
```

Upload the output `your_model_salesforce.glb` as a Static Resource, then load it with normal `GLTFLoader` (no `DRACOLoader` needed).

## Loading in Three.js

If you compressed **without** `--salesforce` / `--no-draco`, files may use **Draco**. Plain `GLTFLoader` then fails with:

`THREE.GLTFLoader: No DRACOLoader instance provided.`

For Salesforce, prefer `--salesforce`. Elsewhere you can wire `DRACOLoader`:

```js
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { DRACOLoader } from 'three/addons/loaders/DRACOLoader.js';

const dracoLoader = new DRACOLoader();
dracoLoader.setDecoderPath('https://www.gstatic.com/draco/versioned/decoders/1.5.7/');

const loader = new GLTFLoader();
loader.setDRACOLoader(dracoLoader);
loader.load('model_compressed.glb', (gltf) => {
  scene.add(gltf.scene);
});
```

## How quality is preserved

Passes run in this order and stop early when the size target is hit:

1. Near-lossless / ultra WebP, full geometry, Draco  
2. Mild texture resize + tiny mesh simplify  
3. Stronger texture/geometry reduction only if still over target  

Textures are usually the biggest win. Geometry simplification is used last because it affects silhouette quality more.

## Exit codes

| Code | Meaning |
|------|---------|
| 0 | Success and under target |
| 1 | Error / no files |
| 2 | Bad arguments |
| 3 | Wrote a file, but could not reach the target size |
