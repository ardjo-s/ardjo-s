"""Regression check: an upstream failure must never replace last-good cards."""
import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location(
    "refresh", Path(__file__).with_name("refresh-tokscale-embed.py")
)
refresh = importlib.util.module_from_spec(spec)
spec.loader.exec_module(refresh)
SVG = b'<svg xmlns="http://www.w3.org/2000/svg"><text>@ardjo-s</text><!--' + b'x' * 1000 + b'--></svg>'


class RefreshTest(unittest.TestCase):
    def test_publish_only_after_both_cards_validate(self):
        for failure in ("network", "html", "empty", None):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as directory:
                destination = Path(directory)
                for theme in refresh.THEMES:
                    (destination / f"{theme}.svg").write_bytes(b"previous")

                def download(args, **kwargs):
                    dark = args[-1].endswith("dark")
                    if dark and failure == "network":
                        raise subprocess.CalledProcessError(22, args)
                    data = SVG
                    if dark and failure == "html":
                        data = b"<html>Service unavailable</html>"
                    if dark and failure == "empty":
                        data = b'<svg xmlns="http://www.w3.org/2000/svg"/>'
                    Path(args[args.index("--output") + 1]).write_bytes(data)

                with patch.object(refresh.subprocess, "run", side_effect=download):
                    if failure:
                        with self.assertRaises((ValueError, subprocess.CalledProcessError)):
                            refresh.refresh(destination)
                    else:
                        refresh.refresh(destination)
                for theme in refresh.THEMES:
                    self.assertEqual((destination / f"{theme}.svg").read_bytes(),
                                     b"previous" if failure else SVG)


if __name__ == "__main__":
    unittest.main()
