import tempfile
import unittest
from pathlib import Path

from scripts.install_extensions import load_profile


class InstallExtensionsTests(unittest.TestCase):
    def test_profile_selects_independent_product_packages(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            profile = Path(directory) / "extensions.toml"
            profile.write_text(
                """
profile_version = 1
[[extensions]]
id = "dymo"
repository = "https://example.invalid/extensions.git"
ref = "dymo-v1.2.3"
host_path = "dymo/host"
frontend_path = "dymo/frontend"
""".strip(),
                encoding="utf-8",
            )

            extension = load_profile(profile)[0]

            self.assertEqual(extension.extension_id, "dymo")
            self.assertEqual(extension.package_path("host"), Path("dymo/host"))
            self.assertEqual(
                extension.package_path("frontend"), Path("dymo/frontend")
            )

    def test_profile_rejects_parent_directory_paths(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            profile = Path(directory) / "extensions.toml"
            profile.write_text(
                """
profile_version = 1
[[extensions]]
id = "unsafe"
repository = "https://example.invalid/extensions.git"
ref = "v1"
host_path = "../host"
frontend_path = "frontend"
""".strip(),
                encoding="utf-8",
            )

            with self.assertRaises(ValueError):
                load_profile(profile)


if __name__ == "__main__":
    unittest.main()
