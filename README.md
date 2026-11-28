# VCClient Forge

> **An RVC-focused fork of [w-okada/voice-changer](https://github.com/w-okada/voice-changer) for real-time communication.**

<img width="741" height="640" alt="image" src="https://github.com/user-attachments/assets/50d1d022-25ed-4b03-ac0f-b4439f33cdc6" />

This project is a modernized **spiritual successor** to [`w-okada/voice-changer`](https://github.com/w-okada/voice-changer) (a.k.a. W-Okada VC), originally created by **[w-okada](https://x.com/DannadoriYellow)**. We deeply respect and honor w-okada's pioneering contributions to the real-time AI voice conversion community.

> [!NOTE]
> **For Japanese speakers:** 日本語で読まれる場合は、ブラウザの翻訳機能（右クリック「日本語に翻訳」など）をご利用ください。

---

## Quick Start

### 1. Download the Release Package

Download the standalone package matching your operating system and hardware from **[GitHub Releases](https://github.com/Maki-Daisuke/vcclient-forge/releases)**:

| Platform        | Your Hardware                  | Download Package                         | CUDA | OpenVINO | DirectML | WebGPU\* | CoreML |
| :-------------- | :----------------------------- | :--------------------------------------- | :--: | :------: | :------: | :------: | :----: |
| **Windows x64** | NVIDIA (Turing or newer)       | **`vcclient-win-x64-cuda-*.7z`**         |  ✓   |    ✓     |          |          |        |
|                 | AMD / Intel / NVIDIA / CPU     | **`vcclient-win-x64-standard-*.7z`**     |      |    ✓     |    ✓     |          |        |
| **Linux x64**   | NVIDIA (Turing or newer)       | **`vcclient-linux-x64-cuda-*.7z`**       |  ✓   |    ✓     |          |    ✓     |        |
|                 | AMD / Intel / NVIDIA / CPU     | **`vcclient-linux-x64-standard-*.7z`**   |      |    ✓     |          |    ✓     |        |
| **Linux ARM64** | NVIDIA (e.g. DGX Spark / GB10) | **`vcclient-linux-arm64-cuda-*.7z`**     |  ✓   |          |          |    ✓     |        |
|                 | Non-NVIDIA / CPU               | **`vcclient-linux-arm64-standard-*.7z`** |      |          |          |    ✓     |        |
| **macOS ARM64** | Apple Silicon (M-series)       | **`vcclient-mac-arm64-standard-*.7z`**   |      |          |          |          |   ✓    |

✓ indicates that the package supports the execution provider. Availability depends on compatible hardware and drivers. \* WebGPU support is experimental.

Windows ARM64 and Intel Mac do not have standalone packages.

> [!TIP]
>
> - **CUDA edition**: Requires a Turing-generation or newer NVIDIA GPU (including GeForce RTX 20 series and GTX 16 series) and a CUDA 13-compatible NVIDIA driver (R580 or newer). The required CUDA 13.x libraries and cuDNN 9 are bundled, so you can skip installing the CUDA Toolkit separately.
> - **Older NVIDIA GPUs on Windows**: The `win-x64-standard` edition can use DirectML on compatible devices.
> - **Intel Arc / AMD Radeon / Apple Silicon Mac**: Download the `standard` package for your platform. Use OpenVINO for Intel Arc on Windows or x64 Linux, DirectML for AMD Radeon on Windows, or CoreML on Apple Silicon.
> - **CoreML on Apple Silicon**: Can use the Apple Neural Engine or Metal GPU. Forge uses MLProgram or NeuralNetwork depending on the model and inference shape.
> - **WebGPU on Linux**: Experimental acceleration for AMD Radeon and other compatible GPUs requires a working Vulkan driver and loader (`libvulkan.so.1`). Select a `[WebGPU]` device in Settings while conversion is stopped.
> - **CPU inference**: Available in every package. ONNX Runtime can use AVX-512 on compatible x64 CPUs and Arm NEON or SVE kernels when supported by the hardware and runtime build. [ONNX Runtime CPU kernels](https://github.com/microsoft/onnxruntime/tree/main/onnxruntime/core/mlas)

Forge tries available compute devices during initial setup once a model is available. You can rerun automatic device selection in Settings while conversion is stopped. Real-time performance depends on the device and model.

### 2. Extract, Launch & Migrate

> [!IMPORTANT]
> Starting with Forge `v2.0.78-forge.0.4.0`, startup migrates numeric model folders to a NanoID catalog. Older Forge versions and w-okada VC `v2.0.78` cannot read the migrated layout. Keep a backup of `settings` and `model_dir` and copy them into a freshly extracted folder before starting Forge.

Extract the downloaded `.7z` archive to any folder (on Ubuntu/Debian, install `7zip` if needed: `sudo apt-get update && sudo apt-get install -y 7zip`). The standalone package includes Python.

For **launch steps** (Windows / macOS / Ubuntu Linux, Desktop App or Web Browser Mode), **Linux dependencies**, **initial model downloads**, and **migration from earlier releases**, see the bundled Quick Start guide:

- **English**: **[`docs/README.txt`](docs/README.txt)** (`README.txt` inside the extracted folder)
- **日本語**: **[`docs/README_ja.txt`](docs/README_ja.txt)** (`README_ja.txt` inside the extracted folder)

---

## Project Goals

- **Build on w-okada VC v2.0.78.** Carry its RVC workflows and model ecosystem forward as a community project.
- **Make portable Windows releases the primary experience.** Make Forge easy to launch locally on gaming and streaming PCs from a standalone `.7z` package.
- **Keep familiar workflows.** Help existing users bring over their RVC models and settings and continue with familiar controls. See the migration steps above when upgrading.
- **Focus on real-time RVC communication.** Prioritize low latency and stable audio during gaming, streaming, and voice chat.
- **Keep the project maintainable.** Track supported Python and accelerator runtimes and use upstream packages where possible.

### Platform Support

- **Windows** is the primary target for standalone releases and running from source.
- **Linux and macOS** receive standalone packages and best-effort support.
- **Docker and Google Colab** are outside the project's support scope.

---

## Development & Build Guide

For source code development, running automated test suites, code formatting/linting, and building standalone packages, please refer to the dedicated [Developer & Build Guide (README_dev.md)](README_dev.md).

See the [architectural and design rationales](okf/rationales.md) for Forge's technical choices. Integrations written for the old REST API or Socket.IO need to migrate to the current [HTTP and WebSocket API](okf/api-reference.md).

---

## Terms of Use for Sample Voice Models

The voice models downloaded during initial setup are provided courtesy of their respective original creators. The **official Japanese terms of service take precedence**; please review the official links before using converted voices:

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

---

## License

VCClient Forge is licensed under the MIT License. See [LICENSE](LICENSE) for the full text and copyright notices.
