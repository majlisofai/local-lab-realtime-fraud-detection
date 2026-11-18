"""Brand themes for the draw.io generators (brand/<name>/brand.json).

Both generators take the same options:

    --brand aurora|majlisofai   (default: $BRAND or majlisofai)
    --out DIR                   (default: the folder the README uses)
"""

import argparse
import json
import os
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[2]
BRANDS = sorted(p.name for p in (ROOT / "brand").iterdir() if (p / "brand.json").exists())


def _ns(value):
    if isinstance(value, dict):
        return SimpleNamespace(**{k: _ns(v) for k, v in value.items()})
    return value


def cli(default_out: Path):
    parser = argparse.ArgumentParser()
    parser.add_argument("--brand", default=os.environ.get("BRAND", "majlisofai"), choices=BRANDS)
    parser.add_argument("--out", type=Path, default=default_out)
    args = parser.parse_args()
    theme = _ns(json.loads((ROOT / "brand" / args.brand / "brand.json").read_text())["diagram"])
    theme.brand = args.brand
    args.out.mkdir(parents=True, exist_ok=True)
    return theme, args.out


def font(theme) -> str:
    """draw.io font declaration (the exporter loads it from Google Fonts)."""
    return f"fontFamily={theme.font};fontSource={quote(theme.font_url, safe='')};"


def rounded(theme) -> str:
    r = theme.node.radius
    return f"rounded=1;absoluteArcSize=1;arcSize={r * 2};" if r else "rounded=0;"
