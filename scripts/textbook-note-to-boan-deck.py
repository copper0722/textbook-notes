#!/usr/bin/env python3
"""
textbook-note-to-boan-deck.py — convert a textbook note .md into a
slide-deck HTML blob suitable for the BoAn CMS `info` field.

Only TEACHING SLIDES + the chapter cover are emitted. KEY TAKEAWAYS
stays out — those go to FB as PNG cards via textbook-fb-render.

Layout: vertical stack of styled <section class="slide"> cards, each
with a label / title / bullets. Inline <style> so the CMS does not
need to load external CSS. Renders readably on mobile (single column).

Usage:
    textbook-note-to-boan-deck.py --input Ch01_...md --out /tmp/Ch01_deck.html
    textbook-note-to-boan-deck.py --input Ch01_...md --publish \\
        [--update-id 66104] [--group-id 484]

If --publish without --update-id → creates a new article.
With --update-id → updates that article.
"""
from __future__ import annotations

import argparse
import html as _html
import json
import re
import subprocess
import sys
from pathlib import Path

# Reuse the battle-tested parser from textbook-fb-render.
RENDER_DIR = Path.home() / "repos/dev/textbook-fb-render/scripts"
if str(RENDER_DIR) not in sys.path:
    sys.path.insert(0, str(RENDER_DIR))

from render import parse_markdown, Slide  # noqa: E402


# ──────────────────────────────────────────────────────────────────────
# HTML template
# ──────────────────────────────────────────────────────────────────────

CSS = """
@import url('https://fonts.googleapis.com/css2?family=Cormorant+Garamond:ital,wght@0,500;0,600;1,500&family=Caveat:wght@500;700&family=Work+Sans:wght@400;500&family=Noto+Serif+TC:wght@500;600&family=Noto+Sans+TC:wght@400;500&display=swap');

.boan-deck { --ink:#2a2520; --muted:#8a7d68; --paper:#f5efe0; --rule:#c9bda0; --margin:#c94a3b; --marker:#f2c94c; --accent:#3a6b52;
  font-family: 'Cormorant Garamond','Noto Serif TC','Songti TC',serif; color:var(--ink);
  max-width: 860px; margin: 0 auto; line-height: 1.6; }

.boan-deck .slide { position: relative; background: var(--paper); padding: 56px 64px 56px 120px; margin: 22px 0;
  border-radius: 4px; box-shadow: 0 3px 14px rgba(0,0,0,.09);
  background-image:
    radial-gradient(ellipse at 20% 10%, rgba(255,255,255,.5), transparent 50%),
    radial-gradient(ellipse at 80% 90%, rgba(0,0,0,.04), transparent 60%),
    repeating-linear-gradient(180deg, transparent 0, transparent 35px, var(--rule) 35px, var(--rule) 36px);
  background-size: 100% 100%, 100% 100%, 100% 36px;
  background-repeat: no-repeat, no-repeat, repeat-y;
  background-position: 0 0, 0 0, 0 80px;
}
/* red vertical margin line */
.boan-deck .slide::before { content:""; position:absolute; left:88px; top:0; bottom:0; width:1px; background:var(--margin); opacity:.7; }
/* 3 punch holes on the left gutter */
.boan-deck .slide::after { content:""; position:absolute; left:26px; top:0; bottom:0; width:22px;
  background-image:
    radial-gradient(circle at 11px 18%, #e0d6bd 10px, transparent 11px),
    radial-gradient(circle at 11px 50%, #e0d6bd 10px, transparent 11px),
    radial-gradient(circle at 11px 82%, #e0d6bd 10px, transparent 11px);
}

.boan-deck .slide-num { font-family:'Caveat',cursive; font-size:22px; color:var(--margin); letter-spacing:.05em; margin-bottom:2px; }

.boan-deck .slide h2 { font-family:'Cormorant Garamond','Noto Serif TC',serif; font-weight:600; font-size:34px;
  margin: 0 0 4px; line-height: 1.12; color: var(--ink); border: none; padding: 0; }
.boan-deck .slide h2 .zh { display:block; font-family:'Caveat','Kalam',cursive; font-size:24px; color:var(--accent);
  font-weight:500; margin-top:4px; letter-spacing:.02em; }

.boan-deck .slide ul { list-style: none; padding: 0; margin: 28px 0 0; counter-reset: bullet; font-size: 17px; }
.boan-deck .slide li { position: relative; margin: 0 0 14px; padding-left: 44px; counter-increment: bullet;
  font-family:'Cormorant Garamond','Noto Serif TC',serif; line-height: 1.45; }
.boan-deck .slide li::before { content: counter(bullet, decimal-leading-zero);
  position:absolute; left:0; top:0; width:32px; font-family:'Caveat',cursive; font-size:22px;
  color:var(--margin); font-weight:700; text-align:right; }
.boan-deck .slide li .zh { display:block; font-family:'Caveat','Kalam',cursive; font-size:18px;
  color:var(--accent); margin-top:2px; letter-spacing:.02em; }

.boan-deck .slide p { font-family:'Cormorant Garamond','Noto Serif TC',serif; font-size:17px; margin:10px 0; }

.boan-deck .slide blockquote { position:relative; border:none; margin: 18px 0; padding-left:48px;
  font-family:'Cormorant Garamond',serif; font-style:italic; font-size:20px; color:var(--ink); }
.boan-deck .slide blockquote::before { content:"“"; position:absolute; left:0; top:-18px;
  font-family:'Cormorant Garamond',serif; font-size:72px; color:var(--margin); opacity:.7; line-height:1; }

/* highlight block — yellow marker */
.boan-deck .slide .highlight, .boan-deck .slide p.highlight {
  display:inline; background:linear-gradient(180deg, transparent 0%, transparent 40%, var(--marker) 40%, var(--marker) 92%, transparent 92%);
  padding: 0 4px; }

/* COVER — big serif title, handwritten accents, washi tape corner */
.boan-deck .cover { padding: 120px 64px 120px 120px; min-height: 360px; }
.boan-deck .cover .slide-num { font-size: 28px; transform: rotate(-2deg); display:inline-block; }
.boan-deck .cover h1 { font-family:'Cormorant Garamond','Noto Serif TC',serif; font-weight:600;
  font-size: 48px; line-height: 1.08; margin: 12px 0 0; letter-spacing: -0.5px; color: var(--ink); border:none; }
.boan-deck .cover h1 .zh { display:block; font-family:'Caveat','Kalam',cursive; font-size:38px;
  color: var(--margin); font-weight:700; margin-top:18px; transform: rotate(-1deg); }
.boan-deck .cover .zh { font-family:'Caveat',cursive; font-size: 26px; color: var(--accent);
  margin-top: 16px; display:block; }
/* washi-tape corner decoration */
.boan-deck .cover::before { content:""; position:absolute; right:60px; top:40px; width:140px; height:32px;
  background: repeating-linear-gradient(45deg, #f4b6a0 0 10px, #f8c8b5 10px 20px);
  transform: rotate(8deg); opacity:.85; box-shadow: 0 3px 8px rgba(0,0,0,.08);
  left:auto; /* override the margin-line ::before */
}
.boan-deck .cover::after { display:none; } /* override the punch-holes ::after for covers */

/* OUTRO — italic end-page */
.boan-deck .outro { background: #faf5e6; font-family:'Caveat',cursive; font-size: 32px;
  color: var(--muted); text-align: center; padding: 40px 20px; font-style: normal; }
.boan-deck .outro::before, .boan-deck .outro::after { display: none; }

@media (max-width: 640px) {
  .boan-deck .slide { padding: 32px 20px 32px 52px; }
  .boan-deck .slide::before { left: 36px; }
  .boan-deck .slide::after { width: 14px; left: 12px;
    background-image:
      radial-gradient(circle at 7px 18%, #e0d6bd 6px, transparent 7px),
      radial-gradient(circle at 7px 50%, #e0d6bd 6px, transparent 7px),
      radial-gradient(circle at 7px 82%, #e0d6bd 6px, transparent 7px);
  }
  .boan-deck .slide h2 { font-size: 26px; }
  .boan-deck .slide ul, .boan-deck .slide p { font-size: 15.5px; }
  .boan-deck .cover { padding: 60px 28px 60px 52px; }
  .boan-deck .cover h1 { font-size: 32px; }
  .boan-deck .cover h1 .zh { font-size: 26px; }
}
""".strip()


def _bil_span(en: str, zh: str) -> str:
    """Render en / zh pair — primary + <span class='zh'>secondary</span>."""
    en_e = _html.escape(en)
    zh_e = _html.escape(zh)
    if en and zh:
        return f"{en_e}<span class=\"zh\">{zh_e}</span>"
    return en_e or zh_e


def _slide_to_html(s: Slide, idx: int) -> str:
    label = _html.escape(s.label or f"{idx:02d}")

    if s.kind == "cover":
        return (
            f'<section class="slide cover" data-kind="cover">'
            f'<div class="slide-num">{label}</div>'
            f'<h1>{_html.escape(s.title or s.titleZh)}'
            + (f'<span class="zh">{_html.escape(s.titleZh)}</span>' if s.title and s.titleZh else "")
            + f'</h1>'
            + (f'<div class="zh">{_html.escape(s.subtitleZh)}</div>' if s.subtitleZh else "")
            + "</section>"
        )

    if s.kind == "outro":
        return (
            f'<section class="slide outro" data-kind="outro">'
            f'{_html.escape(s.title or s.titleZh or "本章完")}'
            f'</section>'
        )

    if s.kind == "quote":
        q = _bil_span(s.quote, s.quoteZh)
        attrib = f'<p style="text-align:right;color:#888;">{_html.escape(s.attribution)}</p>' if s.attribution else ""
        return (
            f'<section class="slide" data-kind="quote">'
            f'<div class="slide-num">{label}</div>'
            f'<blockquote style="border-left:4px solid #1c3d66;padding-left:16px;color:#333;'
            f'font-style:italic;font-size:18px;margin:0;">{q}</blockquote>{attrib}</section>'
        )

    # content / section
    title_html = ""
    if s.title or s.titleZh:
        title_html = f"<h2>{_bil_span(s.title, s.titleZh)}</h2>"

    bullets_html = ""
    if s.bullets:
        lis = "".join(f"<li>{_bil_span(b.get('en', ''), b.get('zh', ''))}</li>" for b in s.bullets)
        bullets_html = f"<ul>{lis}</ul>"

    highlight_html = ""
    if s.highlight or s.highlightZh:
        highlight_html = f"<p>{_bil_span(s.highlight, s.highlightZh)}</p>"

    return (
        f'<section class="slide" data-kind="content">'
        f'<div class="slide-num">{label}</div>'
        f'{title_html}{highlight_html}{bullets_html}'
        f'</section>'
    )


def slides_to_deck_html(slides: list[Slide], *, title: str) -> str:
    cards = "\n".join(_slide_to_html(s, i + 1) for i, s in enumerate(slides))
    return (
        f'<style>{CSS}</style>\n'
        f'<div class="boan-deck">\n{cards}\n</div>'
    )


# ──────────────────────────────────────────────────────────────────────
# Frontmatter helpers
# ──────────────────────────────────────────────────────────────────────

def _strip_yaml(text: str) -> tuple[dict, str]:
    m = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    if not m:
        return {}, text
    fm: dict = {}
    for line in m.group(1).splitlines():
        mk = re.match(r'^([A-Za-z_][\w-]*)\s*:\s*(.*)$', line)
        if mk:
            fm[mk.group(1)] = mk.group(2).strip().strip('"').strip("'")
    return fm, text[m.end():]


# ──────────────────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(description="Textbook note .md → BoAn slide-deck HTML")
    ap.add_argument("--input", required=True, type=Path)
    ap.add_argument("--out", type=Path, default=None, help="Write deck HTML to file")
    ap.add_argument("--publish", action="store_true")
    ap.add_argument("--update-id", default="", help="Update existing BoAn article id (else CREATE)")
    ap.add_argument("--group-id", type=int, default=484)
    ap.add_argument("--include-kt", action="store_true",
                    help="Include KEY TAKEAWAYS slides in the deck (default: drop — those go to FB)")
    args = ap.parse_args()

    md = args.input.read_text(encoding="utf-8")
    fm, _ = _strip_yaml(md)
    title = fm.get("title", args.input.stem)

    chapter_hint = ""
    mch = re.search(r"Ch\s*(\d+)", args.input.name, re.IGNORECASE)
    if mch:
        chapter_hint = f"Ch {mch.group(1).zfill(2)}"

    slides = parse_markdown(md, chapter_hint=chapter_hint)
    # Drop KT + outro. Keep cover + teaching.
    if not args.include_kt:
        slides = [s for s in slides if s.source_section != "key_takeaways"]
    slides = [s for s in slides if s.kind != "outro"]

    print(f"[deck] {len(slides)} slides ({args.input.name})", file=sys.stderr)
    deck_html = slides_to_deck_html(slides, title=title)

    if args.out:
        args.out.write_text(deck_html, encoding="utf-8")
        print(f"wrote {args.out} ({len(deck_html)} chars)", file=sys.stderr)

    if args.publish:
        # brief = first 140 chars of cover subtitle or first bullet
        brief = fm.get("title", title)
        publisher = Path.home() / "repos/Vault/.script/boan-web-publish.py"
        tmp = Path("/tmp/boan_deck_body.html")
        tmp.write_text(deck_html, encoding="utf-8")
        cmd = [
            "python3", str(publisher),
            "update" if args.update_id else "create",
            "--title", title,
            "--brief", brief[:140],
            "--html", str(tmp),
            "--group-id", str(args.group_id),
        ]
        if args.update_id:
            cmd += ["--id", args.update_id]
        r = subprocess.run(cmd, capture_output=True, text=True)
        sys.stdout.write(r.stdout)
        sys.stderr.write(r.stderr)
        sys.exit(r.returncode)


if __name__ == "__main__":
    main()
