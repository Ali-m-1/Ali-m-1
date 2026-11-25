#!/usr/bin/env python3
"""Render self-contained README project cards from config/project_cards.json.

Run: python scripts/generate_project_cards.py
Repository links wrap each card in README.md; no links live inside the SVG.
"""

from __future__ import annotations

import base64
import json
from pathlib import Path
import re
import textwrap
from xml.sax.saxutils import escape


ROOT = Path(__file__).resolve().parents[1]

CARD_THEME = """<style>
@media (prefers-color-scheme: light) {
  #background stop:first-child { stop-color: #F8FAFC; }
  #background stop:last-child { stop-color: #EEF4F7; }
  [stroke="#2B4C62"] { stroke: #CBD9E1; }
  [stroke="#70B8D1"] { stroke: #176378; }
  [fill="#122433"] { fill: #E8EFF3; }
  [fill="#142C3C"] { fill: #EEF4F7; }
  [fill="#F1F5F9"] { fill: #172B3A; }
  [fill="#CBD5E1"], [fill="#94A3B8"], [fill="#A6B3C2"] { fill: #42576A; }
  [fill="#70B8D1"] { fill: #176378; }
  .dark-icon { display: none; }
  .light-icon { display: inline; }
}
</style>"""


def asset_uri(path: Path) -> str:
    mime = {".svg": "image/svg+xml", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}[path.suffix.lower()]
    return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode('ascii')}"


def project_card(
    title: str,
    category: str,
    description: str,
    image: Path | None = None,
    technologies: list[dict] | None = None,
    repository_url: str | None = None,
) -> str:
    """Use one layout for real projects and explicit placeholders."""
    lines = textwrap.wrap(description, width=27, break_long_words=False)
    if len(lines) > 5:
        raise ValueError("Keep the card description short enough for five lines.")
    technologies = technologies or []
    if len(technologies) > 5:
        raise ValueError("Use at most five technology icons.")
    svg = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="640" height="340" viewBox="0 0 640 340" role="img" aria-labelledby="title desc">',
        f'<title id="title">{escape(title)}</title>',
        f'<desc id="desc">{escape(category + ". " + description)}'
        + (" Technologies: " + escape(", ".join(t["name"] for t in technologies)) + "." if technologies else " Placeholder project and visual.")
        + '</desc>',
        CARD_THEME,
        '<defs>',
        '<linearGradient id="background" x2="1" y2="1"><stop stop-color="#0F1B26"/><stop offset="1" stop-color="#142C3C"/></linearGradient>',
        '<clipPath id="card-clip"><rect x="1" y="1" width="638" height="338" rx="22"/></clipPath>',
        '<clipPath id="image-clip"><rect x="32" y="68" width="224" height="156" rx="12"/></clipPath>',
        '</defs>',
        '<rect x="1" y="1" width="638" height="338" rx="22" fill="url(#background)" stroke="#2B4C62"/>',
        '<g clip-path="url(#card-clip)" fill="none" stroke="#70B8D1">',
        '<circle cx="626" cy="28" r="88" stroke-opacity="0.10"/>',
        '<circle cx="626" cy="28" r="62" stroke-opacity="0.07"/>',
        '<circle cx="4" cy="340" r="48" stroke-opacity="0.07"/>',
        '</g>',
        '<g fill="none" stroke="#70B8D1" stroke-width="1.5" stroke-linecap="round">',
    ]
    for length, opacity in [(60, "0.10"), (30, "0.22"), (8, "0.65")]:
        svg.append(
            f'<rect x="1" y="1" width="638" height="338" rx="22" pathLength="1000" stroke-dasharray="{length} {1000-length}" opacity="{opacity}">'
            '<animate attributeName="stroke-dashoffset" values="0;-1000" dur="18s" repeatCount="indefinite"/></rect>'
        )
    svg.append('</g>')
    if image:
        svg.extend([
            '<g clip-path="url(#image-clip)"><rect x="32" y="68" width="224" height="156" fill="#122433"/>',
            f'<image x="38" y="74" width="212" height="144" preserveAspectRatio="xMidYMid meet" href="{asset_uri(image)}"/></g>',
        ])
    else:
        svg.extend([
            '<rect x="32" y="68" width="224" height="156" rx="12" fill="#122433" stroke="#2B4C62"/>',
            '<path d="M126 123h36" stroke="#70B8D1" stroke-opacity="0.55" stroke-width="2" stroke-linecap="round"/>',
            '<text x="144" y="152" text-anchor="middle" font-family="Segoe UI, Arial, sans-serif" font-size="19" fill="#CBD5E1">Project image</text>',
            '<text x="144" y="177" text-anchor="middle" font-family="Segoe UI, Arial, sans-serif" font-size="14" fill="#94A3B8">PLACEHOLDER</text>',
        ])
    if technologies:
        for index, technology in enumerate(technologies):
            icon = ROOT / technology["icon"]
            light_icon = icon.with_stem(icon.stem.removesuffix("-dark"))
            themed = light_icon != icon and light_icon.is_file()
            position = f'x="{32 + index * 43}" y="242" width="28" height="28" preserveAspectRatio="xMidYMid meet"'
            name = escape(technology["name"])
            dark_class = ' class="dark-icon"' if themed else ''
            svg.append(
                f'<image{dark_class} {position} href="{asset_uri(icon)}"><title>{name}</title></image>'
            )
            if themed:
                svg.append(
                    f'<image class="light-icon" display="none" {position} href="{asset_uri(light_icon)}"><title>{name}</title></image>'
                )
    else:
        for x in [32, 75, 118]:
            svg.append(f'<rect x="{x}" y="242" width="28" height="28" rx="7" fill="#142C3C" stroke="#2B4C62"/>')
        svg.append('<text x="32" y="294" font-family="Segoe UI, Arial, sans-serif" font-size="13" fill="#94A3B8">Technology placeholders</text>')
    svg.extend([
        '<rect x="292" y="52" width="32" height="3" rx="1.5" fill="#70B8D1" opacity="0.7"/>',
        f'<text x="292" y="91" font-family="Segoe UI, Arial, sans-serif" font-size="30" font-weight="700" fill="#F1F5F9">{escape(title)}</text>',
        f'<text x="292" y="119" font-family="Segoe UI, Arial, sans-serif" font-size="15" letter-spacing="1" fill="#70B8D1">{escape(category.upper())}</text>',
    ])
    for index, line in enumerate(lines):
        svg.append(f'<text x="292" y="{160 + index * 26}" font-family="Segoe UI, Arial, sans-serif" font-size="20" fill="#A6B3C2">{escape(line)}</text>')
    cue = "Explore project ↗" if repository_url else "Repository URL pending"
    svg.append(f'<text x="292" y="302" font-family="Segoe UI, Arial, sans-serif" font-size="17" fill="#70B8D1">{cue}</text>')
    svg.append('</svg>')
    return "\n".join(svg) + "\n"


def main() -> None:
    projects = json.loads((ROOT / "config/project_cards.json").read_text(encoding="utf-8"))
    for project in projects:
        slug = project["slug"]
        if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", slug):
            raise ValueError("Project slugs must contain lowercase letters, digits, and hyphens.")
        svg = project_card(
            title=project["title"], category=project["category"], description=project["description"],
            image=ROOT / project["image"] if project.get("image") else None,
            technologies=project.get("technologies"),
            repository_url=project.get("repository_url"),
        )
        (ROOT / "assets/projects" / f"{slug}.svg").write_text(svg, encoding="utf-8")


if __name__ == "__main__":
    main()
