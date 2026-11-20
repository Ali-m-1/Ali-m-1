#!/usr/bin/env python3
"""Generate a weighted power-diagram SVG from aggregated language bytes."""

from __future__ import annotations

import argparse
import json
import math
import xml.sax.saxutils as saxutils
from pathlib import Path
from typing import Iterable


WIDTH = 1200
HEIGHT = 420
MAP = (72.0, 96.0, 772.0, 360.0)
LEGEND_X = 836.0
LEGEND_RIGHT = 1128.0

LANGUAGE_COLORS = {
    "Python": "#3572A5",
    "JavaScript": "#F1E05A",
    "TypeScript": "#3178C6",
    "HTML": "#E34C26",
    "CSS": "#563D7C",
    "Shell": "#89E051",
    "Java": "#B07219",
    "C": "#555555",
    "C++": "#F34B7D",
    "C#": "#178600",
    "Go": "#00ADD8",
    "Rust": "#DEA584",
    "Ruby": "#701516",
    "PHP": "#4F5D95",
    "Swift": "#F05138",
    "Kotlin": "#A97BFF",
    "R": "#198CE7",
    "MATLAB": "#E16737",
    "Jupyter Notebook": "#DA5B0B",
    "Dart": "#00B4AB",
    "Lua": "#000080",
    "Scala": "#C22D40",
    "Dockerfile": "#384D54",
    "Vue": "#41B883",
    "Nix": "#7E7EFF",
    "TeX": "#3D6117",
    "Solidity": "#AA6746",
    "Perl": "#0298C3",
    "Haskell": "#5E5086",
    "Django": "#092E20",
}


def choose_top_languages(totals: dict[str, int], limit: int = 8) -> dict[str, int]:
    if not totals:
        raise ValueError("No language data.")
    ranked = sorted(totals.items(), key=lambda item: (-item[1], item[0]))
    major = dict(ranked[:limit])
    remainder = sum(value for _, value in ranked[limit:])
    if remainder:
        major["Other"] = remainder
    total = sum(major.values())
    if total <= 0:
        raise ValueError("Language totals must be positive.")
    return major


def normalize_percentages(totals: dict[str, int]) -> list[tuple[str, float]]:
    total = sum(totals.values())
    if total <= 0:
        raise ValueError("Language totals must be positive.")
    raw = [(name, value * 1000 / total) for name, value in totals.items()]
    tenths = [int(math.floor(value)) for _, value in raw]
    remainder = 1000 - sum(tenths)
    order = sorted(range(len(raw)), key=lambda index: (-(raw[index][1] - tenths[index]), raw[index][0]))
    for index in order[:remainder]:
        tenths[index] += 1
    ranked = sorted(
        zip(totals.keys(), (value / 10 for value in tenths)),
        key=lambda item: (-item[1], item[0]),
    )
    if abs(sum(value for _, value in ranked) - 100.0) > 0.001:
        raise ValueError("Percentage normalization failed.")
    return ranked


def polygon_area(points: list[tuple[float, float]]) -> float:
    if len(points) < 3:
        return 0.0
    return abs(sum(
        points[index][0] * points[(index + 1) % len(points)][1]
        - points[(index + 1) % len(points)][0] * points[index][1]
        for index in range(len(points))
    )) / 2.0


def clip_polygon(
    polygon: list[tuple[float, float]],
    a: tuple[float, float],
    b: tuple[float, float],
    weight_a: float,
    weight_b: float,
) -> list[tuple[float, float]]:
    nx = 2.0 * (b[0] - a[0])
    ny = 2.0 * (b[1] - a[1])
    c = b[0] * b[0] + b[1] * b[1] - weight_b - (
        a[0] * a[0] + a[1] * a[1] - weight_a
    )
    output: list[tuple[float, float]] = []
    if not polygon:
        return output
    previous = polygon[-1]
    previous_value = nx * previous[0] + ny * previous[1] - c
    for current in polygon:
        current_value = nx * current[0] + ny * current[1] - c
        if current_value <= 1e-9:
            if previous_value > 1e-9:
                denominator = previous_value - current_value
                ratio = previous_value / denominator if abs(denominator) > 1e-12 else 0.0
                output.append((
                    previous[0] + ratio * (current[0] - previous[0]),
                    previous[1] + ratio * (current[1] - previous[1]),
                ))
            output.append(current)
        elif previous_value <= 1e-9:
            denominator = previous_value - current_value
            ratio = previous_value / denominator if abs(denominator) > 1e-12 else 0.0
            output.append((
                previous[0] + ratio * (current[0] - previous[0]),
                previous[1] + ratio * (current[1] - previous[1]),
            ))
        previous = current
        previous_value = current_value
    return output


def power_cells(
    count: int,
    targets: list[float],
) -> tuple[list[list[tuple[float, float]]], list[tuple[float, float]], list[float]]:
    left, top, right, bottom = MAP
    if count == 1:
        sites = [((left + right) / 2.0, (top + bottom) / 2.0)]
    elif count == 2:
        sites = [(left + (right - left) * 0.38, (top + bottom) / 2.0),
                 (left + (right - left) * 0.62, (top + bottom) / 2.0)]
    else:
        columns = math.ceil(math.sqrt(count))
        rows = math.ceil(count / columns)
        sites = []
        for index in range(count):
            column = index % columns
            row = index // columns
            x = left + (right - left) * (column + 0.5) / columns
            y = top + (bottom - bottom + bottom - top) * (row + 0.5) / rows
            sites.append((x, y))

    weights = [0.0] * count
    total_area = (right - left) * (bottom - top)
    for _ in range(800):
        polygons = []
        for i, site in enumerate(sites):
            polygon = [(left, top), (right, top), (right, bottom), (left, bottom)]
            for j, other in enumerate(sites):
                if i != j:
                    polygon = clip_polygon(polygon, site, other, weights[i], weights[j])
                    if not polygon:
                        break
            polygons.append(polygon)

        areas = [polygon_area(polygon) for polygon in polygons]
        fractions = [area / total_area for area in areas]
        error = max(abs(fractions[i] - targets[i]) for i in range(count))
        if error <= 0.002:
            break

        for i in range(count):
            weights[i] += (targets[i] - fractions[i]) * total_area * 0.7
        maximum = max(weights)
        weights = [weight - maximum for weight in weights]

        if _ > 0 and _ % 5 == 0:
            new_sites = []
            for i, polygon in enumerate(polygons):
                area = areas[i]
                if area > 1e-9:
                    centroid_x = sum(
                        (polygon[k][0] + polygon[(k + 1) % len(polygon)][0])
                        * (polygon[k][0] * polygon[(k + 1) % len(polygon)][1]
                           - polygon[(k + 1) % len(polygon)][0] * polygon[k][1])
                        for k in range(len(polygon))
                    ) / (6.0 * area)
                    centroid_y = sum(
                        (polygon[k][1] + polygon[(k + 1) % len(polygon)][1])
                        * (polygon[k][0] * polygon[(k + 1) % len(polygon)][1]
                           - polygon[(k + 1) % len(polygon)][0] * polygon[k][1])
                        for k in range(len(polygon))
                    ) / (6.0 * area)
                    if math.isfinite(centroid_x) and math.isfinite(centroid_y):
                        new_sites.append((
                            min(right, max(left, sites[i][0] + 0.15 * (centroid_x - sites[i][0]))),
                            min(bottom, max(top, sites[i][1] + 0.15 * (centroid_y - sites[i][1]))),
                        ))
                    else:
                        new_sites.append(sites[i])
                else:
                    new_sites.append(sites[i])
            sites = new_sites

    polygons = []
    for i, site in enumerate(sites):
        polygon = [(left, top), (right, top), (right, bottom), (left, bottom)]
        for j, other in enumerate(sites):
            if i != j:
                polygon = clip_polygon(polygon, site, other, weights[i], weights[j])
        polygons.append(polygon)
    final_error = max(
        abs(polygon_area(polygons[i]) / total_area - targets[i])
        for i in range(count)
    )
    if final_error > 0.01:
        raise ValueError("Weighted power diagram area validation failed.")
    return polygons, sites, weights


def format_polygon(points: Iterable[tuple[float, float]]) -> str:
    if not points:
        return ""
    return " ".join(
        ("M " if index == 0 else "L ") + f"{x:.1f} {y:.1f}"
        for index, (x, y) in enumerate(points)
    ) + " Z"


def text_contrast(color: str) -> str:
    red = int(color[1:3], 16)
    green = int(color[3:5], 16)
    blue = int(color[5:7], 16)
    luminance = (0.299 * red + 0.587 * green + 0.114 * blue) / 255.0
    return "#101720" if luminance > 0.62 else "#F1F5F9"


def generate_svg(entries: list[tuple[str, float]], username: str = "") -> str:
    targets = [percentage / 100.0 for _, percentage in entries]
    polygons, sites, _ = power_cells(len(entries), targets)
    lines = [
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 420" width="1200" height="420" '
        'role="img" aria-label="Programming language distribution as a weighted territory chart">',
        '<title>Programming Language Territory</title>',
        '<desc>Programming language byte percentages represented by a weighted power diagram and ranked legend.</desc>',
        '<rect width="1200" height="420" fill="#101720"/>',
        '<text x="72" y="60" font-family="system-ui, -apple-system, \'Segoe UI\', sans-serif" '
        'font-size="25" font-weight="700" fill="#F1F5F9">Territory</text>',
        '<text x="72" y="82" font-family="ui-monospace, Menlo, Consolas, monospace" '
        'font-size="10" fill="#CBD5E1" letter-spacing="4">PROGRAMMING LANGUAGES · AREA = SHARE</text>',
    ]

    lines.append("<g>")
    for index, ((name, percentage), polygon) in enumerate(zip(entries, polygons)):
        color = LANGUAGE_COLORS.get(name, "#64748B")
        if name == "Other":
            color = "#64748B"
        ink = text_contrast(color)
        path = format_polygon(polygon)
        lines.append(
            f'<path d="{path}" fill="{color}" fill-opacity="0.88" '
            'stroke="#101720" stroke-width="2"/>'
        )
        if len(polygon) >= 3:
            area = polygon_area(polygon)
            cx = sum(point[0] for point in polygon) / len(polygon)
            cy = sum(point[1] for point in polygon) / len(polygon)
            if area / ((772.0 - 72.0) * (360.0 - 96.0)) >= 0.055:
                lines.append(
                    f'<text x="{cx:.1f}" y="{cy - 2:.1f}" text-anchor="middle" '
                    'font-family="ui-monospace, Menlo, Consolas, monospace" '
                    f'font-size="12" font-weight="700" fill="{ink}">'
                    f'{saxutils.escape(name)}</text>'
                )
                lines.append(
                    f'<text x="{cx:.1f}" y="{cy + 16:.1f}" text-anchor="middle" '
                    'font-family="ui-monospace, Menlo, Consolas, monospace" '
                    f'font-size="11" fill="{ink}" opacity="0.78">{percentage:.1f}%</text>'
                )
    lines.append("</g>")

    lines.append('<text x="836" y="80" font-family="ui-monospace, Menlo, Consolas, monospace" '
                 'font-size="10" fill="#CBD5E1" letter-spacing="4">BY AREA</text>')
    lines.append('<line x1="836" y1="92" x2="1128" y2="92" stroke="#38BDF8" stroke-opacity="0.25"/>')
    for index, (name, percentage) in enumerate(entries):
        y = 126 + index * 28
        color = LANGUAGE_COLORS.get(name, "#64748B")
        if name == "Other":
            color = "#64748B"
        lines.append(f'<rect x="836" y="{y - 10}" width="12" height="12" rx="2" fill="{color}"/>')
        lines.append(
            f'<text x="860" y="{y}" font-family="ui-monospace, Menlo, Consolas, monospace" '
            f'font-size="12" fill="#CBD5E1">{saxutils.escape(name)}</text>'
        )
        lines.append(
            f'<text x="1128" y="{y}" text-anchor="end" '
            'font-family="ui-monospace, Menlo, Consolas, monospace" '
            f'font-size="12" fill="#94A3B8">{percentage:.1f}%</text>'
        )
    lines.append('<line x1="72" y1="384" x2="1128" y2="384" stroke="#38BDF8" stroke-opacity="0.18"/>')
    lines.append('<text x="72" y="404" font-family="ui-monospace, Menlo, Consolas, monospace" '
                 'font-size="9.5" fill="#94A3B8" letter-spacing="2.5">'
                 'WEIGHTED POWER DIAGRAM · WEIGHTS SOLVED SO AREA MATCHES SHARE</text>')
    lines.append('</svg>')
    return "\n".join(lines) + "\n"


def generate_unavailable_svg() -> str:
    return """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 420" width="1200" height="420" role="img" aria-label="Programming language distribution unavailable">
<title>Programming Language Territory</title>
<desc>Language distribution data is unavailable. The automated workflow will replace this status graphic after a successful collection.</desc>
<rect width="1200" height="420" fill="#101720"/>
<text x="72" y="60" font-family="system-ui, -apple-system, 'Segoe UI', sans-serif" font-size="25" font-weight="700" fill="#F1F5F9">Territory</text>
<text x="72" y="82" font-family="ui-monospace, Menlo, Consolas, monospace" font-size="10" fill="#CBD5E1" letter-spacing="4">LANGUAGE DISTRIBUTION</text>
<rect x="72" y="120" width="1056" height="180" rx="18" fill="#111D29" stroke="#38BDF8" stroke-opacity="0.18"/>
<text x="600" y="205" text-anchor="middle" font-family="ui-monospace, Menlo, Consolas, monospace" font-size="16" fill="#CBD5E1">Data unavailable</text>
<text x="600" y="230" text-anchor="middle" font-family="ui-monospace, Menlo, Consolas, monospace" font-size="11" fill="#94A3B8">Run the workflow successfully to generate this chart.</text>
</svg>
"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--unavailable", action="store_true")
    args = parser.parse_args()

    if args.unavailable:
        svg = generate_unavailable_svg()
    else:
        if args.input is None:
            raise SystemExit("--input is required unless --unavailable is used")
        payload = json.loads(args.input.read_text(encoding="utf-8"))
        totals = payload.get("languages")
        if not isinstance(totals, dict) or not totals:
            raise SystemExit("No valid language totals found.")
        selected = choose_top_languages(totals)
        entries = normalize_percentages(selected)
        svg = generate_svg(entries)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    temporary.write_text(svg, encoding="utf-8")
    temporary.replace(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
