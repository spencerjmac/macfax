#!/usr/bin/env python3
"""Export HTML carousel slides as PNG images for social media.

Usage:
    python tools/export_slides.py carousel.html tiktok
    python tools/export_slides.py carousel.html instagram
    python tools/export_slides.py carousel.html tiktok --all

HTML files should include <!-- slides: .your-selector --> so the script
knows which elements are slides without guessing.
"""

import argparse
import asyncio
import re
import sys
from pathlib import Path

from playwright.async_api import async_playwright

FORMATS = {
    "tiktok":    (1080, 1920),
    "instagram": (1080, 1350),
}

FALLBACK_SELECTORS = [
    ".slide",
    "[data-slide]",
    ".carousel-item",
    ".swiper-slide",
    ".slide-item",
    ".carousel > *",
    ".slides > *",
    "#carousel > *",
    "#slides > *",
]


def selector_from_html_comment(html_path: Path) -> str | None:
    text = html_path.read_text(encoding="utf-8")
    m = re.search(r"<!--\s*slides:\s*(\S+)\s*-->", text)
    return m.group(1) if m else None


async def selector_from_dom(page) -> str:
    for sel in FALLBACK_SELECTORS:
        if await page.query_selector_all(sel):
            return sel
    print(
        "error: no slides found. Add <!-- slides: .your-class --> to the HTML file.",
        file=sys.stderr,
    )
    sys.exit(1)


async def export_format(html_path: Path, fmt: str) -> None:
    w, h = FORMATS[fmt]
    out_dir = html_path.parent / f"export-{fmt}"
    out_dir.mkdir(exist_ok=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch()
        ctx = await browser.new_context(viewport={"width": w, "height": h})
        page = await ctx.new_page()
        await page.goto(f"file://{html_path.resolve()}", wait_until="networkidle")

        sel = selector_from_html_comment(html_path) or await selector_from_dom(page)
        slides = await page.query_selector_all(sel)

        if not slides:
            print(
                f"error: selector '{sel}' matched 0 elements.",
                file=sys.stderr,
            )
            sys.exit(1)

        for i, slide in enumerate(slides, 1):
            await slide.evaluate(
                "el => {"
                '  el.style.display = "block";'
                '  el.style.opacity = "1";'
                '  el.style.transform = "none";'
                '  el.style.position = "relative";'
                "}"
            )
            await slide.screenshot(path=str(out_dir / f"slide-{i:02d}.png"))

        await browser.close()

    print(f"{fmt}: {len(slides)} slides → {out_dir}/")


async def run(html_path: Path, fmt: str, all_formats: bool) -> None:
    if all_formats:
        for f in FORMATS:
            await export_format(html_path, f)
    else:
        await export_format(html_path, fmt)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export HTML carousel slides as PNG images for social media."
    )
    parser.add_argument("html_file", help="Path to the HTML carousel file")
    parser.add_argument(
        "format",
        choices=list(FORMATS),
        nargs="?",
        default="instagram",
        help="tiktok=1080×1920, instagram=1080×1350 (ignored with --all)",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Export both tiktok and instagram sizes into separate subfolders",
    )
    args = parser.parse_args()

    html_path = Path(args.html_file).resolve()
    if not html_path.exists():
        print(f"error: file not found: {html_path}", file=sys.stderr)
        sys.exit(1)

    asyncio.run(run(html_path, args.format, args.all))


if __name__ == "__main__":
    main()
