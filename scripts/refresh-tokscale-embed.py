#!/usr/bin/env python3
"""Refresh both profile images; a failed download leaves the previous pair intact."""

from pathlib import Path
import subprocess
import tempfile
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
THEMES = ("light", "dark")


def validate_svg(path):
    data = path.read_bytes()
    root = ET.fromstring(data)
    if root.tag != "{http://www.w3.org/2000/svg}svg":
        raise ValueError(f"Not an SVG: {path}")
    # Reject empty/error responses rather than publishing a broken replacement.
    if len(data) < 1000 or "@ardjo-s" not in " ".join(root.itertext()):
        raise ValueError(f"Incomplete Tokscale card: {path}")
    return data


def refresh(destination=ROOT / "assets" / "tokscale"):
    with tempfile.TemporaryDirectory() as temporary:
        images = {}
        for theme in THEMES:
            path = Path(temporary) / f"{theme}.svg"
            subprocess.run([
                "curl", "--fail", "--silent", "--show-error", "--location",
                "--connect-timeout", "15", "--max-time", "90",
                "--retry", "3", "--retry-all-errors", "--retry-delay", "5",
                "--output", str(path),
                "https://tokscale.ai/api/embed/ardjo-s/svg"
                f"?view=3d&compact=1&theme={theme}",
            ], check=True)
            images[theme] = validate_svg(path)
        destination.mkdir(parents=True, exist_ok=True)
        for theme, data in images.items():
            (destination / f"{theme}.svg").write_bytes(data)
        print("Validated and refreshed both Tokscale cards.")


if __name__ == "__main__":
    refresh()
