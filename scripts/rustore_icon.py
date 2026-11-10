"""Create identical catalog/launcher artwork from the pinned official Flare logo.

RuStore requires a full-bleed opaque 512x512 catalog icon and a matching icon
inside the APK. Generate both from one source so they cannot drift apart.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image

ICON_SIZES = {"mdpi": 48, "hdpi": 72, "xhdpi": 96, "xxhdpi": 144, "xxxhdpi": 192}
BACKGROUND = (31, 31, 35, 255)


def generate_icons(engine: Path) -> Path:
    engine = Path(engine).resolve()
    source = engine / "distribution/flare_logo_icon.png"
    project = engine / "flare-android-project"
    if not source.is_file():
        raise FileNotFoundError(f"Missing pinned upstream Flare icon: {source}")
    if not (project / "app/build.gradle").is_file():
        raise FileNotFoundError(f"Missing Flare Android project: {project}")

    with Image.open(source) as icon_file:
        icon_file.load()
        if icon_file.width != icon_file.height or icon_file.width < 128:
            raise ValueError(f"Expected a square original Flare icon of at least 128px: {source}")
        icon = icon_file.convert("RGBA")

    icon = icon.resize((512, 512), Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", (512, 512), BACKGROUND)
    canvas.alpha_composite(icon)
    master = canvas.convert("RGB")  # RuStore forbids transparent outer edges.

    output = project / "rustore-icon-512.png"
    master.save(output, "PNG", optimize=True)
    resources = project / "app/src/main/res"
    for density, size in ICON_SIZES.items():
        folder = resources / f"drawable-{density}"
        folder.mkdir(parents=True, exist_ok=True)
        master.resize((size, size), Image.Resampling.LANCZOS).save(
            folder / "ic_launcher.png", "PNG", optimize=True
        )
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine", required=True, type=Path)
    args = parser.parse_args()
    print(generate_icons(args.engine))


if __name__ == "__main__":
    main()
