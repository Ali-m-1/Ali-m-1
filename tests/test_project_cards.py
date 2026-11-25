import base64
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET

from scripts.generate_project_cards import project_card


NS = {"s": "http://www.w3.org/2000/svg"}


class ProjectCardTests(unittest.TestCase):
    def test_parameters_are_escaped_and_output_is_deterministic(self):
        params = dict(title="Models & <Data>", category="AI & ML", description="Compare models & explain <failures>.")
        svg = project_card(**params)
        root = ET.fromstring(svg)
        self.assertEqual(root.find("s:title", NS).text, params["title"])
        self.assertEqual(project_card(**params), svg)

    def test_embedded_assets_preserve_bytes_and_aspect_ratio(self):
        with tempfile.TemporaryDirectory() as directory:
            image = Path(directory) / "image.svg"
            content = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 40"/>'
            image.write_bytes(content)
            root = ET.fromstring(project_card("Project", "Category", "Description", image=image))
            embedded = root.find(".//s:image", NS)
            self.assertEqual(base64.b64decode(embedded.get("href").split(",", 1)[1]), content)
            self.assertEqual(embedded.get("preserveAspectRatio"), "xMidYMid meet")

    def test_repository_cue_does_not_depend_on_image_availability(self):
        svg = project_card("Project", "Category", "Description", repository_url="https://github.com/owner/repo")
        self.assertIn("Explore project", svg)
        self.assertNotIn("Repository URL pending", svg)

    def test_light_icon_uses_the_same_slot_as_the_dark_icon(self):
        with tempfile.TemporaryDirectory() as directory:
            light = Path(directory) / "logo.svg"
            dark = light.with_stem("logo-dark")
            light.write_text('<svg xmlns="http://www.w3.org/2000/svg" fill="navy"/>', encoding="utf-8")
            dark.write_text('<svg xmlns="http://www.w3.org/2000/svg" fill="white"/>', encoding="utf-8")
            root = ET.fromstring(project_card("Project", "Category", "Description", technologies=[{
                "name": "Logo", "icon": dark,
            }]))
            dark_image, light_image = root.findall(".//s:image", NS)
            self.assertEqual(dark_image.get("class"), "dark-icon")
            self.assertEqual(light_image.get("class"), "light-icon")
            self.assertEqual(light_image.get("display"), "none")
            for attribute in ("x", "y", "width", "height", "preserveAspectRatio"):
                self.assertEqual(dark_image.get(attribute), light_image.get(attribute))
            self.assertEqual(base64.b64decode(light_image.get("href").split(",", 1)[1]), light.read_bytes())

    def test_placeholder_has_no_fabricated_link(self):
        root = ET.fromstring(project_card("Next Project", "Category", "Description"))
        self.assertEqual(root.findall(".//s:a", NS), [])
        self.assertIn("Repository URL pending", " ".join(root.itertext()))
        animations = root.findall(".//s:animate", NS)
        self.assertEqual(len(animations), 3)
        self.assertTrue(all(a.get("dur") == "18s" for a in animations))

    def test_excess_description_and_icons_fail_instead_of_overflowing(self):
        with self.assertRaises(ValueError):
            project_card("Project", "Category", "Long description. " * 30)
        with self.assertRaises(ValueError):
            project_card("Project", "Category", "Description", technologies=[{}] * 6)
