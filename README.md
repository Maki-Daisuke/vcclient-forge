# VCClient Forge

> **A modernized, high-performance RVC fork of w-okada/voice-changer optimized for pure ONNX Runtime and modern CUDA environments.**

This project is a modernized **spiritual successor** to [`w-okada/voice-changer`](https://github.com/w-okada/voice-changer) (a.k.a. W-Okada VC), originally created by **[w-okada](https://x.com/DannadoriYellow)**. We deeply respect and honor w-okada's pioneering contributions to the real-time AI voice conversion community.

> [!NOTE]
> **For Japanese speakers:** 日本語で読まれる場合は、ブラウザの翻訳機能（右クリック「日本語に翻訳」など）をご利用ください。

---

## Project Goals

- **Spiritual Successor to the Golden Standard (v2.0.78)**:
  Designed as a community-driven spiritual successor to the most widely adopted and beloved version (`v2.0.78`), honoring the original vision while breathing new life into the established ecosystem.
- **Windows-First Portable Experience**:
  Prioritizing the standalone Windows ZIP distribution as our first-class citizen. Our primary mission is ensuring seamless, zero-config local execution on Windows gaming and streaming rigs.
- **Seamless Usability & Compatibility (Zero-Config Transition)**:
  Preserving the familiar UI workflows, model slots, and configuration compatibility of v2.0.78. Creators and streamers can transition immediately without re-learning or re-configuring their setups.
- **Laser-Focused on Real-Time Performance**:
  Dedicated strictly to real-time voice conversion—maximizing latency efficiency and audio stability under demanding gaming and streaming workloads.
- **Dedicated RVC Client**:
  Exclusively specialized for RVC to deliver a clean, efficient, and intuitive real-time voice conversion experience.
- **Future-Proof Maintainability**:
  Engineered to smoothly track modern Python (3.14+) and newer GPU driver architectures, ensuring long-term reliability without bit-rot.

---

## Technical Strategy (How We Achieve It)

- **Decoupling PyTorch toward a "Pure-ONNX" Runtime**:
  Aiming to streamline the entire inference pipeline exclusively into ONNX. By intentionally shedding heavy PyTorch dependencies, we dramatically minimize dependency conflicts and shrink standalone distributions to a fraction of their original size.
- **Deterministic Package Management ([uv](https://docs.astral.sh/uv/))**:
  Employing `pyproject.toml` and a locked dependency manifest (`uv.lock`) for lightning-fast, 100% reproducible environments.
- **Platform Scope & Support Boundaries**:
  - **Windows**: Primary target. Officially supported and validated for portable ZIP distributions and source execution.
  - **Linux & macOS**: Best-effort basis. Startup scripts and hardware extras are maintained, but formal validation is not guaranteed.
  - **Docker & Google Colab**: Explicitly out of scope. Containerized and cloud-hosted environments are not officially supported; users requiring these setups may adapt the source independently (though doing so should be significantly easier and cleaner than before thanks to `uv` and deterministic dependency locks).
- **Multi-Edition Hardware Adapters**:
  Providing tailored extras (`cuda`, `dml`, `mac`, `cpu`) so NVIDIA, AMD, Intel, and Apple Silicon users each get optimal hardware acceleration.
- **Streamlined Pure-ONNX Pitch Estimation (RMVPE & FCPE Only)**:
  Consolidating pitch estimation exclusively to the gold standard (RMVPE) and a newer, ultra-fast alternative (FCPE) running torch-free via ONNX Runtime and NumPy. See [OKF Documentation](okf/streamlined-pitch-estimation-and-torch-free-pipeline.md) for details.
- **Standalone Portable Packaging**:
  Automated bundling of isolated Python runtimes and Web UI assets into portable zip packages (`scripts/build_package.py`).

---

## Quick Start

### 1. Prerequisites

- **[uv](https://docs.astral.sh/uv/getting-started/installation/)**: Fast, deterministic Python environment and package manager.

  ```bash
  # Windows (PowerShell)
  powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

  # Linux & macOS
  curl -LsSf https://astral.sh/uv/install.sh | sh
  ```

- **[Node.js](https://nodejs.org/) & npm**: Task runner and frontend workspace manager (Node.js v24+ / v26 LTS recommended).
- **System Audio Dependency (Linux only)**: Required by `sounddevice`:
  ```bash
  sudo apt-get update && sudo apt-get install -y libportaudio2
  ```

### 2. Clone and Setup Environment

Clone the repository and build both frontend assets and backend runtime for your target hardware in one step:

```bash
git clone https://github.com/Maki-Daisuke/vcclient-forge.git
cd vcclient-forge

# Choose ONE edition matching your hardware (builds Web UI and syncs Python runtime):
npm run build:cuda    # NVIDIA GPU (Windows / Linux)
npm run build:dml     # Windows Universal GPU (DirectX 12: AMD, Intel, NVIDIA)
npm run build:mac     # macOS (Apple Silicon M-series)
npm run build:cpu     # Generic CPU fallback
```

_(Python 3.14 is automatically downloaded and isolated by `uv`—no system Python installation required!)_

### 3. Launch

Run from source using npm or the CLI:

- **npm (Unified)**: Run `npm start`.
- **CLI (Direct)**: Run `uv run --project backend python backend/main.py`.

The `start.bat` and `start.sh` launchers are for extracted portable packages only; they run the bundled executable.

Once started, open your web browser and navigate to:

```text
http://localhost:18888/
```

Initial model assets will be downloaded automatically on first launch.

---

## Development & Build Guide

For source code development, running automated test suites, code formatting/linting, and building standalone packages, please refer to the dedicated [Developer & Build Guide (README_dev.md)](README_dev.md).

---

## Terms of Use for Bundled Voice Models

The bundled initial voice models are provided courtesy of their respective original creators. The **official Japanese terms of service take precedence**; please review the official links before using converted voices:

### 1. Tsukuyomi-chan (つくよみちゃん)

- **Official Website & License:** [Tsukuyomi-chan Corpus](https://tyc.rei-yumesaki.net/material/corpus/) (CV: Rei Yumesaki / © Rei Yumesaki)
- **Key Prohibitions:**
  - Harassing, attacking, or criticizing others.
  - Promoting specific political or religious causes.
  - Distributing explicit or sensitive content without proper zoning.
  - Secondary redistribution of converted voice as raw audio material.

### 2. Amitaro (あみたろ)

- **Official Website & License:** [Amitaro's Voice Material Workshop](https://amitaro.net/voice/faq/#index_id6)
- **Key Guidelines:**
  - You **must clearly state** that the voice has been converted using Amitaro (or Koharune Ami) and that she is not speaking directly.
  - Do not use for defamatory, sensitive, or offensive content violating Amitaro's guidelines.

### 3. Kikoto Mahiro & Kurage (黄琴まひろ / 黄琴海月)

- **Official Website & License:** [Replica Doll (れぷりかどーる)](https://kikyohiroto1227.wixsite.com/kikoto-utau/terms-of-service)
- **Key Guidelines:**
  - Please adhere to the character guidelines published on the Replica Doll official site.

---

## Acknowledgments

- **Original Project**:
  - Original VCClient developed by [w-okada](https://github.com/w-okada/voice-changer).
- **Character Voice Corpora**:
  - [Tsukuyomi-chan Corpus](https://tyc.rei-yumesaki.net/) (© Rei Yumesaki)
  - [Amitaro's Voice Material Workshop](https://amitaro.net/)
  - [Replica Doll (れぷりかどーる)](https://kikyohiroto1227.wixsite.com/kikoto-utau)

---

## Disclaimer

The author and contributors assume no liability for any direct, indirect, incidental, consequential, or special damages arising out of the use of or inability to use this software.
