# Troubleshooting

## Resetting application settings

If a settings problem prevents VCClient Forge from working, you can restore the
application settings to their defaults. Keep a backup so that you can recover your
previous settings if needed.

1. Quit VCClient Forge. If you started it using `start.bat` or `start.sh`,
   press Ctrl+C in the terminal window as well.
2. In the VCClient Forge folder, rename `settings` to `settings.bak`.
3. Start VCClient Forge again. A new `settings` folder will be created.

Models and their individual settings in `model_dir` are not changed.

To restore the backup, quit VCClient Forge as described above, rename the new
`settings` folder to an unused name, and rename the backup to `settings`.

## WebGPU device missing on Linux

WebGPU requires a Vulkan GPU driver and the system loader (`libvulkan.so.1`).
On Ubuntu the loader is provided by [`libvulkan1`](https://packages.ubuntu.com/noble/libvulkan1). Restart Forge after fixing the
Vulkan setup, then look for a `[WebGPU]` entry in Settings while conversion is
stopped. Auto-selection checks whether a candidate can warm up a model pipeline.
If the GPU is still unavailable, use another provider or CPU and check
`vcclient.log` for provider registration or device probe errors.
