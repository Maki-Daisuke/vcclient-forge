# VCClient Forge

> **A modernized, high-performance RVC fork of w-okada/voice-changer optimized for pure ONNX Runtime and modern CUDA environments.**

This project is a modernized **spiritual successor** to [`w-okada/voice-changer`](https://github.com/w-okada/voice-changer) (a.k.a. W-Okada VC), originally created by **[w-okada](https://x.com/DannadoriYellow)**. We deeply respect and honor w-okada's pioneering contributions to the real-time AI voice conversion community.

> [!NOTE]
> **For Japanese speakers:** 日本語で読まれる場合は、ブラウザの翻訳機能（右クリック「日本語に翻訳」など）をご利用ください。

---

## Quick Start

### 1. Download the Release Package

Download the standalone package matching your hardware from **[GitHub Releases](https://github.com/Maki-Daisuke/vcclient-forge/releases)**:

If you have an NVIDIA GPU, download the package with the `cuda` edition for optimal performance; otherwise, the `cpu` edition is recommended.

### 2. Launch

Extract the archive to any folder and run:

- **Windows Desktop App (Recommended)**:
  Double-click **`vcclient-forge.exe`**.
- **Web Browser Mode (Classic)**:
  Double-click **`start.bat`** (Windows) or execute **`./start.sh`** (Linux / macOS).
  Your default web browser will automatically open:
  ```text
  http://localhost:18888/
  ```

> [!NOTE]
> Initial model assets will be downloaded automatically on first launch. This may take a few moments depending on your internet connection.

### Migrating from w-okada VC (v2.0.78)

To transfer your existing models and settings, simply copy the **`settings`** and **`model_dir`** folders from your original v2.0.78 directory into the extracted Forge folder.

### Linux only

Linux requires the PortAudio system library for audio device I/O:

```bash
# Ubuntu / Debian
sudo apt-get update && sudo apt-get install -y libportaudio2
```

---

## Project Goals (Still on Our Way)

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
