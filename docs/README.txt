======================================================================
  VCClient Forge - Quick Start Guide
======================================================================
* For Japanese instructions, please see README_ja.txt.

Thank you for downloading VCClient Forge!

----------------------------------------------------------------------
1. How to Launch
----------------------------------------------------------------------

* Note for CUDA edition (Windows / Linux):
  Please update your NVIDIA GPU driver to the latest version before use
  (CUDA 13-compatible, R580 or newer). CUDA Toolkit and cuDNN are bundled,
  so separate installation is not required.

Windows
-------

[Desktop App (Recommended)]

Double-click "vcclient-forge.exe".

[Web Browser Mode]

Double-click "start.bat".
Your default browser will automatically open at:
http://localhost:18888/

macOS
-----

[Desktop App (Recommended)]

First Launch: Open Terminal in this folder and run:

  sh MacStart.command

* For subsequent launches, simply double-click "MacStart.command" in Finder!

[Web Browser Mode]

Open Terminal in this folder and run:

  ./start.sh

Your default browser will automatically open at:
http://localhost:18888/

Ubuntu Linux
------------

[Requirements & Dependencies]

- OS: Ubuntu 24.04 LTS or newer (glibc >= 2.39)
- Required system packages:

  sudo apt-get update && sudo apt-get install -y libportaudio2 libwebkitgtk-6.0-4 7zip

[Desktop App (Recommended)]

Execute "./vcclient-forge" in Terminal.

[Web Browser Mode]

Execute "./start.sh" in Terminal.
Your default browser will automatically open at:
http://localhost:18888/

----------------------------------------------------------------------
2. Migrating from w-okada VC (v2.0.78)
----------------------------------------------------------------------

To transfer your existing models and settings, simply copy the
"settings" and "model_dir" folders from your original v2.0.78
directory into this folder.

----------------------------------------------------------------------
3. Initial Setup Note
----------------------------------------------------------------------

On first launch, essential AI modules (ContentVec, pitch estimators, etc.)
along with sample RVC voice models will be downloaded automatically.
This initial download may take several minutes depending on your network
connection, so please be patient and wait until it completes.

----------------------------------------------------------------------
4. Support & Links
----------------------------------------------------------------------
- Project Site: https://github.com/Maki-Daisuke/vcclient-forge
- Issues:       https://github.com/Maki-Daisuke/vcclient-forge/issues
======================================================================
