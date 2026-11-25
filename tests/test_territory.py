import unittest
import math
from unittest.mock import Mock, patch

from scripts.fetch_languages import (
    aggregate_language_counts,
    get_user_and_owned_repositories,
    github_request,
    paginate,
)
from scripts.generate_territory import (
    choose_top_languages,
    compact_cubic_path,
    deform_closed_cubic,
    formation_drift,
    adaptive_contour_count,
    count_visible_contours,
    generate_svg,
    generate_unavailable_svg,
    formation_contours,
    format_closed_cubic,
    initial_sites,
    language_palette,
    normalize_percentages,
    polygon_area,
    power_cells,
    radial_gap,
    target_visible_contours,
    MAP,
)


class LanguageAggregationTests(unittest.TestCase):
    @patch("scripts.fetch_languages.github_request")
    def test_owned_repository_discovery_uses_affiliation_without_type(self, github_request):
        owned_page = Mock()
        owned_page.json.return_value = [{"owner": {"login": "owner"}, "name": "repo"}]
        github_request.return_value = owned_page

        repos = paginate(
            Mock(),
            "https://api.github.com/user/repos",
            {"affiliation": "owner"},
        )

        self.assertEqual(repos[0]["name"], "repo")
        _, url, params, operation = github_request.call_args.args
        self.assertEqual(params["affiliation"], "owner")
        self.assertNotIn("type", params)
        self.assertEqual(operation, "Owned repository discovery")

    def test_422_error_reports_operation_and_sanitized_validation(self):
        response = Mock()
        response.status_code = 422
        response.headers = {}
        response.json.return_value = {
            "message": "Validation Failed",
            "errors": [{"resource": "Repository", "field": "name", "code": "invalid"}],
        }
        session = Mock()
        session.get.return_value = response

        with self.assertRaisesRegex(Exception, "Owned repository discovery failed.*HTTP 422"):
            github_request(
                session,
                "https://api.github.com/user/repos",
                {"affiliation": "owner"},
                "Owned repository discovery",
            )

    @patch("scripts.fetch_languages.github_request")
    def test_authenticated_user_and_owned_repository_discovery(self, github_request):
        user_response = Mock()
        user_response.json.return_value = {"login": "owner"}
        first_page = Mock()
        first_page.json.return_value = [
            {"owner": {"login": "owner"}, "name": "repo-one"},
        ]
        github_request.side_effect = [user_response, first_page]

        session = Mock()
        username, repos = get_user_and_owned_repositories(session)
        self.assertEqual(username, "owner")
        self.assertEqual(repos[0]["name"], "repo-one")

    @patch("scripts.fetch_languages.github_request")
    def test_pagination_reads_all_pages(self, github_request):
        first = Mock()
        first.json.return_value = [{"id": index} for index in range(100)]
        second = Mock()
        second.json.return_value = [{"id": 100}]
        github_request.side_effect = [first, second]

        repos = paginate(Mock(), "https://api.github.com/test", {})
        self.assertEqual(len(repos), 101)

    @patch.dict("os.environ", {"LANGUAGE_STATS_TOKEN": "test-token"})
    @patch("scripts.fetch_languages.github_request")
    def test_duplicate_repo_is_counted_once(self, github_request):
        owned = [{
            "owner": {"login": "owner"},
            "name": "shared",
            "fork": False,
            "archived": False,
        }]
        collaborator = [{
            "owner": {"login": "owner"},
            "name": "shared",
            "fork": False,
            "archived": False,
        }]

        class Response:
            def json(self):
                return {"Python": 100, "JavaScript": 50}

        github_request.return_value = Response()
        totals, count = aggregate_language_counts("owner", owned, collaborator, set())
        self.assertEqual(totals, {"Python": 100, "JavaScript": 50})
        self.assertEqual(count, 1)
        github_request.assert_called_once()

    @patch.dict("os.environ", {"LANGUAGE_STATS_TOKEN": "test-token"})
    @patch("scripts.fetch_languages.github_request")
    def test_forks_archived_and_profile_repo_are_excluded(self, github_request):
        repos = [
            {"owner": {"login": "owner"}, "name": "owner", "fork": False, "archived": False},
            {"owner": {"login": "owner"}, "name": "owner.github.io", "fork": False, "archived": False},
            {"owner": {"login": "owner"}, "name": "forked", "fork": True, "archived": False},
            {"owner": {"login": "owner"}, "name": "archived", "fork": False, "archived": True},
            {"owner": {"login": "owner"}, "name": "kept", "fork": False, "archived": False},
        ]

        class Response:
            def json(self):
                return {"Python": 25}

        github_request.return_value = Response()
        totals, count = aggregate_language_counts("owner", repos, [], set())
        self.assertEqual(totals, {"Python": 25})
        self.assertEqual(count, 1)
        github_request.assert_called_once()


class PercentageTests(unittest.TestCase):
    def test_top_eight_and_other(self):
        totals = {f"Language{i}": 100 - i for i in range(12)}
        selected = choose_top_languages(totals)
        self.assertEqual(len(selected), 9)
        self.assertIn("Other", selected)

    def test_normalization_sums_to_100(self):
        entries = normalize_percentages({"Python": 2, "JavaScript": 2, "Go": 1})
        self.assertAlmostEqual(sum(value for _, value in entries), 100.0, places=1)


class GeometryTests(unittest.TestCase):
    def test_initial_sites_are_deterministic_and_separated(self):
        first = initial_sites(9, MAP)
        second = initial_sites(9, MAP)
        self.assertEqual(first, second)
        self.assertEqual(len(first), 9)
        for index, (x, y) in enumerate(first):
            self.assertGreaterEqual(x, MAP[0])
            self.assertLessEqual(x, MAP[2])
            self.assertGreaterEqual(y, MAP[1])
            self.assertLessEqual(y, MAP[3])
            for sx, sy in first[index + 1:]:
                self.assertGreater(math.hypot(x - sx, y - sy), 0.0)

    def test_weighted_power_diagram_area_accuracy(self):
        percentages = [31.0, 19.0, 13.0, 10.0, 8.0, 7.0, 5.0, 4.0, 3.0]
        polygons, _, _ = power_cells(9, [value / 100 for value in percentages])
        total = (MAP[2] - MAP[0]) * (MAP[3] - MAP[1])
        for polygon, target in zip(polygons, [value / 100 for value in percentages]):
            actual = polygon_area(polygon) / total
            self.assertLess(abs(actual - target), 0.01)

    def test_geometry_is_valid(self):
        polygons, _, _ = power_cells(4, [0.4, 0.3, 0.2, 0.1])
        total = (MAP[2] - MAP[0]) * (MAP[3] - MAP[1])
        covered = sum(polygon_area(polygon) for polygon in polygons)
        self.assertAlmostEqual(covered, total, delta=total * 0.01)


class SVGGenerationTests(unittest.TestCase):
    def test_compact_contour_keeps_coordinate_precision(self):
        path = "M 0.0 -0.5 C 1.0 2.3 -1.2 4.0 5.0 6.0 C 7.0 8.0 9.0 10.0 0.0 -0.5 Z"
        self.assertEqual(compact_cubic_path(path), "M0-.5C1 2.3-1.2 4 5 6 7 8 9 10 0-.5Z")

    def test_all_territories_have_path_deformation(self):
        svg = generate_svg([
            ("Python", 40.0),
            ("JavaScript", 25.0),
            ("HTML", 20.0),
            ("Other", 15.0),
        ])
        self.assertGreaterEqual(svg.count('<animate attributeName="d"'), 1)
        self.assertGreaterEqual(svg.count('<animateTransform'), 4)

    def test_deformation_amplitude_decreases_with_ring_radius(self):
        path = "M 0.0 0.0 C 1.0 2.0 3.0 4.0 5.0 6.0 C 7.0 8.0 9.0 10.0 11.0 12.0 Z"
        inner = deform_closed_cubic(path, 1234, 0.8, 0, 11)
        middle = deform_closed_cubic(path, 1234, 0.8, 5, 11)
        outer = deform_closed_cubic(path, 1234, 0.8, 10, 11)
        self.assertNotEqual(inner, middle)
        self.assertNotEqual(middle, outer)
        inner_values = [float(value) for value in inner.replace("M", "").replace("C", "").replace("Z", "").split()]
        middle_values = [float(value) for value in middle.replace("M", "").replace("C", "").replace("Z", "").split()]
        outer_values = [float(value) for value in outer.replace("M", "").replace("C", "").replace("Z", "").split()]
        inner_shift = max(abs(a - b) for a, b in zip(inner_values, middle_values))
        self.assertGreater(inner_shift, 0.0)

    def test_deformed_keyframes_are_deterministic(self):
        path = "M 0.0 0.0 C 1.0 2.0 3.0 4.0 5.0 6.0 C 7.0 8.0 9.0 10.0 11.0 12.0 Z"
        first = deform_closed_cubic(path, 1234, 0.8)
        second = deform_closed_cubic(path, 1234, 0.8)
        self.assertEqual(first, second)
        self.assertTrue(first.startswith("M "))
        self.assertIn(" C ", first)
        self.assertTrue(first.endswith(" Z"))

    def test_all_territories_morph_and_drift_deterministically(self):
        entries = [
            ("Python", 40.0),
            ("JavaScript", 25.0),
            ("HTML", 20.0),
            ("Other", 15.0),
        ]
        svg = generate_svg(entries)
        self.assertGreaterEqual(svg.count('<animate attributeName="d"'), 32)
        self.assertIn('<animateTransform attributeName="transform"', svg)

    def test_formation_drift_is_deterministic_and_bounded(self):
        first = formation_drift("Python", 1)
        second = formation_drift("Python", 1)
        self.assertEqual(first, second)
        duration, dx, dy, phase = first
        self.assertGreaterEqual(duration, 24.0)
        self.assertLessEqual(duration, 30.0)
        self.assertGreaterEqual(abs(dx), 5.0)
        self.assertLessEqual(abs(dx), 8.0)
        self.assertGreaterEqual(abs(dy), 3.0)
        self.assertLessEqual(abs(dy), 5.0)
        self.assertGreaterEqual(phase, 0.0)

    def test_radial_gap_is_inner_middle_outer_progressive(self):
        inner = radial_gap(0, 31, 32.0)
        middle = radial_gap(15, 31, 32.0)
        outer = radial_gap(30, 31, 32.0)
        self.assertAlmostEqual(inner, 32.0)
        self.assertGreater(middle, inner)
        self.assertGreater(outer, middle)
        self.assertAlmostEqual(outer, 57.6)

    def test_exact_target_visible_contour_formula(self):
        cases = [
            (0.362, 26),
            (0.322, 24),
            (0.194, 19),
            (0.109, 14),
            (0.012, 5),
            (0.001, 2),
        ]
        for fraction, expected in cases:
            self.assertEqual(target_visible_contours(fraction), expected)

    def test_adaptive_contour_density_by_polygon_area(self):
        polygons, _, _ = power_cells(
            6,
            [0.362, 0.322, 0.194, 0.109, 0.012, 0.001],
        )
        counts = [adaptive_contour_count(polygon) for polygon in polygons]
        self.assertGreater(counts[0], counts[3])
        self.assertGreater(counts[3], counts[4])
        self.assertGreater(counts[4], counts[5])
        self.assertEqual(counts[0], 26)
        self.assertEqual(counts[1], 24)
        self.assertEqual(counts[5], 2)

    def test_contour_paths_use_closed_cubic_smoothing(self):
        path = format_closed_cubic([(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)])
        self.assertTrue(path.startswith("M "))
        self.assertIn(" C ", path)
        self.assertTrue(path.endswith(" Z"))

    def test_topographic_formations_are_deterministic_and_irregular(self):
        entries = [
            ("Python", 40.0),
            ("JavaScript", 25.0),
            ("HTML", 20.0),
            ("Other", 15.0),
        ]
        polygons, _, _ = power_cells(4, [0.40, 0.25, 0.20, 0.15])
        center, paths, visible, minimum_spacing, average_spacing = formation_contours(polygons[0], "Python", 0, 4)
        center_again, paths_again, visible_again, minimum_spacing_again, average_spacing_again = formation_contours(polygons[0], "Python", 0, 4)
        self.assertEqual(center, center_again)
        self.assertEqual(paths, paths_again)
        self.assertEqual(visible, visible_again)
        self.assertEqual(minimum_spacing, minimum_spacing_again)
        self.assertEqual(average_spacing, average_spacing_again)
        self.assertGreaterEqual(len(paths), 10)
        self.assertLessEqual(len(paths), 32)

    def test_premium_palette_and_fallback_are_valid(self):
        self.assertEqual(
            language_palette("Python"),
            ("#205258", "#003A40", "#03333A"),
        )
        fallback = language_palette("Elixir")
        self.assertEqual(len(fallback), 3)
        for color in fallback:
            self.assertRegex(color, r"^#[0-9A-F]{6}$")

    def test_generated_svg_has_real_geometry_and_accessible_labels(self):
        svg = generate_svg([
            ("Python", 40.0),
            ("JavaScript", 25.0),
            ("HTML", 20.0),
            ("Other", 15.0),
        ])
        self.assertIn('viewBox="0 0 1200 405"', svg)
        self.assertIn("<title id=", svg)
        self.assertIn("<desc id=", svg)
        self.assertIn("Language Landscape", svg)
        self.assertIn(">Code volume</text>", svg)
        self.assertIn('#003A40', svg)
        self.assertIn('gradientUnits="objectBoundingBox"', svg)
        self.assertIn('x1="0%" y1="0%" x2="100%" y2="100%"', svg)
        self.assertIn('fill="url(#language-gradient-', svg)
        self.assertIn('clip-path="url(#language-gradient-', svg)
        self.assertIn('stop-color="#FFFFFF" stop-opacity="0.16"', svg)
        self.assertIn('<g id="formation-', svg)
        self.assertIn('stroke="#F1F5F9"', svg)
        self.assertIn('stroke-width="1.4"', svg)
        for share in ("40.0%", "25.0%", "20.0%", "15.0%"):
            self.assertEqual(svg.count(f">{share}</text>"), 1)
        self.assertIn('fill="#0F1B26" stroke="#2B4C62"', svg)
        self.assertIn("Updated weekly", svg)
        self.assertIn('x="44" y="116" width="790" height="296" rx="10"', svg)
        self.assertIn('x="907"', svg)
        self.assertIn('x="1168"', svg)
        self.assertIn('fill="#F1F5F9" stroke="#101720" stroke-opacity="0.75"', svg)
        self.assertIn('font-size="11" fill="#94A3B8" letter-spacing="1.8">LANGUAGE</text>', svg)
        self.assertIn('font-size="17" font-weight="600" fill="#CBD5E1">Python</text>', svg)
        self.assertIn('font-size="17" font-weight="600" fill="#F1F5F9">40.0%</text>', svg)
        self.assertNotIn("<circle", svg)
        self.assertNotIn('<path d=""', svg)

    def test_unavailable_svg_is_safe_status_output(self):
        svg = generate_unavailable_svg()
        self.assertIn("Data unavailable", svg)
        self.assertIn('viewBox="0 0 1200 405"', svg)


if __name__ == "__main__":
    unittest.main()
