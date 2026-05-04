# Image Tab — Image Preview Area Guide

## Overview

The **Image Preview Area** is the live output and action hub for the Image Tab.

It is not only used to view the latest generated image. It also acts as a routing point that can send the current output into other workflows such as Img2Img, Inpaint, Outpaint, ControlNet, IP-Adapter, Upscale Lab, Selective Repair, and Identity Rescue.

Use this area after a generation finishes and you want to continue working from the selected image instead of starting over.

---

## Main Purpose

The Image Preview Area helps you:

- View the latest generated output
- Click the preview to zoom/open it larger
- Select an active output from the current run
- Reuse the output as a source image
- Send the output into reference workflows
- Run finishing passes on the active output
- Keep the visible workspace mode stable while running derived actions

---

## Output Preview

### Latest Preview

This shows the current active generation preview.

If no job has been queued yet, Neo shows a message telling the user to connect an image backend, choose a checkpoint, and queue from Neo Studio.

### Clicking the Preview

Clicking the preview image opens the zoom modal.

Use this when you need to inspect:

- Face quality
- Hands
- Clothing details
- Composition
- Artifacts
- Small subject errors

---

## Current Run Outputs

The current run outputs list shows thumbnails from the latest generation job.

### Behavior

- Clicking a thumbnail swaps it into the main preview
- Zoom stays tied to the main preview only
- Derived preview actions may replace the parent thumbnail when appropriate

### Important Behavior

For actions like:

- Upscale Lab
- Selective Repair
- ADetailer / detailer pass
- Identity Rescue
- Local repair

Neo treats the result as a **derived output** from the selected parent image.

When the derived action is meant to improve the current image, Neo replaces the parent preview in the run gallery instead of adding confusing duplicate thumbnails.

---

# Preview Action Buttons

The preview action buttons are grouped into three lanes:

- Source
- Reference
- Finish

Each lane sends the active output to a different part of the Image workflow.

---

## 1. Source Actions

Source actions reuse the current output as the main source image for another generation workflow.

---

### 🖼️ Send to Img2Img

**Button ID:** `btn-generation-preview-img2img`  
**Action:** `sendGenerationPreviewToMode('img2img')`

### What it does

- Takes the active preview image
- Sends it into the source image input
- Switches the workflow type to `img2img`
- Keeps the image ready for image-to-image regeneration

### When to use

Use this when the output is close, but you want to regenerate it with:

- Better prompt control
- Slight variation
- Lower denoise refinement
- Style adjustment

### User note

Img2Img is best when the image is already useful and you want to guide it, not fully rebuild it.

---

### 🩹 Send to Inpaint

**Button ID:** `btn-generation-preview-inpaint`  
**Action:** `sendGenerationPreviewToMode('inpaint')`

### What it does

- Sends the active preview image into the source image input
- Switches workflow type to `inpaint`
- Clears any existing mask image
- Prompts the user to add or draw a mask next

### When to use

Use this when you want to repair only part of the image, such as:

- Face
- Hand
- Clothing detail
- Background object
- Small artifact

### Important

After sending to Inpaint, you still need to add/draw the mask. The button only prepares the image for inpainting.

---

### ↔️ Send to Outpaint

**Button ID:** `btn-generation-preview-outpaint`  
**Action:** `sendGenerationPreviewToMode('outpaint')`

### What it does

- Sends the active preview image into the source image input
- Switches workflow type to `outpaint`
- Clears any existing mask image
- Prepares the image for canvas expansion

### When to use

Use this when you want to extend the image beyond its original frame:

- Add more background
- Widen composition
- Turn a tight crop into a larger scene
- Extend top/bottom/side areas

### Important

After sending to Outpaint, set the padding directions and outpaint settings before queueing.

---

## 2. Reference Actions

Reference actions reuse the current output as a guide image for another generation.

---

### 🎯 Send to ControlNet Reference

**Button ID:** `btn-generation-preview-controlnet`  
**Action:** `sendGenerationPreviewToReferenceLane('controlnet')`

### What it does

- Sends the active preview image into the ControlNet image input
- Enables ControlNet
- Opens the ControlNet settings area
- Prompts the user to confirm model, preprocessor, and strength

### When to use

Use this when you want to preserve or guide:

- Pose
- Composition
- Edges
- Depth
- Layout

### Example

Generate one image, then send it to ControlNet to keep the same pose while changing the style or character details.

---

### 👤 Send to IP-Adapter Reference

**Button ID:** `btn-generation-preview-ipadapter`  
**Action:** `sendGenerationPreviewToReferenceLane('ipadapter')`

### What it does

- Sends the active preview image into the IP-Adapter image input
- Enables IP-Adapter
- Opens the IP-Adapter settings area
- Prompts the user to confirm mode, model, and CLIP Vision settings

### When to use

Use this when you want to reuse visual identity or style from the current output, such as:

- Face likeness
- Character look
- Clothing style
- General visual identity

### Family limitation

For Qwen Image Edit, this action is disabled because that family uses Qwen multi-source references instead of the normal IP-Adapter lane.

---

## 3. Finish Actions

Finish actions run a new derived pass using the active output as the source.

These actions are designed to improve the selected output without forcing the visible workspace mode to switch.

---

### ✨ Run Upscale Lab

**Button ID:** `btn-generation-preview-hires`  
**Action:** `runGenerationPreviewHiresFix()`

### What it does

- Uses the active output as the source
- Queues an Upscale Lab / high-res style pass
- Enables refine settings internally
- Keeps batch size at `1`
- Opens the Enhance / Upscale Lab settings
- Keeps visible workspace mode unchanged

### Uses settings from

- Refine steps
- Refine denoise
- Refine scale
- Refine mode
- Selected upscaler

### When to use

Use this when the image is good but needs:

- Higher resolution
- Better detail
- Cleaner final output
- Final polish before saving/exporting

---

### 🩹+ Run Selective Repair

**Button ID:** `btn-generation-preview-detailer`  
**Action:** `runGenerationPreviewDetailerPass()`

### What it does

- Uses the active output as the source
- Queues a Selective Repair / detailer pass
- Opens the Enhance / Selective Repair settings
- Keeps visible workspace mode unchanged

### Requirement

Selective Repair must already be enabled/configured.

If it is not configured, Neo warns the user and opens the Selective Repair settings instead of queueing blindly.

### When to use

Use this when only specific parts need fixing:

- Face detail
- Eyes
- Hands
- Small artifacts
- Character cleanup

---

### 🧬 Run Identity Rescue / FaceID

**Button ID:** `btn-generation-preview-identity`  
**Action:** `runGenerationPreviewIdentityRescuePass()`

### What it does

- Uses the active output as the source
- Queues an Identity Rescue pass
- Requires at least one FaceID IP-Adapter setup
- Adjusts denoise into a safer identity-preservation range
- Keeps visible workspace mode unchanged

### Requirement

At least one IP-Adapter unit must be configured in FaceID mode.

If no FaceID setup exists, Neo warns the user and opens the IP-Adapter settings.

### When to use

Use this when the image is mostly correct but the face/identity drifted.

Best for:

- Restoring likeness
- Improving character consistency
- Fixing face drift after generation

### Family limitation

For Qwen Image Edit, this action is disabled because Identity Rescue / FaceID is not supported for that family.

---

# Output Save Settings Near Preview

The preview area also contains output destination controls.

## Output Root Folder

Controls where generated images are saved.

### Buttons

- **Browse** → choose output root folder
- **Open** → open the current output folder

---

## Category

Used to organize outputs into folders or logical groups.

Examples:

- Uncategorized
- Characters
- Portraits
- Asian Men
- Product Tests

---

## Add Category

Creates a new category option.

Use this to keep outputs organized by project, style, character, or client.

---

## Save Path Preview

Shows where Neo will save the output once settings are loaded.

This helps prevent images from being saved into the wrong folder.

---

# Recommended User Workflow

## After generating an image

1. Check the main preview
2. Click thumbnails in Current Run Outputs to choose the best result
3. Use Source buttons if you want to regenerate from the image
4. Use Reference buttons if you want the image to guide another generation
5. Use Finish buttons if the image is good and needs polish
6. Save/export from the correct output category

---

# Common Mistakes

## Running Finish before selecting the right output

Always click the correct thumbnail first.

## Sending to Inpaint and forgetting the mask

The Inpaint button only prepares the source image. You still need a mask.

## Using Identity Rescue without FaceID setup

Identity Rescue requires FaceID IP-Adapter setup first.

## Sending everything to ControlNet

Use ControlNet when you need structure/pose/layout control, not for every image.

## Treating object/detail fixes as full regeneration

If only one detail is wrong, use Inpaint or Selective Repair instead of regenerating the whole image.

---

# Practical Notes

- Preview actions work on the active selected output
- Derived actions usually run as single-image follow-up passes
- Finish actions preserve the visible workspace mode
- Qwen Image Edit disables unsupported IP-Adapter / Identity Rescue buttons
- The preview area is the fastest way to turn a good image into a refined final image

---

## Screenshot Placeholders

### Image Preview Area

(Add screenshot here)

### Current Run Outputs

(Add screenshot here)

### Preview Action Buttons

(Add screenshot here)

### Output Save Settings

(Add screenshot here)
