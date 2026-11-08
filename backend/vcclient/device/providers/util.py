from __future__ import annotations


def parse_vram_string(val: str | None) -> int:
    """Parse human-readable VRAM string like '128 MB' or '8 GB' into bytes."""
    if not val:
        return 0
    parts = val.strip().split()
    if not parts:
        return 0
    try:
        num = float(parts[0])
        unit = parts[1].upper() if len(parts) > 1 else "B"
        multipliers = {
            "B": 1,
            "KB": 1024,
            "MB": 1024 * 1024,
            "GB": 1024 * 1024 * 1024,
            "TB": 1024 * 1024 * 1024 * 1024,
        }
        return int(num * multipliers.get(unit, 1))
    except Exception:
        return 0
