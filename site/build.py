"""Build the static site into site/_site/.

Usage: python site/build.py [path/to/METHOD.md]
"""
import json
import re
import shutil
import sys
from pathlib import Path

import markdown

SITE = Path(__file__).resolve().parent
OUT = SITE / "_site"
STATIC = ["index.html", "how-it-works.html", "api.html", "how-it-works.js", "style.css", "CNAME"]

TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Method - Ingress MU calculator</title>
<link rel="stylesheet" href="style.css">
</head>
<body>
<header>
  <span class="site">Ingress MU calculator</span>
  <a href="./">Calculator</a>
  <a href="how-it-works.html">How it works</a>
  <a href="method.html" aria-current="page">Method</a>
  <a href="api.html">API</a>
  <a href="https://github.com/InvestigateXM/Ingress-MU-calculation">GitHub</a>
</header>
<main>
{body}
</main>
<footer>
  Independent reconstruction; not affiliated with or endorsed by Niantic. Population data: Global Rural-Urban Mapping Project, Version 1 (GRUMP v1), CIESIN / NASA SEDAC. Source and API description: <a href="https://github.com/InvestigateXM/Ingress-MU-calculation">GitHub</a>.
</footer>
</body>
</html>
"""


def main():
    source = Path(sys.argv[1]) if len(sys.argv) > 1 else SITE.parent / "docs" / "METHOD.md"
    if not source.is_file():
        sys.exit(f"build.py: method source not found: {source}")
    html = markdown.markdown(
        source.read_text(encoding="utf-8"),
        extensions=["tables", "fenced_code", "toc"],
    )
    # Link the contents list to the numbered section headings.
    ids = iter(re.findall(r'<h2 id="(\d+-[^"]*)"', html))
    contents = re.search(r"<ol>.*?</ol>", html, re.S)
    if contents and contents.group(0).count("<li>") == len(re.findall(r'<h2 id="\d+-', html)):
        linked = re.sub(r"<li>(.*?)</li>", lambda m: f'<li><a href="#{next(ids)}">{m.group(1)}</a></li>', contents.group(0))
        html = html.replace(contents.group(0), linked, 1)
    shutil.rmtree(OUT, ignore_errors=True)
    OUT.mkdir()
    (OUT / "method.html").write_text(TEMPLATE.replace("{body}", html), encoding="utf-8")
    for name in STATIC:
        shutil.copy(SITE / name, OUT / name)
    maps = {f.stem: json.loads(f.read_text(encoding='utf-8')) for f in sorted((SITE / 'maps').glob('a*.json'))}
    page = OUT / 'how-it-works.html'
    page.write_text(page.read_text(encoding='utf-8').replace('<!-- MAP_DATA -->',
        '<script type="application/json" id="map-data">' + json.dumps(maps, ensure_ascii=False, separators=(',', ':')).replace('<', '\\u003c') + '</script>'), encoding='utf-8')
    shutil.copytree(SITE / 'maps', OUT / 'maps')
    shutil.copytree(SITE / "traces", OUT / "traces")
    print(f"built {OUT} from {source}")


if __name__ == "__main__":
    main()
