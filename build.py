#!/usr/bin/env python3
"""
Build the placement archive into a single self-contained index.html.

Reads every scrape in data/, derives a real month from each posting's relative
"N months ago" string, merges the batches, and injects the result straight
into the page -- so the output is one file with no fetch, no CORS and no
server. It works opened from disk and on GitHub Pages unchanged.

    python build.py                     # every *.json in data/
    python build.py a.json b.json       # or name the files

Each file is one account's scrape. Its batch label comes from, in order:
  1. a "batch" field already on the records (the scraper's --batch flag)
  2. the filename, if it contains something like 2024-25
  3. a prompt, so an unlabelled file never silently joins the pile

Output: index.html at the repo root (what GitHub Pages serves).
"""

import json
import re
import sys
import datetime
from pathlib import Path

from dates import derive

ROOT = Path(__file__).parent
TEMPLATE = ROOT / "src" / "template.html"
DATA_DIR = ROOT / "data"
OUTPUT = ROOT / "index.html"

DROP_FIELDS = {"raw"}
BATCH_IN_NAME = re.compile(r"(20\d{2})\s*[-_]\s*(\d{2})")


def load(path: Path):
    if not path.exists():
        sys.exit(f"No data file at {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        sys.exit(f"{path.name} isn't valid JSON: {e}")
    if not isinstance(data, list) or not data:
        sys.exit(f"{path.name} should be a non-empty JSON array of jobs.")
    return data


def batch_for(path: Path, jobs):
    stated = {j.get("batch") for j in jobs if j.get("batch")}
    if len(stated) == 1:
        return stated.pop()
    if len(stated) > 1:
        sys.exit(f"{path.name} mixes batch labels: {sorted(stated)}")

    m = BATCH_IN_NAME.search(path.stem)
    if m:
        return f"{m.group(1)}-{m.group(2)}"

    print(f"\n{path.name} has no batch label.")
    print("  (The scraper's --batch flag sets one; files from before it don't have it.)")
    ans = input("  Batch label for this file, e.g. 2025-26: ").strip()
    if not ans:
        sys.exit("No batch given -- stopping rather than merging it unlabelled.")
    return ans


def drive_name(job):
    """The portal states its own drive name ('Full-Time Placement for
    2025-26 ...') inside the eligibility text. Used only to cross-check the
    batch label, never to override it."""
    for key in ("academic_eligibility", "other_restrictions",
                "course_eligibility", "additional_information"):
        t = job.get(key) or ""
        m = re.search(r"Placement for (20\d{2}-\d{2})", t)
        if m:
            return m.group(1)
    return None


def prepare(jobs, batch):
    out = []
    for j in jobs:
        rec = {k: v for k, v in j.items() if k not in DROP_FIELDS}
        rec["batch"] = batch
        # index alone collides: every scrape numbers its jobs from 0
        rec["uid"] = f"{batch}#{j.get('index')}"
        d = derive(j.get("posted"), j.get("scraped_on"))
        if d:
            rec.update(d)
        out.append(rec)
    return out


def check(all_jobs, by_batch):
    warn = []
    for b, jobs in by_batch.items():
        drives = {d for d in (drive_name(j) for j in jobs) if d}
        if drives and b not in drives:
            warn.append(f"batch {b!r}: the portal's own text mentions "
                        f"{sorted(drives)} -- check the label is right")

    def count(f):
        return sum(1 for j in all_jobs if f(j))

    n = count(lambda j: j.get("ctc_min") is None and j.get("ctc_max") is None)
    if n:
        warn.append(f"{n} without a package (shown as 'Not stated')")
    n = count(lambda j: (j.get("company") or "").endswith("..."))
    if n:
        warn.append(f"{n} with a truncated company name -- re-scrape those")
    n = count(lambda j: not j.get("posted_month"))
    if n:
        warn.append(f"{n} whose posting date couldn't be read "
                    f"(shown without a date)")
    return warn


def main():
    if len(sys.argv) > 1:
        files = [Path(a) for a in sys.argv[1:]]
    else:
        files = sorted(DATA_DIR.glob("*.json"))
    if not files:
        sys.exit(f"No .json files in {DATA_DIR}. Put a scrape there first.")

    all_jobs, by_batch = [], {}
    for f in files:
        jobs = load(f)
        batch = batch_for(f, jobs)
        prepped = prepare(jobs, batch)
        by_batch.setdefault(batch, []).extend(prepped)
        all_jobs.extend(prepped)
        print(f"  {f.name}: {len(jobs)} jobs -> batch {batch}")

    dupes = len(all_jobs) - len({j["uid"] for j in all_jobs})
    if dupes:
        sys.exit(f"\n{dupes} duplicate records across files -- the same scrape "
                 f"is probably in data/ twice under different names.")

    if not TEMPLATE.exists():
        sys.exit(f"Missing template at {TEMPLATE}")
    html = TEMPLATE.read_text(encoding="utf-8")

    payload = json.dumps(all_jobs, ensure_ascii=False, separators=(",", ":"))
    payload = payload.replace("</", "<\\/")   # a stray </script> would end the block

    start, end = "/*__JOBS__*/", "/*__END__*/"
    if start not in html or end not in html:
        sys.exit("Template is missing its data placeholder.")
    out = html.split(start)[0] + start + payload + end + html.split(end)[1]
    out = out.replace("/*__BUILT__*/", datetime.date.today().strftime("%d %b %Y"))
    OUTPUT.write_text(out, encoding="utf-8")

    kb = OUTPUT.stat().st_size / 1024
    print(f"\nBuilt index.html -- {len(all_jobs)} jobs across "
          f"{len(by_batch)} batch(es), {kb:.0f} KB")
    exact = sum(1 for j in all_jobs if j.get("posted_precision") == "exact")
    print(f"  dates: {exact} to the month, {len(all_jobs) - exact} approximate")
    for w in check(all_jobs, by_batch):
        print(f"  note: {w}")
    print("\nOpen index.html, or commit and push to publish.")


if __name__ == "__main__":
    main()
