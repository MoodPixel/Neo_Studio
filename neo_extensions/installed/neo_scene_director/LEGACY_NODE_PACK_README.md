# Neo Scene Director v0.5.2 — IPAdapter Region Prep

This build keeps the stable v0.5.1 count-locked scene behavior and adds clean regional identity prep for IPAdapter workflows.

## Install
Copy this folder into ComfyUI custom nodes:

```text
ComfyUI/custom_nodes/neo_scene_director/
```

Restart ComfyUI.

## Main node
```text
Neo Scene Director v0.5.2 (IPAdapter Region Prep)
```

## New outputs
The original outputs are unchanged at the front, so old workflows should still load. New outputs are appended:

```text
subject_1_mask
subject_2_mask
subject_3_mask
subject_4_mask
identity_plan_json
```

Use these masks with your installed IPAdapter implementation's masked/attention mask input. The node does not bundle IPAdapter itself, because ComfyUI users may use different IPAdapter extensions.

## Safe starting settings
- IPAdapter weight: `0.45–0.70`
- start_at: `0.0`
- end_at: `0.65–0.80`
- Add one subject reference at a time.
- If subject count breaks, lower IPAdapter weight before changing Scene Director region settings.

## Test workflows
Start with:

```text
neo_scene_director_v052_pose_interaction_checkpoint_gguf_vae_api.json
neo_scene_director_v052_3_people_checkpoint_gguf_vae_api.json
neo_scene_director_v052_4_people_checkpoint_gguf_vae_api.json
```

## Notes
The v0.5.2 node outputs subject masks and an identity routing plan. To actually apply identity references, connect the relevant subject mask to your IPAdapter node and load the matching reference image there.
