"""Build the static site into site/_site/.

Usage: python site/build.py [path/to/METHOD.md]
"""
import shutil
import sys
from pathlib import Path

import markdown

SITE = Path(__file__).resolve().parent
OUT = SITE / "_site"
STATIC = ["index.html", "style.css", "CNAME"]

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
  <a href="method.html" aria-current="page">Method</a>
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
    shutil.rmtree(OUT, ignore_errors=True)
    OUT.mkdir()
    (OUT / "method.html").write_text(TEMPLATE.replace("{body}", html), encoding="utf-8")
    for name in STATIC:
        shutil.copy(SITE / name, OUT / name)
    print(f"built {OUT} from {source}")


if __name__ == "__main__":
    main()
