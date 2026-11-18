"""Download the brand fonts (OFL, Google Fonts) as TTF into build/fonts/<brand>/.

The headless draw.io exporter cannot load web fonts, so `make diagrams` / `make docs`
mount this folder into the container as system fonts.

    uv run --no-project python scripts/fetch_fonts.py
"""

import json
import re
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UA = {"User-Agent": "curl/8"}  # a non-browser agent gets TTF instead of WOFF2


def get(url: str) -> bytes:
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
        return r.read()


for brand_json in sorted((ROOT / "brand").glob("*/brand.json")):
    out = ROOT / "build" / "fonts" / brand_json.parent.name
    if out.exists() and any(out.glob("*.ttf")):
        continue
    out.mkdir(parents=True, exist_ok=True)
    css = get(json.loads(brand_json.read_text())["fonts_css"]).decode()
    for family, weight, url in re.findall(
            r"font-family: '([^']+)';.*?font-weight: (\d+);.*?src: url\((https://[^)]+\.ttf)\)", css, re.S):
        target = out / f"{family.replace(' ', '')}-{weight}.ttf"
        target.write_bytes(get(url))
        print(f"  {target.relative_to(ROOT)}")
