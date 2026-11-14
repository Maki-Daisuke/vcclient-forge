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
