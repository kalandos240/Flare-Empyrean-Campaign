#!/usr/bin/env python3
"""Conservatively detect whether tapping Play left Flare's title-screen menu.

This is a graphical regression heuristic, *not* OCR or full gameplay validation.
"""
from __future__ import annotations

import argparse

from PIL import Image


def changed_pixels(before: Image.Image, after: Image.Image) -> tuple[int, int]:
    if before.size != after.size:
        raise ValueError("Android emulator screenshots have different dimensions")

    width, height = before.size
    # Main menu button group in the original title screen on the Pixel 5.
    # Use relative positions, as emulator hardware resolution may vary.
    rect = (
        round(width * 0.52),
        round(height * 0.70),
        round(width * 0.70),
        round(height * 0.89),
    )
    old_region = before.convert("RGB").crop(rect)
    new_region = after.convert("RGB").crop(rect)
    pixels_a = old_region.load()
    pixels_b = new_region.load()
    changed = 0
    examined = 0
    for y in range(0, old_region.height, 3):
        for x in range(0, old_region.width, 3):
            a = pixels_a[x, y]
            b = pixels_b[x, y]
            examined += 1
            if max(abs(a[i] - b[i]) for i in range(3)) >= 42:
                changed += 1
    return changed, examined


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("title_screenshot")
    parser.add_argument("after_play_screenshot")
    args = parser.parse_args()
    with Image.open(args.title_screenshot) as before, Image.open(
        args.after_play_screenshot
    ) as after:
        changed, total = changed_pixels(before, after)
    ratio = changed / total
    print(f"Flare title menu area changed on {ratio:.1%} of sampled pixels")
    if ratio < 0.11:
        raise SystemExit(
            "The title menu appears unchanged after an Android touchscreen tap. "
            "Inspect both emulator screenshots to diagnose the UI/input issue."
        )
    print("Flare Play-menu navigation changed the title screen.")


if __name__ == "__main__":
    main()
