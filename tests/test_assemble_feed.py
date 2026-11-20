import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from scripts.assemble_feed import assemble_public_release


class AssembleFeedTests(unittest.TestCase):
    def test_publishes_installers_and_evergreen_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            incoming = root / "incoming"
            output = root / "public"
            for component, package_id in (
                ("host", "WeavingComputer.Host"),
                ("frontend", "WeavingComputer.Frontend"),
            ):
                artifact = incoming / component / f"{component}-windows-x86_64"
                artifact.mkdir(parents=True)
                package = artifact / f"{package_id}-26.11.3-full.nupkg"
                package.write_bytes(f"{component}-package".encode())
                feed = {
                    "Assets": [
                        {
                            "PackageId": package_id,
                            "Version": "26.11.3",
                            "Type": "Full",
                            "FileName": package.name,
                            "Size": package.stat().st_size,
                            "SHA256": hashlib.sha256(package.read_bytes()).hexdigest(),
                        }
                    ]
                }
                (artifact / "releases.stable.json").write_text(
                    json.dumps(feed), encoding="utf-8"
                )
                (artifact / f"{package_id}-Setup.exe").write_bytes(
                    f"{component}-setup".encode()
                )

            extensions = root / "extensions.toml"
            extensions.write_text(
                """profile_version = 1

[[extensions]]
id = "dymo"
display_name = "DYMO LabelWriter"
ref = "dymo-v0.1.1"
host_config_path = ["extensions", "dymo", "enabled"]
""",
                encoding="utf-8",
            )
            assemble_public_release(
                incoming,
                output,
                sequence=10,
                extensions_path=extensions,
            )

            manifest = json.loads(
                (output / "installer.stable.json").read_text(encoding="utf-8")
            )
            self.assertEqual(manifest["format"], "wc-split-installer")
            self.assertEqual(manifest["release"]["version"], "26.11.3")
            self.assertEqual(manifest["release"]["sequence"], 10)
            self.assertEqual(manifest["extensions"][0]["id"], "dymo")
            self.assertEqual(
                manifest["extensions"][0]["display_name"], "DYMO LabelWriter"
            )
            self.assertEqual(
                manifest["extensions"][0]["host_config_path"],
                ["extensions", "dymo", "enabled"],
            )
            self.assertEqual(
                manifest["products"]["host"]["installer"]["url"],
                "host/windows-x86_64/WeavingComputer.Host-Setup.exe",
            )
            self.assertEqual(
                manifest["products"]["host"]["main_executable"],
                "Vävdator Server.exe",
            )
            self.assertEqual(
                manifest["products"]["host"]["data_directories"],
                [
                    "WeavingComputer.Host/configurations",
                    "WeavingComputer.Host/database",
                ],
            )
            self.assertEqual(
                manifest["products"]["frontend"]["data_directories"], []
            )
            self.assertTrue(
                (
                    output
                    / manifest["products"]["frontend"]["installer"]["url"]
                ).is_file()
            )

    def test_rejects_mismatched_product_versions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            incoming = root / "incoming"
            for component, package_id, version in (
                ("host", "WeavingComputer.Host", "26.11.3"),
                ("frontend", "WeavingComputer.Frontend", "26.11.4"),
            ):
                artifact = incoming / f"{component}-windows-x86_64"
                artifact.mkdir(parents=True)
                package = artifact / f"{package_id}-{version}-full.nupkg"
                package.write_bytes(b"package")
                (artifact / "releases.stable.json").write_text(
                    json.dumps(
                        {
                            "Assets": [
                                {
                                    "PackageId": package_id,
                                    "Version": version,
                                    "Type": "Full",
                                    "FileName": package.name,
                                    "Size": package.stat().st_size,
                                    "SHA256": hashlib.sha256(
                                        package.read_bytes()
                                    ).hexdigest(),
                                }
                            ]
                        }
                    ),
                    encoding="utf-8",
                )
                (artifact / f"{package_id}-Setup.exe").write_bytes(b"setup")
            extensions = root / "extensions.toml"
            extensions.write_text("extensions = []\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "not coordinated"):
                assemble_public_release(
                    incoming,
                    root / "public",
                    sequence=11,
                    extensions_path=extensions,
                )


if __name__ == "__main__":
    unittest.main()
