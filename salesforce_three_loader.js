/**
 * Salesforce / LWC Three.js loader for Meshopt-compressed GLBs
 * produced by: python compress.py model.glb --salesforce
 *
 * No Draco. Uses EXT_meshopt_compression + MeshoptDecoder from Three.js.
 */
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { MeshoptDecoder } from 'three/addons/libs/meshopt_decoder.module.js';

export function createSalesforceGltfLoader() {
  const loader = new GLTFLoader();
  loader.setMeshoptDecoder(MeshoptDecoder);
  return loader;
}

// Example:
// const loader = createSalesforceGltfLoader();
// loader.load(modelUrl, (gltf) => scene.add(gltf.scene));
