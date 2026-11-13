"""Container entrypoint and command-line calculator."""

import json
import os
import sys
from .download import ensure_data


def main():
    command = sys.argv[1] if len(sys.argv) > 1 else "serve"
    if command not in ("serve", "calc", "download"):
        raise SystemExit(
            "Usage: python -m mu_calculator [serve|calc p1 p2 p3|download]"
        )
    folder = os.environ.get("GRUMP_DATA", "/data/grump")
    ensure_data(folder)
    os.environ.setdefault("GRUMP_DIR", os.path.join(folder, "bil"))
    if command == "download":
        return
    if command == "calc":
        from . import Grump, MODEL
        from .coordinates import calculate

        print(json.dumps(dict(calculate(Grump(), sys.argv[2:]), model=MODEL)))
    else:
        import uvicorn

        uvicorn.run(
            "mu_calculator.api:app", host="0.0.0.0", port=8000, access_log=False
        )


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        raise SystemExit(str(error)) from None
