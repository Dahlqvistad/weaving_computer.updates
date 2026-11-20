import tempfile
import unittest
from pathlib import Path

from scripts.verify_frozen_extensions import verify_frozen_extensions


class VerifyFrozenExtensionsTests(unittest.TestCase):
    def test_accepts_selected_extension_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            profile = self._write_profile(root)
            metadata = root / "frozen" / "dymo.dist-info"
            metadata.mkdir(parents=True)
            (metadata / "entry_points.txt").write_text(
                "[wc_split.host_extensions]\ndymo = package:create_extension\n",
                encoding="utf-8",
            )

            verify_frozen_extensions(profile, "host", root / "frozen")

    def test_rejects_missing_selected_extension_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            profile = self._write_profile(root)
            (root / "frozen").mkdir()

            with self.assertRaisesRegex(RuntimeError, "dymo"):
                verify_frozen_extensions(profile, "host", root / "frozen")

    @staticmethod
    def _write_profile(root: Path) -> Path:
        profile = root / "extensions.toml"
        profile.write_text(
            'profile_version = 1\n[[extensions]]\nid = "dymo"\n',
            encoding="utf-8",
        )
        return profile


if __name__ == "__main__":
    unittest.main()
