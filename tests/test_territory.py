import unittest
from unittest.mock import Mock, patch

from scripts.fetch_languages import (
    aggregate_language_counts,
    get_user_and_owned_repositories,
    github_request,
    paginate,
)
from scripts.generate_territory import (
    choose_top_languages,
    generate_svg,
    generate_unavailable_svg,
    normalize_percentages,
    polygon_area,
    power_cells,
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
    def test_weighted_power_diagram_area_accuracy(self):
        percentages = [31.0, 19.0, 13.0, 10.0, 8.0, 7.0, 5.0, 4.0, 3.0]
        polygons, _, _ = power_cells(9, [value / 100 for value in percentages])
        total = 700.0 * 264.0
        for polygon, target in zip(polygons, [value / 100 for value in percentages]):
            actual = polygon_area(polygon) / total
            self.assertLess(abs(actual - target), 0.01)

    def test_geometry_is_valid(self):
        polygons, _, _ = power_cells(4, [0.4, 0.3, 0.2, 0.1])
        total = 700.0 * 264.0
        covered = sum(polygon_area(polygon) for polygon in polygons)
        self.assertAlmostEqual(covered, total, delta=total * 0.01)


class SVGGenerationTests(unittest.TestCase):
    def test_generated_svg_has_real_geometry_and_accessible_labels(self):
        svg = generate_svg([
            ("Python", 40.0),
            ("JavaScript", 25.0),
            ("HTML", 20.0),
            ("Other", 15.0),
        ])
        self.assertIn('viewBox="0 0 1200 420"', svg)
        self.assertIn("<title>", svg)
        self.assertIn("<desc>", svg)
        self.assertIn('fill="#3572A5"', svg)
        self.assertIn("40.0%", svg)
        self.assertIn('fill="#101720"', svg)

    def test_unavailable_svg_is_safe_status_output(self):
        svg = generate_unavailable_svg()
        self.assertIn("Data unavailable", svg)
        self.assertIn('viewBox="0 0 1200 420"', svg)


if __name__ == "__main__":
    unittest.main()
