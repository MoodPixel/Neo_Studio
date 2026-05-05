# Image Tab Guide

## 🎨 Overview

The **Image Tab** is designed to simplify complex image generation workflows by dividing them into clear, structured sections.

Instead of managing everything in one place, Neo Studio organizes the process into stages—from building the image to refining and exporting it.

### Image backend:
Launch Backend > Connect Backend

### Model family selector:
Select the Model family (SDXL/SD 1.5), use the same

### Image workspace:
which pipeline you are working on, txt2img, img2img, inpaint, or outpaint

---

## 🧱 Workflow Structure

The Image Tab is divided into the following main sections:

* Prompt Stack
* Image Preview
* Build
* Assets
* Reference
* Finish
* Results

Each section represents a stage in the image creation pipeline.

---

## 🧩 Sections

---

### 🏗️ Build

**Purpose:**
This is where the main image generation setup happens.

You define:

* Prompt and negative prompt
* Model and sampler settings
* Resolution and steps
* Core generation parameters

This is the starting point for all image workflows.

**Typical use:**

* Creating new images from scratch
* Testing prompts
* Adjusting base generation settings

---

### 🧰 Assets

**Purpose:**
Manage reusable creative assets and enhancements.

Includes:

* LoRA / embeddings / styles
* Prompt helpers or presets
* Reusable configurations

This section helps speed up workflow by reusing elements instead of rebuilding each time.

**Typical use:**

* Applying style consistency
* Reusing character looks
* Managing prompt presets

---

### 🧭 Reference

**Purpose:**
Control structure and visual guidance using reference inputs.

Includes:

* ControlNet inputs (pose, depth, edges, etc.)
* Reference images
* Identity or composition guidance

This is where you influence *how* the image should look structurally.

**Typical use:**

* Pose matching
* Composition control
* Identity consistency

---

### 🛠️ Finish

**Purpose:**
Refine and enhance generated images.

Includes:

* Upscaling
* Inpainting / selective repair
* ADetailer and cleanup tools
* Final polish adjustments

This is where rough outputs become final results.

**Typical use:**

* Fixing faces or details
* Improving resolution
* Cleaning artifacts

---

### 📦 Results

**Purpose:**
View, manage, and export generated images.

Includes:

* Output previews
* Saved results
* Metadata inspection
* Image selection

This is the final stage of the workflow.

**Typical use:**

* Reviewing outputs
* Selecting best results
* Exporting or reusing images

## 🎥 Image Tab Guide (Video)

Learn how to use the full Image Tab workflow in Neo Studio:

[![Neo Studio Image Tab Guide](https://img.youtube.com/vi/yyIaZ-ZTu-0/0.jpg)](https://youtu.be/yyIaZ-ZTu-0)

This guide covers:

- Prompt Stack  
- Image Preview  
- Build settings  
- Scene Director (region-based prompting)  
- Reference (ControlNet workflows)  
- Finish (upscale & fixes)  
- Results  

More detailed section-by-section guides will be added as separate videos.

---

## 🔄 Common Workflows

### Basic Image Creation

1. Go to **Build**
2. Enter prompt and settings
3. Generate image
4. Review in **Results**

---

### Controlled Generation (Pose / Structure)

1. Setup in **Build**
2. Add reference in **Reference**
3. Generate image
4. Adjust as needed

---

### High-Quality Final Output

1. Generate in **Build**
2. Refine in **Finish**
3. Upscale and clean
4. Export from **Results**

---

## ⚠️ Tips

* Start simple in **Build**, then refine later
* Use **Assets** to save time on repeated styles
* Use **Reference** only when needed (can over-constrain results)
* Always finalize in **Finish** for best quality

---

## 🚧 Current Limitations

* Some advanced workflows may require manual tuning
* Performance depends on your local setup and backend
* Certain features may evolve in future updates

---

## 🚀 Planned Improvements

* Better workflow presets
* Improved preview and comparison tools
* More automation for common tasks
* Enhanced ControlNet and refinement tools

---
