# Image Tab — Assets → Scene Director Guide

## 🎬 Overview

The **Scene Director** is an advanced system that allows you to control different parts of an image using **region-based prompting**.

Instead of relying on a single global prompt, you can:

* Divide the image into regions
* Assign different prompts to each region
* Control characters, objects, and composition independently

This is especially useful for complex scenes with multiple subjects.

---

## 🧠 What Scene Director Solves

Normal prompting struggles with:

* Multiple characters
* Overlapping styles
* Missing details
* Incorrect object placement

Scene Director fixes this by:

* Giving **localized control**
* Improving **prompt accuracy**
* Reducing **prompt conflicts**

---

## ⚙️ Enabling Scene Director

* Toggle **Enable Scene Director**
* Once enabled:

  * Global prompt becomes base
  * Regions override or refine specific areas

---

## 🧩 Core Components

---

## 👤 1. Identity Profiles

### Purpose

Reusable character setups.

Includes:

* Reference images
* FaceID / IPAdapter settings
* Weights
* Optional LoRA
* Notes

---

### Behavior

* Assigning a profile automatically:

  * Overrides manual IPAdapter
  * Prepares identity routing for the region

---

### When to use

* Maintaining character consistency
* Reusing the same person across scenes
* Avoiding manual reconfiguration

---

## 🎛️ 2. Scene Presets

### Purpose

Save and reuse full scene setups.

Includes:

* Global prompt
* Region layout
* Region prompts
* IPAdapter bindings
* LoRA mappings

---

### When to use

* Repeating complex scenes
* Keeping consistent layouts
* Speeding up workflow

---

## 🧱 3. Region Layout Presets

### Purpose

Quickly generate region boxes.

---

### Behavior

* Creates structured layouts (e.g., split scenes)
* Keeps existing prompts by index unless replaced

---

### When to use

* Multi-character scenes
* Standard compositions
* Fast setup

---

## 🧭 4. Canvas Regional Editor

### Purpose

Visual control over where each prompt applies.

---

### Features

* Add region boxes
* Drag to reposition
* Resize with handles
* Label each region

---

### Example Layout

* Left → Person 1
* Right → Person 2
* Center → Object

---

### Important Rule

> Regions define *where influence happens*, not exact pixel control.

---

## 🧩 5. Region Controls

Each region has its own configuration.

---

### Region Type

* Character → human subject
* Object → item or detail

---

### Core Actions

* Lock → prevent changes
* Hide → temporarily disable
* Duplicate → copy region
* Delete → remove region

---

## ✍️ 6. Region Prompt

### Purpose

Defines what appears in that specific region.

---

### Example (Character)

```text
1boy, short Sri Lankan man, shy expression, oversized hoodie, holding a rose flower
```

---

### Example (Object)

```text
pink hoodie
```

---

### Behavior

* Overrides global prompt locally
* Works together with base prompt

---

## ➖ 7. Region Negative Prompt

### Purpose

Remove unwanted elements *only in that region*.

---

### Example

```text
female, beard, extra limbs
```

---

### Use Case

* Cleaning character features
* Preventing style bleed
* Removing conflicting elements

---

## 🎚️ 8. Prompt Strength

### Purpose

Controls how strongly the region prompt affects the image.

---

### Behavior

* Low → subtle influence
* High → strong override

---

### Typical Range

* 1.2 – 1.8 → balanced
* Higher → more control but risk of artifacts

---

## 🧠 9. IPAdapter (Per Region)

### Purpose

Bind reference images to specific regions.

---

### Behavior

* Uses global IPAdapter slot
* Applies only within region mask
* Prevents identity bleeding

---

### Important Note

> When Scene Director is ON, global IPAdapter is suppressed
> → Only region-bound adapters are used

---

## 🧩 Controls

* Binding → enable/disable region binding
* Region Mask → apply only within region
* Weight → control influence strength

---

## 🎯 How Regions Actually Work (Important)

Regions are **not always required**.

Use them when:

* Prompt is not being respected
* Details are missing
* Multiple subjects conflict

---

## 💡 Example: Fixing Missing Details

### Problem

Prompt says:

```text
wearing a pink hoodie
```

But result:

* Hoodie not pink
* Colors overridden by other elements

---

### Solution

1. Create **Object Region**
2. Place over hoodie area
3. Add prompt:

```text
pink hoodie
```

4. Adjust strength

---

### Result

* Higher chance of correct color
* Better detail consistency

---

## 🔄 Typical Workflows

---

### Multi-Character Scene

1. Add 2 character regions
2. Assign prompts individually
3. Adjust positions

---

### Character + Object Control

1. Add character region
2. Add object region (e.g., flower, clothing)
3. Fine-tune prompts

---

### Identity Consistency

1. Assign Identity Profile
2. Use region IPAdapter
3. Lock identity

---

## ⚠️ Common Mistakes

* Using too many regions
* Overlapping regions incorrectly
* Setting too high prompt strength
* Forgetting global prompt still matters

---

## 💡 Tips

* Start simple → add regions only when needed
* Use object regions for problem fixing (not default use)
* Keep region prompts focused
* Combine with good base prompt

---

## 📸 Sample Scenario

Global Prompt "2boys, cinematic romantic closeup shot of a gay couple standing together in a cozy neon-lit city street at night, soft rain, warm reflections, looking at each other affectionately, emotional storytelling, stylish modern outfits, shallow depth of field, high detail, natural skin, beautiful composition, "

Scene Director:
Person 01 "1boy, a short Sri Lankan man, dark brown skin, stubble, looks shy, keeping his head on his boyfriend's shoulder, shorter than his boyfriend, wearing a oversize red hoodie and short shorts, holding a rose flower"
Person 02 "1boy, a tall chineese boy, skinny, Joong char, fair light skin, colored pink spiky hair, wearing spectacles, holding his boyfriend closer to his chest, he seems caring and protective of his boyfriend, taller than his boyfriend, wearing a chineese street wear with a pink jacket and yellow jogger pants,"
Flower "rose flower"
Hoodie "Pink Jacket"

![Image](assets/Image/ss06.png)
![Image](assets/Image/ss05.png)

---