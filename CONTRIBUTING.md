# Contributing to Neo Studio

Thank you for your interest in contributing to **Neo Studio**. 🙌

Neo Studio is a structured, system-based project. Contributions are welcome, but to keep the system stable and maintainable, please follow the guidelines below.

---

## 🧠 Project Philosophy

Neo Studio is designed as:

* A **local-first AI workflow system**
* A **modular and structured environment**
* A tool focused on **clarity over chaos**

When contributing, aim to:

* Keep systems clean and traceable
* Avoid breaking cross-tab workflows
* Improve usability without adding unnecessary complexity

---

## 🚀 Getting Started

1. Fork the repository
2. Clone your fork:

```bash
git clone https://github.com/YOUR_USERNAME/Neo_Studio.git
cd Neo_Studio
```

3. Set up the environment:

```bash
setup_neo_studio_venv.bat
```

4. Run the app:

```bash
run_neo_studio.bat
```

---

## 🧩 Types of Contributions

You can contribute in the following ways:

### 🐛 Bug Fixes

* Fix UI issues
* Fix broken workflows
* Improve stability

---

### ✨ Improvements

* UI/UX enhancements
* Performance improvements
* Better workflow clarity

---

### 📚 Documentation

* Improve guides in `docs/`
* Update README or usage instructions
* Add missing explanations

---

### ⚙️ System Enhancements

* Add new features carefully
* Improve existing systems without breaking structure

---

## 🔒 Contribution Rules

### 1. Do NOT break existing workflows

Key flows to keep stable:

* Image → Prompt → Assistant
* Roleplay → Scene → Stories

---

### 2. Follow existing structure

Do not:

* Move core files randomly
* Rename systems without reason
* Mix unrelated logic into one place

---

### 3. Keep changes focused

* One feature per PR
* One fix per PR
* Avoid large unrelated changes

---

## 🧪 Testing

Before submitting:

* Run the app locally
* Test the affected tab/system
* Check for:

  * UI errors
  * Console errors
  * Broken workflows

---

## 🔄 Pull Request Process

1. Create a new branch:

```bash
git checkout -b feature/your-feature-name
```

2. Make your changes

3. Commit clearly:

```bash
git commit -m "Fix: Describe what you fixed"
```

4. Push:

```bash
git push origin feature/your-feature-name
```

5. Open a Pull Request

---

## 🧾 Commit Guidelines

Use clear messages:

* `Fix: backend launcher issue`
* `Add: scene director improvements`
* `Update: image tab guide`

Avoid:

* vague messages like “update stuff”

---

## ⚠️ Areas That Require Extra Care

Be cautious when modifying:

* Roleplay system (Forge / Scene)
* Assistant behavior and responses
* Prompt → Image workflows
* Backend launcher

These systems affect multiple parts of the app.

---

## 💬 Communication

* Be clear and respectful
* Explain your changes
* Ask questions if unsure

---

## 🚧 Project Status

Neo Studio is in **active development (V1)**.

Expect:

* Changes in structure
* Evolving systems
* Ongoing improvements

---

## 🙌 Final Note

Contributions are appreciated, but stability and structure come first.

If you're unsure about a change, open an issue before implementing it.

---

Thank you for helping improve Neo Studio 💙
