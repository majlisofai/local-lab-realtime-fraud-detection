"""Build the lab docs as a branded static HTML site: site/<brand>/.

    uv run --no-project --with markdown==3.7 python scripts/build_docs.py --brand majlisofai --images build/majlisofai
    make docs BRAND=majlisofai|aurora

Pages: README.md -> index.html, docs/01-architecture.md -> architecture.html, docs/02-workflow.md -> workflow.html.
Diagram PNGs come from --images (rendered in the same brand); Mermaid blocks get the brand's theme.
"""

import argparse
import json
import re
import shutil
from html import escape
from pathlib import Path

import markdown

ROOT = Path(__file__).resolve().parents[1]
PAGES = [("README.md", "index.html", "Guide"),
         ("docs/01-architecture.md", "architecture.html", "Architecture"),
         ("docs/02-workflow.md", "workflow.html", "Workflow")]
MERMAID_JS = "https://cdn.jsdelivr.net/npm/mermaid@11.4.1/dist/mermaid.min.js"
EMOJI = re.compile("[\U0001F300-\U0001FAFF☀-⛿✀-✒✙-➿⭐️]")


def rewrite(md: str, brand: str) -> str:
    """Point links and images at the site layout."""
    for src, page, _ in PAGES:
        md = md.replace(f"]({src})", f"]({page})").replace(f"]({Path(src).name})", f"]({page})")
    md = re.sub(r"\]\((?:\.\./)?(?:docs/)?(?:images|diagrams)/([^)]+\.png)\)", r"](images/\1)", md)
    md = re.sub(r"\]\((?:docs/)?diagrams/([^)]+\.drawio)\)", r"](images/\1)", md)
    md = re.sub(r"brand/[a-z]+/banner\.svg", "assets/banner.svg", md)
    return md


def render(md: str, theme: dict) -> tuple[str, str, str]:
    # Mermaid: keep the source out of the Markdown parser, drop any init block (the brand sets the theme)
    blocks: list[str] = []

    def stash(m: re.Match) -> str:
        body = re.sub(r"%%\{init:.*?\}%%\s*", "", m.group(1), flags=re.S)
        blocks.append(f'<pre class="mermaid">{escape(body)}</pre>')
        return f"\n\nMERMAIDBLOCK{len(blocks) - 1}\n\n"

    md = re.sub(r"```mermaid\n(.*?)```", stash, md, flags=re.S)
    if theme["strip_emoji"]:
        md = re.sub(EMOJI.pattern + r"+[ \t]?", "", md)
    conv = markdown.Markdown(extensions=["tables", "fenced_code", "toc", "attr_list", "sane_lists"],
                             extension_configs={"toc": {"permalink": "#", "toc_depth": "2-3"}})
    html = conv.convert(md)
    for i, block in enumerate(blocks):
        html = html.replace(f"<p>MERMAIDBLOCK{i}</p>", block)
    html = re.sub(r"<table>(.*?)</table>", r'<div class="table-wrap"><table>\1</table></div>', html, flags=re.S)
    html = html.replace('<p><img alt="', '<p class="figure"><img alt="')
    html = re.sub(r'<p class="figure">(<img [^>]*src="assets/banner.svg"[^>]*>)</p>', r'<div class="banner">\1</div>', html)
    title = re.sub(r"<[^>]+>", "", re.search(r"<h1[^>]*>(.*?)</h1>", html).group(1)).replace("#", "").strip()
    return html, conv.toc, title


def page_html(theme: dict, body: str, toc: str, title: str, current: str) -> str:
    here = ' aria-current="page"'
    nav = "".join(f'<a href="{p}"{here if p == current else ""}>{label}</a>' for _, p, label in PAGES)
    stamp = '<span class="stamp">FOR REVIEW</span>' if theme["name"] == "majlisofai" else ""
    return f"""<!doctype html>
<html lang="en" data-brand="{theme['name']}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>{escape(title)} · {escape(theme['title'])}</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="{theme['fonts_css']}">
<link rel="stylesheet" href="assets/docs.css">
<link rel="icon" href="assets/mark.svg">
</head>
<body>
<header class="bar">
  <a class="brand" href="index.html"><img src="assets/mark.svg" alt=""><span class="wordmark">{escape(theme['wordmark'])}</span><span class="tag">{escape(theme['tag'])}</span></a>
  <nav aria-label="Pages">{nav}</nav>
</header>
<div class="layout">
  <aside class="toc" aria-label="On this page"><span class="eyebrow">On this page</span>{toc}</aside>
  <main class="doc">{body}</main>
</div>
<footer><span><span class="ping"></span>Airport real-time fraud detection · local MLOps lab</span><span>T1 · {current}</span>{stamp}</footer>
<script src="{MERMAID_JS}"></script>
<script>mermaid.initialize({{ startOnLoad: true, theme: "base", securityLevel: "strict", themeVariables: {json.dumps(theme['mermaid'])} }});</script>
</body>
</html>
"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--brand", default="majlisofai")
    parser.add_argument("--images", type=Path, required=True, help="folder with the brand's diagram PNGs")
    args = parser.parse_args()
    brand_dir = ROOT / "brand" / args.brand
    theme = json.loads((brand_dir / "brand.json").read_text())
    out = ROOT / "site" / args.brand
    shutil.rmtree(out, ignore_errors=True)
    (out / "assets").mkdir(parents=True)
    (out / "images").mkdir()
    for name in ("docs.css", "mark.svg", "banner.svg"):
        shutil.copy(brand_dir / name, out / "assets" / name)
    for f in list(args.images.glob("*.png")) + list(args.images.glob("*.drawio")):
        shutil.copy(f, out / "images" / f.name)
    for src, dest, _ in PAGES:
        body, toc, title = render(rewrite((ROOT / src).read_text(), args.brand), theme)
        (out / dest).write_text(page_html(theme, body, toc, title, dest))
        print(f"  site/{args.brand}/{dest}")


if __name__ == "__main__":
    main()
