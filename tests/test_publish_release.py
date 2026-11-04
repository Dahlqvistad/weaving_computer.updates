import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import publish_release


class PublishReleaseTests(unittest.TestCase):
    def test_stable_versions_are_strict(self) -> None:
        self.assertEqual(publish_release.normalize_version("v1.2.3"), "1.2.3")
        for invalid in ("1.2", "01.2.3", "1.2.3-beta", "latest"):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                publish_release.normalize_version(invalid)

    def test_project_version_can_be_bumped_safely(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project_file = Path(directory) / "pyproject.toml"
            project_file.write_text(
                '[project]\nname = "example"\nversion = "1.2.3"\n',
                encoding="utf-8",
            )

            changed = publish_release.update_project_version(project_file, "1.2.4")

            self.assertTrue(changed)
            self.assertEqual(publish_release.project_version(project_file), "1.2.4")
            self.assertFalse(
                publish_release.update_project_version(project_file, "1.2.4")
            )

    def test_release_tag_carries_the_coordinated_sequence(self) -> None:
        product = publish_release.Product(
            name="frontend",
            repository="owner/frontend",
            directory=Path("frontend"),
            release_title="Vävdatorn",
        )

        with patch.object(publish_release, "run") as run:
            publish_release.push_release_tag(product, "1.2.3", 14)

        first_call = run.call_args_list[0]
        self.assertEqual(first_call.args[:4], ("git", "tag", "--annotate", "v1.2.3"))
        self.assertIn("sequence: 14", first_call.args[5])

    def test_release_verification_requires_title_and_all_package_types(self) -> None:
        product = publish_release.Product(
            name="frontend",
            repository="owner/frontend",
            directory=Path("frontend"),
            release_title="Vävdatorn",
        )
        payload = {
            "tagName": "v1.2.3",
            "name": "Vävdatorn v1.2.3",
            "assets": [
                {"name": "Frontend-Setup.exe"},
                {"name": "Frontend-Portable.zip"},
                {"name": "Frontend-1.2.3-full.nupkg"},
            ],
        }
        with patch.object(publish_release, "output", return_value=json.dumps(payload)):
            publish_release.verify_release(product, "1.2.3")

        payload["assets"].pop()
        with (
            patch.object(publish_release, "output", return_value=json.dumps(payload)),
            self.assertRaises(RuntimeError),
        ):
            publish_release.verify_release(product, "1.2.3")


if __name__ == "__main__":
    unittest.main()
