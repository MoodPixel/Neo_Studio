# Prompt Stack Guide

## 🧠 Overview

The **Prompt Stack** is the control center for all prompt-related input in the Image Tab.

It manages:

* Your working prompt
* Saved prompt reuse
* Prompt Studio / Caption Studio integration
* Prompt conditioning behavior

This is where you define *what the image should be*, before the Build section defines *how it is generated*.

---

## 🧩 Structure

The Prompt Stack is divided into:

* Working Copy
* Saved Prompt
* Positive Prompt
* Prompt Conditioning
* Negative Prompt

---

## 📝 1. Working Copy

### Purpose

Acts as a **live draft system** for prompts.

* Stores your current working prompt
* Allows switching between tools without losing progress

---

### Key Actions

* **Open Prompt Studio**

  * Generate or refine prompts

* **Open Caption Studio**

  * Convert images → prompts

* **Open Library**

  * Load previously saved prompts

---

### Behavior

* Always keeps the latest version
* Acts as a buffer between tools and generation

---

### When to use

* Iterating on prompts
* Testing variations
* Moving between tools without losing edits

---

## 💾 2. Saved Prompt

### Purpose

Load and manage stored prompts.

---

### Features

* Dropdown selection of saved prompts
* Quick load into working copy
* Save / overwrite / manage presets

---

### Typical use

* Reusing proven prompts
* Maintaining consistency across generations
* Storing project-specific styles

---

## ✍️ 3. Positive Prompt

### Purpose

Defines what should appear in the image.

---

### Behavior

* Directly controls:

  * Content
  * Style
  * Composition
  * Mood

---

### Example

```text
2boys, cinematic romantic closeup shot, cozy neon-lit city street at night...
```

---

### Best Practices

* Start broad → refine
* Structure prompts logically:

  * Subject → environment → style → details
* Avoid overloading too many concepts

---

### Common Issues

* Too long → muddy results
* Conflicting descriptions → unstable outputs

---

## ⚙️ 4. Prompt Conditioning

---

### What it does

Controls how the prompt is interpreted before encoding.

---

### Modes

#### Raw (default)

* Prompt is sent exactly as written
* No processing or weighting

👉 Best when:

* You already know what you’re doing
* Using structured prompt syntax

---

#### Weight Handling

* Controls emphasis behavior
* Can affect how strongly parts of the prompt are applied

---

#### Clip Skip

* Adjusts how deep the model reads the prompt

Typical:

* Off → default behavior
* Higher → can change style/interpretation

---

#### Prompt Health

Example:

* **Clean**

Indicates:

* No obvious structural issues
* Prompt is safe to process

---

### Important Note

> Prompt conditioning is "idle" in Raw mode
> → No hidden modifications are applied

---

## ➖ 5. Negative Prompt

### Purpose

Defines what should be removed or avoided in the image.

---

### Example

```text
low quality, blurry, bad anatomy, extra fingers, watermark, oversaturated
```

---

### What it controls

* Artifacts
* Quality issues
* Undesired styles

---

### Best Practices

* Keep it focused
* Don’t overstack unnecessary negatives
* Use common stable negatives

---

## 🔄 Prompt Flow

```text
Prompt Studio / Caption Studio / Library
        ↓
   Working Copy
        ↓
 Positive + Negative Prompt
        ↓
 Prompt Conditioning
        ↓
 Sent to Build → Generation
```

---

## ⚠️ Common Mistakes

* Editing prompt directly without saving
* Overloading prompt with too many ideas
* Ignoring negative prompt entirely
* Using high CFG without adjusting prompt quality

---

## 💡 Tips

* Use Prompt Studio for ideation
* Use Saved Prompts for consistency
* Keep a clean working copy
* Pair strong prompts with proper CFG settings

---

## 📸 Screenshot

![Image](assets/Image/ss00.png)

---