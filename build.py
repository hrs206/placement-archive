#!/usr/bin/env python3
"""
Build the placement archive into a single self-contained index.html.

Takes the scraper's JSON and injects it straight into the page, so the result
is one file with no fetch, no CORS problem, and no server -- it works opened
from disk and works on GitHub Pages unchanged.

    python build.py                        # uses data/superset_jobs_clean.json
    python build.py path/to/other.json     # or point it somewhere else

Output: index.html at the repo root (what GitHub Pages serves).
"""

import json
import sys
import datetime
from pathlib import Path

ROOT = Path(__file__).parent
TEMPLATE = ROOT / "src" / "template.html"
DEFAULT_DATA = ROOT / "data" / "superset_jobs_clean.json"
OUTPUT = ROOT / "index.html"

# Fields the page never reads. 'raw' in particular is the verbatim tab text and
# roughly doubles the page size, so it is dropped from the build even if the
# input file still carries it.
DROP_FIELDS = {"raw"}


def load(path: Path):
    if not path.exists():
        sys.exit(
            f"No data file at {path}\n"
            f"Put the scraper's superset_jobs_clean.json in data/, "
            f"or pass a path: python build.py <file.json>"
        )
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        sys.exit(f"{path.name} isn't valid JSON: {e}")

    if not isinstance(data, list):
        sys.exit(f"{path.name} should contain a JSON array of job records.")
    if not data:
        sys.exit(f"{path.name} is an empty list -- nothing to build.")
    return data


def check(jobs):
    """Report anything that would look wrong on the page, rather than shipping
    it silently. None of these stop the build."""
    warn = []
    missing_ctc = [j for j in jobs if j.get("ctc_min") is None and j.get("ctc_max") is None]
    missing_co = [j for j in jobs if not j.get("company")]
    truncated = [j for j in jobs if (j.get("company") or "").endswith("...")]
    no_title = [j for j in jobs if not j.get("title")]

    if missing_ctc:
        warn.append(f"{len(missing_ctc)} without a package (shown as 'Not stated')")
    if missing_co:
        warn.append(f"{len(missing_co)} without a company name")
    if truncated:
        warn.append(f"{len(truncated)} with a truncated company name "
                    f"(e.g. {truncated[0]['company']!r}) -- re-scrape those")
    if no_title:
        warn.append(f"{len(no_title)} without a role title")
    return warn


def main():
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_DATA
    jobs = load(src)

    slim = [{k: v for k, v in j.items() if k not in DROP_FIELDS} for j in jobs]

    if not TEMPLATE.exists():
        sys.exit(f"Missing template at {TEMPLATE}")
    html = TEMPLATE.read_text(encoding="utf-8")

    payload = json.dumps(slim, ensure_ascii=False, separators=(",", ":"))
    # </script> inside any string would end the script block early
    payload = payload.replace("</", "<\\/")

    start, end = "/*__JOBS__*/", "/*__END__*/"
    if start not in html or end not in html:
        sys.exit("Template is missing its data placeholder -- don't edit the "
                 "/*__JOBS__*/ ... /*__END__*/ markers.")
    head = html.split(start)[0]
    tail = html.split(end)[1]
    built = datetime.date.today().strftime("%d %b %Y")
    out = head + start + payload + end + tail
    out = out.replace("/*__BUILT__*/", built)

    OUTPUT.write_text(out, encoding="utf-8")

    kb = OUTPUT.stat().st_size / 1024
    print(f"Built index.html -- {len(slim)} jobs, {kb:.0f} KB")
    for w in check(jobs):
        print(f"  note: {w}")
    print("\nOpen index.html directly, or commit and push to publish.")


if __name__ == "__main__":
    main()
