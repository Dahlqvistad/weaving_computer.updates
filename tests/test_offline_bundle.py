import hashlib
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from scripts import offline_bundle
from scripts.build_offline_windows import deterministic_sequence


class OfflineBundleTests(unittest.TestCase):
    def test_sequence_is_deterministic_from_calendar_version(self) -> None:
        self.assertEqual(deterministic_sequence("26.11.3"), 26_011_003)

    def test_bundle_contains_both_verified_velo_pack_feeds(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            releases = {
                product: self._release_directory(
                    root,
                    product,
                    package_id,
                    f"{product}-full.nupkg",
                )
                for product, package_id in offline_bundle.PRODUCTS.items()
            }
            destination = root / "WC-Split.wcupdate"

            offline_bundle.create_offline_bundle(
                releases,
                destination,
                version="26.11.3",
                sequence=26_011_003,
                extensions=[
                    {
                        "id": "dymo",
                        "ref": "dymo-v0.1.1",
                        "commit": "a" * 40,
                    }
                ],
            )

            with zipfile.ZipFile(destination) as archive:
                manifest = json.loads(archive.read("manifest.json"))
                names = set(archive.namelist())

        self.assertEqual(manifest["release"]["version"], "26.11.3")
        self.assertEqual(manifest["release"]["sequence"], 26_011_003)
        self.assertEqual(manifest["extensions"][0]["id"], "dymo")
        self.assertIn(
            "host/windows-x86_64/releases.stable.json",
            names,
        )
        self.assertIn(
            "frontend/windows-x86_64/frontend-full.nupkg",
            names,
        )

    @staticmethod
    def _release_directory(
        root: Path,
        product: str,
        package_id: str,
        filename: str,
    ) -> Path:
        directory = root / product
        directory.mkdir()
        content = f"{product}-package".encode()
        (directory / filename).write_bytes(content)
        feed = {
            "Assets": [
                {
                    "PackageId": package_id,
                    "Version": "26.11.3",
                    "Type": "Full",
                    "FileName": filename,
                    "SHA256": hashlib.sha256(content).hexdigest(),
                    "Size": len(content),
                }
            ]
        }
        (directory / "releases.stable.json").write_text(
            json.dumps(feed),
            encoding="utf-8",
        )
        return directory


if __name__ == "__main__":
    unittest.main()
