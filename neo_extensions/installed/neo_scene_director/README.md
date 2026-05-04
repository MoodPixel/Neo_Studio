# Neo Scene Director Built-in Extension

This folder is the production built-in extension version of Scene Director.

It is registered through `neo_extension.json` instead of the old legacy `neo_studio_v1/extensions/image/scene_director/manifest.json` scanner path.

## Contents

- `neo_extension.json` — extension manifest
- `static/scene_director.js` — frontend panel hook
- `backend/routes.py` — extension backend route hook wrapper
- `workflows/test_workflows/` — imported Scene Director workflow packs
- `Neo_Scene_Director_v0_5_2_IPAdapter_Region_Prep.zip` — bundled ComfyUI node pack

## Transition note

The legacy Python adapter module remains in `neo_studio_v1/extensions/image/scene_director/adapter.py` for the generation route import path during this transition. The legacy manifest files are disabled to prevent duplicate registry entries.
