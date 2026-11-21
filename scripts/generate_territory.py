#!/usr/bin/env python3
"""Generate a weighted power-diagram SVG from aggregated language bytes."""

from __future__ import annotations

import argparse
import colorsys
import hashlib
import json
import math
import random
import re
import xml.sax.saxutils as saxutils
from pathlib import Path
from typing import Iterable


WIDTH = 1200
HEIGHT = 450
MAP = (44.0, 116.0, 834.0, 412.0)
CHART_X = 44.0
CHART_Y = 116.0
CHART_WIDTH = 790.0
CHART_HEIGHT = 296.0
LEGEND_X = 864.0
LEGEND_RIGHT = 1156.0

LANGUAGE_PALETTE = {
    "Jupyter Notebook": ("#F0A573", "#C77945", "#884422"),
    "Python": ("#69C0EA", "#3289BD", "#164F81"),
    "HTML": ("#ED8C7B", "#C95B52", "#8B3037"),
    "CSS": ("#AE91DC", "#795FAD", "#463275"),
    "JavaScript": ("#F0D579", "#D2AE49", "#977128"),
    "Dockerfile": ("#74CBD3", "#4396A1", "#23636F"),
}

LANGUAGE_COLORS = {
    "Python": "#4F78A8",
    "JavaScript": "#C9B84A",
    "TypeScript": "#557FA8",
    "HTML": "#B66A55",
    "CSS": "#685E8A",
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
    "Jupyter Notebook": "#B66F45",
    "Dart": "#4F9A96",
    "Lua": "#59658A",
    "Scala": "#9B5A62",
    "Dockerfile": "#557A86",
    "Vue": "#579B7B",
    "Nix": "#6F78A8",
    "TeX": "#687A55",
    "Solidity": "#966F59",
    "Perl": "#4F8291",
    "Haskell": "#74678A",
    "Django": "#4D7C68",
}


def mix_hex(color: str, target: str, ratio: float) -> str:
    source = [int(color[index:index + 2], 16) for index in (1, 3, 5)]
    destination = [int(target[index:index + 2], 16) for index in (1, 3, 5)]
    mixed = [
        round(source[channel] + (destination[channel] - source[channel]) * ratio)
        for channel in range(3)
    ]
    return "#" + "".join(f"{channel:02X}" for channel in mixed)


def language_palette(name: str) -> tuple[str, str, str]:
    if name in LANGUAGE_PALETTE:
        return LANGUAGE_PALETTE[name]
    if name == "Other":
        return ("#9CB0C4", "#64748B", "#3E4C5C")

    base = LANGUAGE_COLORS.get(name)
    if base is None:
        digest = hashlib.sha256(name.encode("utf-8")).digest()
        hue = digest[0] / 255.0
        saturation = 0.42 + (digest[1] / 255.0) * 0.18
        highlight_rgb = colorsys.hls_to_rgb(hue, 0.68, saturation)
        base_rgb = colorsys.hls_to_rgb(hue, 0.50, saturation)
        shadow_rgb = colorsys.hls_to_rgb(hue, 0.34, saturation)
        base = "#" + "".join(f"{round(channel * 255):02X}" for channel in base_rgb)
        highlight = "#" + "".join(f"{round(channel * 255):02X}" for channel in highlight_rgb)
        shadow = "#" + "".join(f"{round(channel * 255):02X}" for channel in shadow_rgb)
        return (highlight, base, shadow)

    highlight = mix_hex(base, "#FFFFFF", 0.46)
    shadow = mix_hex(base, "#101720", 0.46)
    return (highlight, base, shadow)


def gradient_id(name: str) -> str:
    suffix = hashlib.sha256(name.encode("utf-8")).hexdigest()[:10]
    return f"language-gradient-{suffix}"


def formation_drift(name: str, rank: int) -> tuple[float, float, float, float]:
    digest = hashlib.sha256(name.encode("utf-8")).digest()
    duration = 24.0 + (digest[rank % len(digest)] % 7)
    dx = 5.0 + (digest[(rank + 1) % len(digest)] % 4)
    dy = 3.0 + (digest[(rank + 2) % len(digest)] % 3)
    if digest[(rank + 3) % len(digest)] % 2:
        dx = -dx
    if digest[(rank + 4) % len(digest)] % 2:
        dy = -dy
    phase = (digest[(rank + 5) % len(digest)] % 100) / 100.0 * duration
    return (duration, dx, dy, phase)


def formation_deformation(name: str, rank: int) -> tuple[float, float]:
    digest = hashlib.sha256(name.encode("utf-8")).digest()
    return (32.0, (digest[(rank + 7) % len(digest)] % 100) / 100.0 * 32.0)


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
    sites = initial_sites(count, MAP)

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


def smooth_circular_radials(radials: list[float]) -> list[float]:
    if len(radials) < 3:
        return radials[:]
    count = len(radials)
    smoothed = [
        0.25 * radials[index - 1]
        + 0.50 * radials[index]
        + 0.25 * radials[(index + 1) % count]
        for index in range(count)
    ]
    return [
        0.20 * smoothed[index - 1]
        + 0.60 * smoothed[index]
        + 0.20 * smoothed[(index + 1) % count]
        for index in range(count)
    ]


def format_closed_cubic(points: list[tuple[float, float]]) -> str:
    if len(points) < 3:
        return ""
    count = len(points)
    segments: list[str] = [f"M {points[0][0]:.1f} {points[0][1]:.1f}"]
    for index in range(count):
        point_0 = points[index - 1]
        point_1 = points[index]
        point_2 = points[(index + 1) % count]
        point_3 = points[(index + 2) % count]
        control_1 = (
            point_1[0] + (point_2[0] - point_0[0]) / 6.0,
            point_1[1] + (point_2[1] - point_0[1]) / 6.0,
        )
        control_2 = (
            point_2[0] - (point_3[0] - point_1[0]) / 6.0,
            point_2[1] - (point_3[1] - point_1[1]) / 6.0,
        )
        segments.append(
            f"C {control_1[0]:.1f} {control_1[1]:.1f} "
            f"{control_2[0]:.1f} {control_2[1]:.1f} "
            f"{point_2[0]:.1f} {point_2[1]:.1f}"
        )
    return " ".join(segments) + " Z"


def deform_closed_cubic(
    path: str,
    seed: int,
    phase: float,
    ring_index: int = 0,
    ring_count: int = 1,
) -> str:
    rng = random.Random(seed)
    field_phase = rng.uniform(0.0, math.tau) + phase
    t = ring_index / max(1, ring_count - 1)
    amplitude = 2.5 + 3.5 * (1.0 - t) ** 1.2
    deformed: list[str] = []
    coordinate_index = 0
    tokens = path.replace("C", " C ").replace("M", " M ").replace("Z", " Z ").split()
    for token in tokens:
        if token in ("M", "C", "Z"):
            deformed.append(token)
            continue
        value = float(token)
        spatial_phase = coordinate_index * 0.055 + field_phase
        field = math.sin(spatial_phase)
        field += 0.35 * math.sin(spatial_phase * 2.0 - 0.7)
        field /= 1.35
        if coordinate_index % 2 == 0:
            displacement = amplitude * field
        else:
            displacement = amplitude * math.sin(spatial_phase - 0.35) * 0.82
        deformed.append(f"{value + displacement:.1f}")
        coordinate_index += 1
    return " ".join(deformed)

def initial_sites(count: int, bounds: tuple[float, float, float, float]) -> list[tuple[float, float]]:
    if count < 1:
        return []

    left, top, right, bottom = bounds
    width = right - left
    height = bottom - top
    rng = random.Random(20261121)

    if count == 6:
        anchors = [
            (0.22, 0.32),
            (0.55, 0.60),
            (0.84, 0.24),
            (0.17, 0.84),
            (0.73, 0.88),
            (0.95, 0.70),
        ]
    elif count == 1:
        anchors = [(0.50, 0.50)]
    elif count == 2:
        anchors = [(0.28, 0.42), (0.72, 0.58)]
    elif count == 3:
        anchors = [(0.18, 0.68), (0.52, 0.30), (0.86, 0.76)]
    elif count == 4:
        anchors = [(0.20, 0.26), (0.68, 0.20), (0.34, 0.78), (0.82, 0.82)]
    elif count == 5:
        anchors = [(0.16, 0.22), (0.48, 0.18), (0.82, 0.34), (0.28, 0.78), (0.72, 0.82)]
    elif count == 7:
        anchors = [
            (0.22, 0.32), (0.55, 0.60), (0.84, 0.24),
            (0.17, 0.84), (0.73, 0.88), (0.95, 0.70),
            (0.08, 0.54),
        ]
    elif count == 8:
        anchors = [
            (0.22, 0.32), (0.55, 0.60), (0.84, 0.24),
            (0.17, 0.84), (0.73, 0.88), (0.95, 0.70),
            (0.08, 0.54), (0.52, 0.08),
        ]
    else:
        anchors = [
            (0.22, 0.32), (0.55, 0.60), (0.84, 0.24),
            (0.17, 0.84), (0.73, 0.88), (0.95, 0.70),
            (0.08, 0.54), (0.52, 0.08), (0.90, 0.94),
        ]

    selected = anchors[:count]
    minimum_separation = min(width, height) * 0.035
    sites: list[tuple[float, float]] = []
    for index, (anchor_x, anchor_y) in enumerate(selected):
        jitter_x = 0.03
        jitter_y = 0.03
        candidate: tuple[float, float] | None = None
        for _ in range(50):
            nx = anchor_x + rng.uniform(-jitter_x, jitter_x)
            ny = anchor_y + rng.uniform(-jitter_y, jitter_y)
            nx = min(0.98, max(0.02, nx))
            ny = min(0.98, max(0.02, ny))
            x = left + nx * width
            y = top + ny * height
            if all(math.hypot(x - sx, y - sy) >= minimum_separation for sx, sy in sites):
                candidate = (x, y)
                break
        if candidate is None:
            candidate = (
                left + min(0.98, max(0.02, anchor_x)) * width,
                top + min(0.98, max(0.02, anchor_y)) * height,
            )
        sites.append(candidate)

    return sites


def text_contrast(color: str) -> str:
    red = int(color[1:3], 16)
    green = int(color[3:5], 16)
    blue = int(color[5:7], 16)
    luminance = (0.299 * red + 0.587 * green + 0.114 * blue) / 255.0
    return "#101720" if luminance > 0.62 else "#F1F5F9"


def polygon_bounds(polygon: list[tuple[float, float]]) -> tuple[float, float, float, float]:
    xs = [point[0] for point in polygon]
    ys = [point[1] for point in polygon]
    return (min(xs), min(ys), max(xs), max(ys))


def adaptive_contour_count(polygon: list[tuple[float, float]]) -> int:
    if len(polygon) < 3:
        return 0
    area = polygon_area(polygon)
    map_area = (MAP[2] - MAP[0]) * (MAP[3] - MAP[1])
    fraction = area / map_area
    return target_visible_contours(fraction)


def target_visible_contours(area_fraction: float) -> int:
    return max(1, min(28, math.ceil(42 * math.sqrt(area_fraction))))


def point_in_polygon(point: tuple[float, float], polygon: list[tuple[float, float]]) -> bool:
    x, y = point
    inside = False
    for index, vertex in enumerate(polygon):
        next_vertex = polygon[(index + 1) % len(polygon)]
        x1, y1 = vertex
        x2, y2 = next_vertex
        if (y1 > y) != (y2 > y):
            crossing_x = x1 + (y - y1) * (x2 - x1) / (y2 - y1)
            if x < crossing_x:
                inside = not inside
    return inside


def segment_polygon_visible_length(
    start: tuple[float, float],
    end: tuple[float, float],
    polygon: list[tuple[float, float]],
) -> float:
    parameters = [0.0, 1.0]
    x1, y1 = start
    x2, y2 = end
    dx = x2 - x1
    dy = y2 - y1
    for index, vertex in enumerate(polygon):
        next_vertex = polygon[(index + 1) % len(polygon)]
        sx, sy = vertex
        tx, ty = next_vertex
        sdx = tx - sx
        sdy = ty - sy
        cross = dx * sdy - dy * sdx
        if abs(cross) < 1e-12:
            continue
        rx = sx - x1
        ry = sy - y1
        segment_t = (rx * sdy - ry * sdx) / cross
        if -1e-9 <= segment_t <= 1.0 + 1e-9:
            if 0.0 <= ((rx * dy - ry * dx) / cross) <= 1.0 + 1e-9:
                parameters.append(max(0.0, min(1.0, segment_t)))
    parameters.sort()
    visible_length = 0.0
    length = math.hypot(dx, dy)
    for first, second in zip(parameters, parameters[1:]):
        if second - first < 1e-9:
            continue
        midpoint_t = (first + second) / 2.0
        midpoint = (x1 + dx * midpoint_t, y1 + dy * midpoint_t)
        if point_in_polygon(midpoint, polygon):
            visible_length += (second - first) * length
    return visible_length


def visible_contour_arcs(
    polygon: list[tuple[float, float]],
    contour_points: list[list[tuple[float, float]]],
) -> int:
    if len(polygon) < 3:
        return 0
    arc_count = 0
    for points in contour_points:
        visible_segments = 0
        visible_length = 0.0
        for index, start in enumerate(points):
            end = points[(index + 1) % len(points)]
            segment_length = segment_polygon_visible_length(start, end, polygon)
            if segment_length >= 6.0:
                visible_segments += 1
                visible_length += segment_length
        if visible_segments >= 2 and visible_length >= 12.0:
            arc_count += 1
    return arc_count


def count_visible_contours(contours, polygon: list[tuple[float, float]]) -> int:
    if not contours or len(polygon) < 3:
        return 0
    if isinstance(contours[0], str):
        sampled: list[list[tuple[float, float]]] = []
        for path in contours:
            numbers = [float(value) for value in re.findall(r"[-+]?(?:\d*\.\d+|\d+\.?\d*)(?:[eE][-+]?\d+)?", path)]
            points = [
                (numbers[index], numbers[index + 1])
                for index in range(0, len(numbers) - 1, 2)
                if index + 1 < len(numbers)
            ]
            if len(points) >= 3:
                sampled.append(points)
        return visible_contour_arcs(polygon, sampled)
    return visible_contour_arcs(polygon, contours)


def generate_contours_for_target(polygon, formation, target):
    if len(polygon) < 3:
        return []
    center_x, center_y = formation
    ring_count = 32
    left, top, right, bottom = polygon_bounds(polygon)
    map_height = MAP[3] - MAP[1]
    outer_radius = map_height * 0.77
    inner_radius = map_height * 0.065
    generated: list[list[tuple[float, float]]] = []
    radii = progressive_radial_radii(
        (center_x, center_y),
        polygon,
        inner_radius,
        outer_radius,
        1.0,
        1.0,
        ring_count,
    )
    for radius in radii:
        radial_values = [1.0] * 128
        radial_values = smooth_circular_radials(radial_values)
        points = []
        for step, radial in enumerate(radial_values):
            angle = math.tau * step / 128.0
            local_radius = radius * radial
            points.append((
                center_x + math.cos(angle) * local_radius,
                center_y + math.sin(angle) * local_radius,
            ))
        generated.append(points)
    visible = count_visible_contours(generated, polygon)
    if visible >= target:
        return generated
    return generated


def visible_contour_spacing(
    polygon: list[tuple[float, float]],
    contour_points: list[list[tuple[float, float]]],
) -> tuple[float, float]:
    distances: list[float] = []
    visible_rings = [
        points for points in contour_points
        if visible_contour_arcs(polygon, [points]) > 0
    ]
    for first, second in zip(visible_rings, visible_rings[1:]):
        for index, point in enumerate(first):
            if point_in_polygon(point, polygon) and point_in_polygon(second[index], polygon):
                distances.append(math.hypot(
                    point[0] - second[index][0],
                    point[1] - second[index][1],
                ))
    if not distances:
        return (0.0, 0.0)
    return (min(distances), sum(distances) / len(distances))


def radial_gap(index: int, total_gaps: int, inner_gap: float) -> float:
    if total_gaps <= 1:
        return inner_gap
    t = index / (total_gaps - 1)
    return inner_gap * (1.0 + 0.8 * t ** 1.5)


def progressive_radial_radii(
    center: tuple[float, float],
    polygon: list[tuple[float, float]],
    inner_radius: float,
    outer_radius: float,
    stretch_x: float,
    stretch_y: float,
    ring_count: int,
) -> list[float]:
    inner_gap = 32.0
    total_gaps = max(0, ring_count - 1)
    radii: list[float] = []
    radius = inner_radius
    for i in range(ring_count):
        if i == 0:
            radius = inner_radius
        else:
            gap = radial_gap(i - 1, total_gaps, inner_gap)
            gap *= 1.0 + 0.025 * math.sin((i + 1) * 1.73)
            radius += gap
        radii.append(radius)
    return radii


def formation_contours(
    polygon: list[tuple[float, float]],
    name: str,
    rank: int,
    language_count: int,
) -> tuple[tuple[float, float], list[str], int, float, float]:
    if len(polygon) < 3:
        return ((0.0, 0.0), [], 0, 0.0, 0.0)

    left, top, right, bottom = polygon_bounds(polygon)
    width = right - left
    height = bottom - top
    digest = hashlib.sha256(name.encode("utf-8")).digest()
    seed = int.from_bytes(digest[:4], "big") ^ (rank * 0x9E3779B1)
    rng = random.Random(seed)

    map_width = MAP[2] - MAP[0]
    map_height = MAP[3] - MAP[1]
    center_x = left + width * rng.uniform(0.18, 0.82)
    center_y = top + height * rng.uniform(0.18, 0.82)
    center_x += rng.uniform(-0.32, 0.32) * map_width
    center_y += rng.uniform(-0.34, 0.34) * map_height

    outer_radius = map_height * rng.uniform(0.72, 0.82)
    inner_radius = map_height * rng.uniform(0.055, 0.075)
    target = adaptive_contour_count(polygon)
    rotation = rng.uniform(-math.pi, math.pi)
    stretch_x = rng.uniform(0.88, 1.22)
    stretch_y = rng.uniform(0.82, 1.16)
    shared_phase = rng.uniform(0.0, math.tau)
    shared_phase_2 = rng.uniform(0.0, math.tau)
    harmonic_2 = rng.uniform(2.0, 3.0)
    harmonic_3 = rng.uniform(4.0, 6.0)
    tilt = rng.uniform(-0.20, 0.20)
    local_rng_state = rng.getstate()
    paths: list[str] = []
    sampled_contours: list[list[tuple[float, float]]] = []
    visible_count = 0
    minimum_spacing = 0.0
    average_spacing = 0.0

    rng.setstate(local_rng_state)
    ring_count = 32
    radii = progressive_radial_radii(
        (center_x, center_y),
        polygon,
        inner_radius,
        outer_radius,
        stretch_x,
        stretch_y,
        ring_count,
    )
    for ring, radius in enumerate(radii):
        local_phase = rng.uniform(-0.018, 0.018) * ring
        radial_values: list[float] = []
        for step in range(128):
            angle = math.tau * step / 128.0
            terrain = 0.075 * math.sin(harmonic_2 * angle + shared_phase)
            terrain += 0.035 * math.sin(harmonic_3 * angle + shared_phase_2)
            terrain += 0.020 * math.cos(7.0 * angle + shared_phase + local_phase)
            terrain += 0.012 * math.sin(11.0 * angle + shared_phase_2 - local_phase)
            radial_values.append(1.0 + terrain)
        radial_values = smooth_circular_radials(radial_values)

        points: list[tuple[float, float]] = []
        for step, radial in enumerate(radial_values):
            angle = math.tau * step / 128.0
            local_radius = radius * radial
            rotated_x = math.cos(angle + rotation) * local_radius
            rotated_y = math.sin(angle + rotation) * local_radius
            dx = rotated_x * stretch_x + rotated_y * tilt
            dy = rotated_y * stretch_y - rotated_x * tilt * 0.28
            points.append((center_x + dx, center_y + dy))
        sampled_contours.append(points)
        paths.append(format_closed_cubic(points))

    visible_count = count_visible_contours(sampled_contours, polygon)
    minimum_spacing, average_spacing = visible_contour_spacing(polygon, sampled_contours)

    return ((center_x, center_y), paths, visible_count, minimum_spacing, average_spacing)


def generate_svg(entries: list[tuple[str, float]], username: str = "") -> str:
    targets = [percentage / 100.0 for _, percentage in entries]
    polygons, _, _ = power_cells(len(entries), targets)
    largest_polygon_index = max(
        range(len(polygons)),
        key=lambda index: polygon_area(polygons[index]),
        default=-1,
    )
    largest_polygon_index = max(
        range(len(polygons)),
        key=lambda index: polygon_area(polygons[index]),
        default=-1,
    )
    map_area = (MAP[2] - MAP[0]) * (MAP[3] - MAP[1])
    lines = [
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 450" width="1200" height="450" '
        'role="img" aria-labelledby="chart-title chart-desc">',
        '<title id="chart-title">Language Landscape</title>',
        '<desc id="chart-desc">Programming language distribution across GitHub repositories, shown as a weighted territory diagram with a ranked legend.</desc>',
        '<rect x="1" y="1" width="1198" height="448" rx="20" fill="#101720" stroke="#294052" stroke-width="1"/>',
        '<text x="44" y="58" font-family="Inter, Segoe UI, Arial, sans-serif" '
        'font-size="26" font-weight="700" letter-spacing="-0.4" fill="#F1F5F9">Language Landscape</text>',
        '<text x="44" y="82" font-family="Inter, Segoe UI, Arial, sans-serif" '
        'font-size="14" font-weight="400" fill="#CBD5E1">Distribution across my GitHub repositories</text>',
        '<g transform="translate(1020 44)" fill="none" stroke="#38BDF8" '
        'stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M14 8A6 6 0 0 0 4 3.53L2 5.33"/>'
        '<polyline points="2 2 2 5.33 5.33 5.33"/>'
        '<path d="M2 8A6 6 0 0 0 12 12.47L14 10.67"/>'
        '<polyline points="14 14 14 10.67 10.67 10.67"/>'
        '</g>',
        '<text x="1156" y="60" text-anchor="end" font-family="Inter, Segoe UI, Arial, sans-serif" '
        'font-size="15" font-weight="500" fill="#CBD5E1">Updated weekly</text>',
        '<text x="1156" y="82" text-anchor="end" font-family="Inter, Segoe UI, Arial, sans-serif" '
        'font-size="13" font-weight="400" fill="#94A3B8">Based on code volume</text>',
    ]

    lines.append('<defs><clipPath id="map-clip"><rect x="44" y="116" width="790" height="296" rx="10"/></clipPath>')
    for name, _ in entries:
        highlight, base, shadow = language_palette(name)
        lines.append(
            f'<linearGradient id="{gradient_id(name)}" gradientUnits="objectBoundingBox" '
            'x1="0%" y1="0%" x2="100%" y2="100%">'
            f'<stop offset="0%" stop-color="{highlight}"/>'
            f'<stop offset="40%" stop-color="{base}"/>'
            f'<stop offset="100%" stop-color="{shadow}"/>'
            '</linearGradient>'
        )
    for (name, _), polygon in zip(entries, polygons):
        area = polygon_area(polygon)
        if len(polygon) >= 3:
            clip_id = f"{gradient_id(name)}-clip"
            path = format_polygon(polygon)
            lines.append(f'<clipPath id="{clip_id}"><path d="{path}"/></clipPath>')
            if area / map_area >= 0.055:
                light_id = f"{gradient_id(name)}-light"
                lines.append(
                    f'<linearGradient id="{light_id}" gradientUnits="objectBoundingBox" '
                    'x1="0%" y1="0%" x2="0%" y2="100%">'
                    '<stop offset="0%" stop-color="#FFFFFF" stop-opacity="0.16"/>'
                    '<stop offset="55%" stop-color="#FFFFFF" stop-opacity="0.0"/>'
                    '<stop offset="100%" stop-color="#FFFFFF" stop-opacity="0.0"/>'
                    '</linearGradient>'
                )
    lines.append('</defs>')
    lines.append('<rect x="44" y="116" width="790" height="296" rx="10" fill="#111B25" stroke="#294052" stroke-width="1"/>')
    lines.append('<g clip-path="url(#map-clip)">')
    for (name, _), polygon in zip(entries, polygons):
        path = format_polygon(polygon)
        if path:
            lines.append(f'<path d="{path}" fill="url(#{gradient_id(name)})"/>')

    for (name, _), polygon in zip(entries, polygons):
        if len(polygon) >= 3:
            area = polygon_area(polygon)
            if area / map_area >= 0.055:
                left, top, right, bottom = polygon_bounds(polygon)
                highlight_height = (bottom - top) * 0.12
                highlight_width = right - left
                clip_id = f"{gradient_id(name)}-clip"
                light_id = f"{gradient_id(name)}-light"
                lines.append(
                    f'<rect x="{left:.1f}" y="{top:.1f}" '
                    f'width="{highlight_width:.1f}" height="{highlight_height:.1f}" '
                    f'fill="url(#{light_id})" clip-path="url(#{clip_id})"/>'
                )

    for rank, ((name, _), polygon) in enumerate(zip(entries, polygons)):
        if len(polygon) >= 3:
            _, contour_paths, _, _, _ = formation_contours(polygon, name, rank, len(entries))
            if contour_paths:
                clip_id = f"{gradient_id(name)}-clip"
                lines.append(
                    f'<g id="formation-{gradient_id(name)}" '
                    f'clip-path="url(#{clip_id})">'
                )
                duration, dx, dy, phase = formation_drift(name, rank)
                lines.append(
                    '<g>'
                    f'<animateTransform attributeName="transform" type="translate" '
                    f'dur="{duration:.1f}s" repeatCount="indefinite" begin="-{phase:.1f}s" '
                    'calcMode="spline" keyTimes="0;0.25;0.5;0.75;1" '
                    'keySplines="0.42 0 0.58 1;0.42 0 0.58 1;0.42 0 0.58 1;0.42 0 0.58 1" '
                    f'values="0 0;{dx:.1f} 0;{dx:.1f} {dy:.1f};0 {dy:.1f};0 0"/>'
                )
                for contour_index, contour_path in enumerate(contour_paths):
                    opacity = 0.42 - 0.12 * (contour_index / max(1, len(contour_paths) - 1))
                    animate = ""
                    if rank == largest_polygon_index:
                        seed = int(hashlib.sha256(name.encode("utf-8")).hexdigest()[:8], 16)
                        deformation_duration, deformation_phase = formation_deformation(name, rank)
                        ring_count = len(contour_paths)
                        variation_a = deform_closed_cubic(
                            contour_path,
                            seed,
                            deformation_phase / 32.0 + 0.8,
                            contour_index,
                            ring_count,
                        )
                        variation_b = deform_closed_cubic(
                            contour_path,
                            seed,
                            deformation_phase / 32.0 + 2.9,
                            contour_index,
                            ring_count,
                        )
                        animate = (
                            f'<animate attributeName="d" dur="{deformation_duration:.1f}s" repeatCount="indefinite" '
                            'calcMode="spline" keyTimes="0;0.33;0.67;1" '
                            'keySplines="0.42 0 0.58 1;0.42 0 0.58 1;0.42 0 0.58 1" '
                            f'values="{saxutils.escape(contour_path)};'
                            f'{saxutils.escape(variation_a)};'
                            f'{saxutils.escape(variation_b)};'
                            f'{saxutils.escape(contour_path)}"/>'
                        )
                    lines.append(
                        f'<path d="{contour_path}" fill="none" '
                        'stroke="#F1F5F9" '
                        f'stroke-width="1.4" stroke-opacity="{opacity:.2f}">'
                        f'{animate}</path>'
                    )
                lines.append('</g></g>')

    for (name, _), polygon in zip(entries, polygons):
        path = format_polygon(polygon)
        if path:
            lines.append(
                f'<path d="{path}" fill="none" stroke="#101720" stroke-width="1.5"/>'
            )

    for (name, percentage), polygon in zip(entries, polygons):
        _, color, _ = language_palette(name)
        ink = text_contrast(color)
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
                    'font-family="JetBrains Mono, Consolas, monospace" '
                    f'font-size="12" font-weight="700" fill="{ink}" paint-order="stroke">'
                    f'{saxutils.escape(name)}</text>'
                )
                lines.append(
                    f'<text x="{cx:.1f}" y="{cy + 16:.1f}" text-anchor="middle" '
                    'font-family="JetBrains Mono, Consolas, monospace" '
                    f'font-size="11" fill="{ink}" opacity="0.82" paint-order="stroke">{percentage:.1f}%</text>'
                )
    lines.append("</g>")

    row_step = 25
    legend_header_y = CHART_Y + CHART_HEIGHT / 2.0 - ((len(entries) - 1) * row_step + 14) / 2.0
    lines.append(f'<text x="{LEGEND_X:.0f}" y="{legend_header_y:.1f}" font-family="JetBrains Mono, Consolas, monospace" '
                 'font-size="11" fill="#94A3B8" letter-spacing="1.8">LANGUAGE</text>')
    lines.append(f'<text x="{LEGEND_RIGHT:.0f}" y="{legend_header_y:.1f}" text-anchor="end" font-family="JetBrains Mono, Consolas, monospace" '
                 'font-size="11" fill="#94A3B8" letter-spacing="1.2">SHARE</text>')
    for index, (name, percentage) in enumerate(entries):
        y = legend_header_y + 25 + index * row_step
        _, color, _ = language_palette(name)
        lines.append(f'<rect x="{LEGEND_X:.0f}" y="{y - 10:.1f}" width="10" height="10" rx="2" fill="{color}"/>')
        lines.append(
            f'<text x="886" y="{y:.1f}" font-family="Inter, Segoe UI, Arial, sans-serif" '
            f'font-size="13" font-weight="600" fill="#CBD5E1">{saxutils.escape(name)}</text>'
        )
        lines.append(
            f'<text x="{LEGEND_RIGHT:.0f}" y="{y:.1f}" text-anchor="end" '
            'font-family="JetBrains Mono, Consolas, monospace" '
            f'font-size="13" fill="#CBD5E1">{percentage:.1f}%</text>'
        )
    lines.append('</svg>')
    return "\n".join(lines) + "\n"


def generate_unavailable_svg() -> str:
    return """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 450" width="1200" height="450" role="img" aria-label="Programming language distribution unavailable">
<title>Language Landscape</title>
<desc>Language distribution data is unavailable. The automated workflow will replace this status graphic after a successful collection.</desc>
<rect x="1" y="1" width="1198" height="448" rx="20" fill="#101720" stroke="#294052" stroke-width="1"/>
<text x="44" y="58" font-family="Inter, Segoe UI, Arial, sans-serif" font-size="26" font-weight="700" letter-spacing="-0.4" fill="#F1F5F9">Language Landscape</text>
<text x="44" y="82" font-family="Inter, Segoe UI, Arial, sans-serif" font-size="14" fill="#CBD5E1">Distribution across my GitHub repositories</text>
<g transform="translate(1024 44)" fill="none" stroke="#38BDF8" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
<path d="M14 8A6 6 0 0 0 4 3.53L2 5.33"/>
<polyline points="2 2 2 5.33 5.33 5.33"/>
<path d="M2 8A6 6 0 0 0 12 12.47L14 10.67"/>
<polyline points="14 14 14 10.67 10.67 10.67"/>
</g>
<text x="1156" y="60" text-anchor="end" font-family="Inter, Segoe UI, Arial, sans-serif" font-size="15" font-weight="500" fill="#CBD5E1">Updated weekly</text>
<text x="1156" y="82" text-anchor="end" font-family="Inter, Segoe UI, Arial, sans-serif" font-size="13" font-weight="400" fill="#94A3B8">Based on code volume</text>
<rect x="44" y="116" width="790" height="296" rx="10" fill="#111B25" stroke="#294052" stroke-width="1"/>
<text x="439" y="252" text-anchor="middle" font-family="JetBrains Mono, Consolas, monospace" font-size="16" fill="#CBD5E1">Data unavailable</text>
<text x="439" y="276" text-anchor="middle" font-family="Inter, Segoe UI, Arial, sans-serif" font-size="12" fill="#94A3B8">Run the workflow successfully to generate this chart.</text>
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
