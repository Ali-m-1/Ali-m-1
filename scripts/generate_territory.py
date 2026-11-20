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
MAP = (52.0, 112.0, 840.0, 348.0)
LEGEND_X = 888.0
LEGEND_RIGHT = 1128.0

LANGUAGE_COLORS = {
    "Python": "#397DA6",
    "JavaScript": "#C8A84E",
    "TypeScript": "#557FA8",
    "HTML": "#B8534B",
    "CSS": "#765C9A",
    "Shell": "#78A85A",
    "Java": "#A37A45",
    "C": "#646A73",
    "C++": "#B85F7D",
    "C#": "#568B54",
    "Go": "#4B98A8",
    "Rust": "#B98F78",
    "Ruby": "#934D50",
    "PHP": "#66709A",
    "Swift": "#B86D58",
    "Kotlin": "#8B76A8",
    "R": "#557C9E",
    "MATLAB": "#A86F58",
    "Jupyter Notebook": "#B86B40",
    "Dart": "#4F9A96",
    "Lua": "#59658A",
    "Scala": "#9B5A62",
    "Dockerfile": "#4C8992",
    "Vue": "#579B7B",
    "Nix": "#6F78A8",
    "TeX": "#687A55",
    "Solidity": "#966F59",
    "Perl": "#4F8291",
    "Haskell": "#74678A",
    "Django": "#4D7C68",
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


def adjust_color(color: str, amount: int) -> str:
    values = [
        max(0, min(255, int(color[index:index + 2], 16) + amount))
        for index in (1, 3, 5)
    ]
    return "#" + "".join(f"{value:02X}" for value in values)


def other_language_color(name: str) -> str:
    palette = (
        "#6B8299",
        "#6D8F82",
        "#8A7A9C",
        "#9A7B67",
        "#657E8A",
        "#807D64",
    )
    value = sum((index + 1) * ord(character) for index, character in enumerate(name))
    return palette[value % len(palette)]


def generate_svg(entries: list[tuple[str, float]], username: str = "") -> str:
    targets = [percentage / 100.0 for _, percentage in entries]
    polygons, _, _ = power_cells(len(entries), targets)
    map_area = (MAP[2] - MAP[0]) * (MAP[3] - MAP[1])
    lines = [
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 420" width="1200" height="420" preserveAspectRatio="xMidYMid meet" '
        'role="img" aria-labelledby="chart-title chart-desc">',
        '<title id="chart-title">Language Landscape</title>',
        '<desc id="chart-desc">Programming language distribution across GitHub repositories, shown as a weighted territory diagram with a ranked legend.</desc>',
        '<rect x="1" y="1" width="1198" height="418" rx="20" fill="#101720" stroke="#294052" stroke-width="1"/>',
        '<text x="52" y="58" font-family="Inter, Segoe UI, Arial, sans-serif" '
        'font-size="30" font-weight="700" letter-spacing="-0.6" fill="#F1F5F9">Language Landscape</text>',
        '<text x="52" y="82" font-family="Inter, Segoe UI, Arial, sans-serif" '
        'font-size="15" font-weight="400" fill="#CBD5E1">Languages across my GitHub repositories</text>',
    ]

    gradient_definitions = [
        '<defs>',
        '<clipPath id="map-clip"><rect x="52" y="112" width="788" height="236" rx="10"/></clipPath>',
        '<pattern id="surface-grain" width="12" height="12" patternUnits="userSpaceUse">',
        '<circle cx="2" cy="3" r="0.35" fill="#F1F5F9" opacity="0.10"/>',
        '<circle cx="9" cy="8" r="0.30" fill="#101720" opacity="0.10"/>',
        '</pattern>',
        '<pattern id="contour-lines" width="96" height="72" patternUnits="userSpaceUse">',
        '<path d="M-12 18 C12 5 28 27 48 16 S84 6 108 20" fill="none" stroke="#F1F5F9" stroke-opacity="0.11" stroke-width="0.65"/>',
        '<path d="M-14 36 C10 23 31 43 52 34 S88 24 110 38" fill="none" stroke="#101720" stroke-opacity="0.10" stroke-width="0.65"/>',
        '<path d="M-10 54 C14 41 34 62 55 51 S89 43 108 56" fill="none" stroke="#F1F5F9" stroke-opacity="0.09" stroke-width="0.65"/>',
        '</pattern>',
        '<filter id="label-shadow" x="-15%" y="-15%" width="130%" height="130%">',
        '<feDropShadow dx="0" dy="1" stdDeviation="0.55" flood-color="#101720" flood-opacity="0.72"/>',
        '</filter>',
    ]
    for index, (name, _) in enumerate(entries):
        base = LANGUAGE_COLORS.get(name) if name != "Other" else other_language_color(name)
        if not base:
            base = other_language_color(name)
        gradient_definitions.append(
            f'<linearGradient id="language-gradient-{index}" x1="0" y1="0" x2="1" y2="1">'
            f'<stop offset="0" stop-color="{adjust_color(base, 22)}"/>'
            f'<stop offset="0.58" stop-color="{base}"/>'
            f'<stop offset="1" stop-color="{adjust_color(base, -18)}"/>'
            f'</linearGradient>'
        )
        gradient_definitions.append(
            f'<radialGradient id="language-highlight-{index}" cx="18%" cy="12%" r="82%">'
            f'<stop offset="0" stop-color="#FFFFFF" stop-opacity="0.16"/>'
            f'<stop offset="0.42" stop-color="#FFFFFF" stop-opacity="0.06"/>'
            f'<stop offset="1" stop-color="#FFFFFF" stop-opacity="0"/>'
            f'</radialGradient>'
        )
    gradient_definitions.append('</defs>')
    lines.append("".join(gradient_definitions))
    lines.append('<rect x="52" y="112" width="788" height="236" rx="10" fill="#111B25" stroke="#294052" stroke-width="1"/>')
    lines.append('<g clip-path="url(#map-clip)">')
    for index, ((name, percentage), polygon) in enumerate(zip(entries, polygons)):
        color = LANGUAGE_COLORS.get(name)
        if name == "Other" or not color:
            color = other_language_color(name)
        ink = text_contrast(color)
        path = format_polygon(polygon)
        if path:
            lines.append(
                f'<path d="{path}" fill="url(#language-gradient-{index})" '
                'stroke="#101720" stroke-width="1.0" stroke-linejoin="round"/>'
            )
            lines.append(
                f'<path d="{path}" fill="url(#language-highlight-{index})" '
                'stroke="#E2E8F0" stroke-opacity="0.08" stroke-width="0.45" '
                'stroke-linejoin="round"/>'
            )
            lines.append(
                f'<path d="{path}" fill="url(#contour-lines)" '
                'opacity="0.62" stroke="none"/>'
            )
        if len(polygon) >= 3:
            area = polygon_area(polygon)
            signed_double_area = sum(
                polygon[index][0] * polygon[(index + 1) % len(polygon)][1]
                - polygon[(index + 1) % len(polygon)][0] * polygon[index][1]
                for index in range(len(polygon))
            )
            if abs(signed_double_area) > 1e-9:
                cx = sum(
                    (polygon[index][0] + polygon[(index + 1) % len(polygon)][0])
                    * (polygon[index][0] * polygon[(index + 1) % len(polygon)][1]
                       - polygon[(index + 1) % len(polygon)][0] * polygon[index][1])
                    for index in range(len(polygon))
                ) / (3.0 * signed_double_area)
                cy = sum(
                    (polygon[index][1] + polygon[(index + 1) % len(polygon)][1])
                    * (polygon[index][0] * polygon[(index + 1) % len(polygon)][1]
                       - polygon[(index + 1) % len(polygon)][0] * polygon[index][1])
                    for index in range(len(polygon))
                ) / (3.0 * signed_double_area)
            else:
                cx = sum(point[0] for point in polygon) / len(polygon)
                cy = sum(point[1] for point in polygon) / len(polygon)
            if area / map_area >= 0.055:
                lines.append(
                    f'<text x="{cx:.1f}" y="{cy - 2:.1f}" text-anchor="middle" '
                    'font-family="Inter, Segoe UI, Arial, sans-serif" '
                    f'font-size="13" font-weight="800" fill="{ink}" '
                    'stroke="#101720" stroke-opacity="0.20" stroke-width="0.35" '
                    'paint-order="stroke" filter="url(#label-shadow)">'
                    f'{saxutils.escape(name)}</text>'
                )
                lines.append(
                    f'<text x="{cx:.1f}" y="{cy + 16:.1f}" text-anchor="middle" '
                    'font-family="JetBrains Mono, Consolas, monospace" '
                    f'font-size="12" font-weight="500" fill="{ink}" opacity="0.82" '
                    f'paint-order="stroke" filter="url(#label-shadow)">{percentage:.1f}%</text>'
                )
    lines.append('<rect x="52" y="112" width="788" height="236" rx="10" fill="url(#surface-grain)" opacity="0.22" pointer-events="none"/>')
    lines.append("</g>")

    legend_start = 162 if len(entries) <= 6 else 154
    legend_step = 31 if len(entries) <= 6 else 27
    for index, (name, percentage) in enumerate(entries):
        y = legend_start + index * legend_step
        color = LANGUAGE_COLORS.get(name)
        if name == "Other" or not color:
            color = other_language_color(name)
        lines.append(f'<rect x="{LEGEND_X}" y="{y - 10}" width="12" height="12" rx="3" fill="{color}"/>')
        lines.append(
            f'<text x="{LEGEND_X + 24}" y="{y}" font-family="Inter, Segoe UI, Arial, sans-serif" '
            f'font-size="13" font-weight="600" fill="#CBD5E1">{saxutils.escape(name)}</text>'
        )
        lines.append(
            f'<text x="1148" y="{y}" text-anchor="end" '
            'font-family="JetBrains Mono, Consolas, monospace" '
            f'font-size="13" fill="#CBD5E1">{percentage:.1f}%</text>'
        )
    lines.append('</svg>')
    return "\n".join(lines) + "\n"


def generate_unavailable_svg() -> str:
    return """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 420" width="1200" height="420" preserveAspectRatio="xMidYMid meet" role="img" aria-label="Programming language distribution unavailable">
<title>Language Landscape</title>
<desc>Language distribution data is unavailable. The automated workflow will replace this status graphic after a successful collection.</desc>
<rect x="1" y="1" width="1198" height="418" rx="20" fill="#101720" stroke="#294052" stroke-width="1"/>
<text x="52" y="58" font-family="Inter, Segoe UI, Arial, sans-serif" font-size="30" font-weight="700" letter-spacing="-0.6" fill="#F1F5F9">Language Landscape</text>
<text x="52" y="82" font-family="Inter, Segoe UI, Arial, sans-serif" font-size="15" fill="#CBD5E1">Languages across my GitHub repositories</text>
<rect x="52" y="112" width="1096" height="236" rx="10" fill="#111B25" stroke="#294052" stroke-width="1"/>
<text x="600" y="220" text-anchor="middle" font-family="JetBrains Mono, Consolas, monospace" font-size="16" fill="#CBD5E1">Data unavailable</text>
<text x="600" y="244" text-anchor="middle" font-family="Inter, Segoe UI, Arial, sans-serif" font-size="13" fill="#94A3B8">Run the workflow successfully to generate this chart.</text>
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
