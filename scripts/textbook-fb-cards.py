#!/usr/bin/env python3
"""textbook-fb-cards.py — generate FB-ready 1080×1080 carousel PNGs from
textbook short-note KEY TAKEAWAYS.

Pipeline:
  1. Scan vault notes with frontmatter `publish: true`.
  2. Parse `## KEY TAKEAWAYS` bullets.
  3. Measure each bullet (CJK-aware width: zh char = 2, latin = 1).
  4. Pack into cards: each card body ≤ MAX_BODY_WIDTH (default 260 zh-eq).
     Long bullets auto-split at sentence boundaries (。/.! ?；;).
  5. Generate Marp 1:1 slide deck per chapter:
       - 01: cover (book + chapter + author)
       - 02..N-1: one takeaway per slide (or split-segment per slide)
       - N: CTA (URL + QR code placeholder)
  6. Marp CLI exports each slide as PNG (1080×1080, 2× scale = 2160×2160).
  7. PNGs land in repos/note/textbook-notes/cards/{book}/{ch}/{NN}.png

Usage:
  python3 textbook-fb-cards.py [--book {prefix}] [--chapter {prefix}] [--dry-run]

Output: ready-to-upload FB carousel set (≤10 PNGs ideal; if more, Copper
selects the most-impactful or splits to multiple posts).
"""
from __future__ import annotations
import argparse
import datetime
import os
import re
import shutil
import subprocess
import sys
import unicodedata
from pathlib import Path

import yaml

VAULT = Path.home() / "repos" / "Vault"
SCAN_ROOTS = [VAULT / "proj" / "note" / "textbooks"]
OUTPUT_REPO = Path.home() / "repos" / "textbook-notes"
OUTPUT_DIR = OUTPUT_REPO / "cards"  # cards/{book}/{ch}/{NN}.png

# Card body width budget (CJK-eq chars, where zh char = 2, latin = 1)
MAX_BODY_WIDTH = 260
SOFT_BODY_WIDTH = 200  # prefer ≤ this for breathing room
MIN_BODY_WIDTH = 60   # don't make tiny cards; pack short bullets together

PAGES_BASE_URL = "https://copper0722.github.io/textbook-notes"

FM_BOUND = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
TAKEAWAY_HEADER = re.compile(r"^## KEY TAKEAWAYS\s*\n(.*?)(?=\n## |\Z)", re.DOTALL | re.MULTILINE)
BULLET = re.compile(r"^-\s+(.+)$", re.MULTILINE)


def parse_frontmatter(text: str) -> tuple[dict | None, str]:
    m = FM_BOUND.match(text)
    if not m:
        return None, text
    try:
        fm = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError:
        return None, text
    return fm, text[m.end():]


def cjk_width(s: str) -> int:
    """Display width: CJK 2, Latin 1."""
    return sum(2 if unicodedata.east_asian_width(c) in ("W", "F") else 1 for c in s)


def split_long_bullet(bullet: str, max_width: int) -> list[str]:
    """Split a bullet that exceeds max_width at sentence boundaries.
    Order of preference: 。 ！ ？ ； . ! ? ; (with optional surrounding whitespace).
    Last resort: split at comma 、 ， , (only if still over budget).
    """
    if cjk_width(bullet) <= max_width:
        return [bullet]
    # Sentence-end pattern that keeps the punctuation with the preceding chunk
    sentence_split = re.compile(r"([。！？；.!?;])\s*")
    parts = sentence_split.split(bullet)
    # parts = [text, punct, text, punct, ..., text]
    chunks = []
    cur = ""
    for i in range(0, len(parts), 2):
        seg = parts[i] + (parts[i + 1] if i + 1 < len(parts) else "")
        if not seg.strip():
            continue
        candidate = (cur + seg).strip()
        if cjk_width(candidate) <= max_width or not cur:
            cur = candidate
        else:
            chunks.append(cur)
            cur = seg.strip()
    if cur:
        chunks.append(cur)

    # If any chunk still too long, sub-split at commas
    final = []
    for c in chunks:
        if cjk_width(c) <= max_width:
            final.append(c)
            continue
        comma_split = re.compile(r"([、，,])\s*")
        sub = comma_split.split(c)
        cur = ""
        for i in range(0, len(sub), 2):
            seg = sub[i] + (sub[i + 1] if i + 1 < len(sub) else "")
            candidate = (cur + seg).strip()
            if cjk_width(candidate) <= max_width or not cur:
                cur = candidate
            else:
                final.append(cur)
                cur = seg.strip()
        if cur:
            final.append(cur)
    return final


def pack_takeaways(bullets: list[str]) -> list[dict]:
    """Pack bullets into card-sized chunks.
    Returns list of {kind: 'takeaway', body: str, idx: int}.
    Long bullets split into multiple cards (idx incremented).
    """
    cards = []
    for b in bullets:
        chunks = split_long_bullet(b, MAX_BODY_WIDTH)
        for chunk in chunks:
            cards.append({"kind": "takeaway", "body": chunk})
    return cards


def build_marp_slides(book: str, chapter: str, title: str, author: str, cards: list[dict],
                       pages_url: str) -> str:
    """Generate Marp 1:1 slide deck markdown. Each card → 1 slide."""
    n_cards = len(cards) + 2  # +cover +cta
    header = f"""---
marp: true
size: 1080:1080
paginate: false
header: ""
footer: ""
style: |
  section {{
    background: linear-gradient(180deg, #ffffff 0%, #f0f4f9 100%);
    color: #1e293b;
    font-family: -apple-system, BlinkMacSystemFont, "PingFang TC", "Heiti TC", "Microsoft JhengHei", "Noto Sans TC", sans-serif;
    padding: 60px 70px;
    display: flex;
    flex-direction: column;
    justify-content: space-between;
  }}
  section.cover {{
    background: linear-gradient(135deg, #1a5276 0%, #2c3e50 100%);
    color: #ffffff;
    text-align: center;
    align-items: center;
    justify-content: center;
  }}
  section.cover h1 {{
    font-size: 48px;
    line-height: 1.4;
    margin: 0 0 30px;
    font-weight: 700;
  }}
  section.cover .meta {{
    font-size: 24px;
    opacity: 0.85;
    margin-top: 24px;
  }}
  section.takeaway .head {{
    font-size: 18px;
    color: #1a5276;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    font-weight: 600;
    border-bottom: 2px solid #1a5276;
    padding-bottom: 12px;
  }}
  section.takeaway .body {{
    font-size: 36px;
    line-height: 1.7;
    text-align: left;
    flex: 1;
    display: flex;
    align-items: center;
    color: #1e293b;
  }}
  section.takeaway .body strong {{ color: #1a5276; }}
  section.takeaway .body em {{ color: #475569; font-style: italic; }}
  section.takeaway .foot {{
    font-size: 16px;
    color: #64748b;
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    border-top: 1px solid #cbd5e1;
    padding-top: 14px;
  }}
  section.cta {{
    background: #f0f4f9;
    text-align: center;
    align-items: center;
    justify-content: center;
  }}
  section.cta h2 {{
    font-size: 38px;
    color: #1a5276;
    margin-bottom: 24px;
  }}
  section.cta .url {{
    font-size: 22px;
    color: #475569;
    font-family: "SF Mono", "Menlo", monospace;
    background: #ffffff;
    padding: 16px 24px;
    border-radius: 12px;
    display: inline-block;
    margin: 20px 0;
    border: 2px dashed #cbd5e1;
  }}
  section.cta .author {{
    margin-top: 30px;
    font-size: 20px;
    color: #1a5276;
    font-weight: 600;
  }}
---

"""

    # Cover
    body = f"""<!-- _class: cover -->

# {title}

<div class="meta">{book.replace('_', ' ')} · {chapter.replace('_', ' ')}</div>
<div class="meta">{author}</div>

---

"""

    # Takeaway cards
    for i, c in enumerate(cards, 1):
        body += f"""<!-- _class: takeaway -->

<div class="head">KEY TAKEAWAY {i:02d} / {len(cards):02d}</div>

<div class="body">

{c['body']}

</div>

<div class="foot">
<span>{book.replace('_', ' ')}｜{chapter.replace('_', ' ')}</span>
<span>{author}</span>
</div>

---

"""

    # CTA
    short_url = f"{pages_url}/takeaways/{book}/{chapter}.html"
    body += f"""<!-- _class: cta -->

## 完整 takeaway + slide

<div class="url">{short_url}</div>

<div class="meta">17 個 takeaway 全文 + Marp 教學投影片</div>

<div class="author">— {author} ·  textbook-notes</div>
"""

    return header + body


def render_chapter(note_path: Path, dry: bool, verbose: bool) -> dict:
    text = note_path.read_text(encoding="utf-8")
    fm, body = parse_frontmatter(text)
    if not fm or not fm.get("publish") or fm.get("publish_to") != "textbook-notes":
        return {"skipped": True}

    book = fm.get("book") or note_path.parent.name
    chapter = note_path.stem
    title = fm.get("title", chapter)
    # Strip "｜English subtitle" if present, keep the leading zh part for cover
    cover_title = title.split("｜")[0].strip() if "｜" in title else title
    author = "王介立醫師"

    m = TAKEAWAY_HEADER.search(body)
    if not m:
        return {"error": "no ## KEY TAKEAWAYS section"}
    takeaway_block = m.group(1)
    bullets = [b.strip() for b in BULLET.findall(takeaway_block)]
    if not bullets:
        return {"error": "no bullets in KEY TAKEAWAYS"}

    cards = pack_takeaways(bullets)

    marp_md = build_marp_slides(book, chapter, cover_title, author, cards, PAGES_BASE_URL)

    out_dir = OUTPUT_DIR / book / chapter
    out_dir.mkdir(parents=True, exist_ok=True)

    # Write the Marp source for inspection + the PNGs
    marp_src = out_dir / f"_source.md"
    marp_src.write_text(marp_md, encoding="utf-8")

    if dry:
        return {"book": book, "chapter": chapter, "n_cards": len(cards) + 2,
                "marp_src": str(marp_src), "rendered": False}

    # marp --images png --image-scale 2 generates {basename}.001.png ... .NNN.png
    cmd = ["marp", str(marp_src), "--images", "png", "--image-scale", "2",
           "--output", str(out_dir / "card.png")]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        return {"error": f"marp failed: {res.stderr.strip()[:300]}"}

    # Marp names them card.001.png, card.002.png, ...
    # Re-name to NN-{kind}.png for clarity
    pngs = sorted(out_dir.glob("card.*.png"))
    rename_log = []
    for idx, p in enumerate(pngs):
        if idx == 0:
            new_name = "00-cover.png"
        elif idx == len(pngs) - 1:
            new_name = f"{idx:02d}-cta.png"
        else:
            new_name = f"{idx:02d}-takeaway.png"
        target = out_dir / new_name
        if target.exists():
            target.unlink()
        p.rename(target)
        rename_log.append(new_name)

    if verbose:
        print(f"  ✓ {book}/{chapter}: {len(pngs)} PNGs → {out_dir.relative_to(OUTPUT_REPO)}")
        for n in rename_log[:3]:
            print(f"      {n}")
        if len(rename_log) > 3:
            print(f"      ... ({len(rename_log) - 3} more)")

    return {"book": book, "chapter": chapter, "n_cards": len(pngs),
            "marp_src": str(marp_src), "rendered": True, "files": rename_log}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--book", help="Filter by book key (e.g. 2026_Campbell_13e)")
    p.add_argument("--chapter", help="Filter by chapter prefix (e.g. Ch01)")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args()

    if not shutil.which("marp"):
        print("marp CLI not found. brew install marp-cli", file=sys.stderr)
        sys.exit(2)

    candidates = []
    for root in SCAN_ROOTS:
        if root.is_dir():
            candidates.extend(root.rglob("*.md"))

    matched = 0
    rendered = 0
    errors = 0
    for note in candidates:
        if args.book and args.book not in str(note):
            continue
        if args.chapter and args.chapter not in note.name:
            continue
        result = render_chapter(note, args.dry_run, args.verbose)
        if result.get("skipped"):
            continue
        matched += 1
        if "error" in result:
            errors += 1
            print(f"  ✗ {note.name}: {result['error']}", file=sys.stderr)
        elif result.get("rendered"):
            rendered += 1

    print(f"textbook-fb-cards: matched={matched} rendered={rendered} errors={errors}"
          f"{' [dry-run]' if args.dry_run else ''}")
    return 0 if errors == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
