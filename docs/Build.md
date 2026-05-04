### 🏗️ Build

## 🏗️ Overview

The **Build section** is the core of image generation in Neo Studio.

This is where you:

* Define how the image is generated
* Control model behavior
* Adjust quality, structure, and randomness
* Select sampler engines and advanced generation systems

Everything else (Reference, Finish, etc.) builds *on top of this*.

---

## 🧠 Core Components

---

## 🎯 1. Model Selection

### Checkpoint

* Main model used for generation
* Defines overall style, realism, and capability

**Example:**

* Realistic → photoreal models
* Stylized → anime/art models

---

### VAE

* Controls color accuracy and decoding quality
* Usually paired with the model

👉 If images look:

* Washed out → VAE issue
* Over-saturated → VAE mismatch

---

## ⚙️ 2. Sampling System

---

### Sampling Method

Controls how the image is generated step-by-step.

Example:

* `dpmpp_2m_sde_heun_gpu`

This affects:

* Detail quality
* Stability
* Speed

---

### Schedule Type

Controls how noise is reduced over time.

Example:

* `karras`

👉 Think of this as the *curve* of how the image forms.

---
![Image](assets/Image/ss01.png)
---

## 🚀 3. RES4LYF Sampler Support

### What it is

An advanced sampler compatibility + enhancement layer.

Neo detects compatible samplers and allows switching between optimized presets.

---

### Available Modes

* **RES Balanced**

  * Safe default
  * Stable results

* **RES Detail Slow**

  * Higher detail
  * Slower generation

* **RES Experimental**

  * New/untested behavior
  * Can improve or break results

---

### Important Notes

* Works only with compatible samplers
* Automatically switches sampler/scheduler internally
* Safe for txt2img/img2img workflows

---

### When to use

* Use **Balanced** for normal work
* Use **Detail Slow** for final renders
* Use **Experimental** only for testing

---
![Image](assets/Image/ss02.png)
---

## 🧪 4. Sampler Engine

---

### Core KSampler

Default generation engine.

* Stable
* Fully supported
* Recommended for most workflows

---

### Advanced Engine (ClownsharkSampler)

* Replaces base KSampler internally
* Adds experimental behavior
* Can improve queue/runtime efficiency

⚠️ Use only if:

* You know the workflow supports it
* You’re testing performance or behavior

---
![Image](assets/Image/ss03.png)
---

## 📐 5. Resolution & Batch

---

### Width / Height

Defines output resolution.

Example:

* 896 × 1344 (portrait)

👉 Important:

* Higher = more detail + more VRAM usage
* Lower = faster but less detail

---

### Batch Size

* Number of images generated at once

👉 Keep low unless:

* You have enough VRAM
* You need multiple variations

---

## ⏱️ 6. Steps

* Number of iterations used to refine the image

Typical:

* 20–30 → fast
* 30–50 → balanced
* 50+ → diminishing returns

---

## 🎚️ 7. CFG (Classifier-Free Guidance)

Controls how strongly the prompt is followed.

---

### Behavior

* Low CFG → more creative / loose
* High CFG → strict / prompt-heavy

---

### Example

* 5–8 → soft / artistic
* 8–12 → balanced
* 12–15+ → rigid / overforced

---

## 🧠 8. CFG Fix / Dynamic Thresholding

---

### What it does

Prevents:

* Overexposure
* Burned highlights
* Over-saturated outputs

---

### Key Settings

#### Preset

* Simple / Full
* Controls how aggressive correction is

---

#### Mode

* Full = full dynamic control
* Simpler modes reduce intervention

---

#### Mimic CFG

* Simulates a lower CFG internally
* Helps reduce harshness

---

#### Threshold Percentile

* Controls clipping level
* Lower = stronger correction

---

### When to use

Use this when:

* High CFG causes artifacts
* Image looks too “burned”
* Details are getting destroyed

---
![Image](assets/Image/ss04.png)
---

## 📦 9. Size Presets

* Save commonly used resolutions
* Speeds up workflow

Example:

* Portrait preset
* Landscape preset

---

## 🎲 10. Seed

Controls randomness.

---

### Behavior

* `-1` → random seed
* Fixed number → reproducible result

---

### When to use

* Use random for exploration
* Use fixed seed for:

  * Iteration
  * Refinement
  * Consistency

---

## 🔄 Typical Workflows

---

### Basic Generation

1. Select model
2. Set resolution
3. Adjust CFG + steps
4. Generate

---

### High Quality Output

1. Enable RES4LYF (Detail Slow)
2. Increase steps
3. Adjust CFG Fix
4. Generate

---

### Controlled Testing

1. Fix seed
2. Change one parameter
3. Compare results

---

## ⚠️ Common Mistakes

* Too high CFG → broken images
* Too many steps → wasted time
* Wrong sampler + scheduler combo
* Ignoring VAE mismatch

---

## 💡 Tips

* Start simple → refine later
* Don’t stack too many advanced features at once
* Use presets for consistency
* Always test with fixed seed when tuning

---