#!/usr/bin/env python3
"""textbook-share-sync — publish complete notes to GitHub share repos.

Scans vault notes for frontmatter `publish: true` + `publish_to: <repo>`.
For each matched note, extracts KEY TAKEAWAYS + TEACHING SLIDES sections
and writes to the target repo's standard layout. Unpublished notes
(publish: false or field removed) → remove from target repo.

Supersedes `brenner-slides-sync.py` (2026-04-19, hardcoded book list
replaced with frontmatter-driven routing per Vault §9.3 doctrine).

Layout per target repo:
  textbook-notes/
    takeaways/{book_slug}/{chapter_slug}.md   ← KEY TAKEAWAYS only
    slides/{book_slug}/{chapter_slug}.md      ← Marp slide deck
  nephro-cme/
    note/{chapter_slug}.md                    ← full note body (zh-TW for exam)
    slides/{book_slug}/{chapter_slug}.md      ← Marp slide deck

Writes are idempotent and marked via sync frontmatter `_synced_from:` +
`_synced_at:`. Human-authored files without `_synced_from:` are never touched.

Run: python3 textbook-share-sync.py [--dry-run] [--verbose]
Cron/launchd: hourly.
"""
from __future__ import annotations
import argparse
import datetime
import os
import re
import sys
import yaml
from pathlib import Path


def _resolve_vault() -> Path:
    # Phase 9 (2026-04-23, Law §8.1): git repo canonical; Dropbox legacy fallback only.
    for p in (
        Path.home() / "repos" / "Vault",
        Path.home() / "VaultBinary",
        Path.home() / "Library" / "CloudStorage" / "Dropbox" / "Vault_Binary",
    ):
        if p.exists():
            return p
    return Path.home() / "repos" / "Vault"


VAULT = _resolve_vault()
# 2026-04-22: standalone repos (~/repos/{name}) are canonical per Law §8.3 / admin/REPOS.md.
# Earlier code wrote to vault-internal duplicates (~/repos/Vault/repos/{name}) which were
# gitignored from vault and never reached GitHub. Retargeted to standalone — single source.
STANDALONE_REPOS = Path.home() / "repos"

ALLOWED_TARGETS = {
    "textbook-notes": STANDALONE_REPOS / "textbook-notes",
    "nephro-cme": STANDALONE_REPOS / "nephro-cme",
}

SCAN_ROOTS = [
    # Layer split (Copper 2026-04-20): notes live in proj/note/, not in raw/.
    # raw/ now holds raw.md + source.pdf only. Scan proj/note/ as primary.
    VAULT / "proj" / "note",
    # Legacy raw/ paths kept during migration window — drop after cleanup confirmed.
    VAULT / "raw" / "books",
    VAULT / "raw" / "articles",
    VAULT / "raw" / "clinical_medicine" / "internal_medicine",
]

SYNC_FRONTMATTER_KEYS = {"_synced_from", "_synced_at"}

FM_BOUND = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def parse_frontmatter(text: str) -> tuple[dict | None, str]:
    m = FM_BOUND.match(text)
    if not m:
        return None, text
    try:
        fm = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError:
        return None, text
    body = text[m.end():]
    return fm, body


def build_frontmatter(data: dict) -> str:
    return "---\n" + yaml.safe_dump(data, allow_unicode=True, sort_keys=False).strip() + "\n---\n"


def slugify_zh(name: str) -> str:
    # Preserve zh-TW; remove only filesystem-problematic chars.
    return re.sub(r"[\\/:*?\"<>|]", "_", name).strip()


def book_and_chapter(note_path: Path) -> tuple[str, str]:
    """Resolve (book_slug, chapter_slug) from any vault path style:
    - Canonical post-2026-04-20: proj/note/textbooks/{Book}/{Ch}.md → (Book, Ch)
    - Canonical articles: proj/note/articles/{key}.md → ('articles', key)
    - Legacy: raw/books/{Book}/{Ch}.md → (Book, Ch)
    - Topic-tree (2026-04-19): raw/.../_textbooks/{Book}/{Ch}.md → (Book, Ch)
    - Legacy articles: raw/articles/{key}.md → ('articles', key)
    - Other: ('misc', stem)
    """
    rel = note_path.relative_to(VAULT)  # vault-internal note paths only — Path object preserved
    parts = rel.parts
    # Canonical proj/note/
    if parts[0] == "proj" and parts[1] == "note" and len(parts) >= 4 and parts[2] == "textbooks":
        return slugify_zh(parts[3]), slugify_zh(note_path.stem)
    if parts[0] == "proj" and parts[1] == "note" and parts[2] == "articles":
        return "articles", slugify_zh(note_path.stem)
    # Legacy raw/
    if parts[0] == "raw" and parts[1] == "books" and len(parts) >= 3:
        return slugify_zh(parts[2]), slugify_zh(note_path.stem)
    if "_textbooks" in parts:
        i = parts.index("_textbooks")
        if i + 1 < len(parts):
            return slugify_zh(parts[i + 1]), slugify_zh(note_path.stem)
    if parts[0] == "raw" and parts[1] == "articles":
        return "articles", slugify_zh(note_path.stem)
    return "misc", slugify_zh(note_path.stem)


SECTION_RE = {
    "KEY_TAKEAWAYS": re.compile(r"^## KEY TAKEAWAYS\s*\n(.*?)(?=\n## (?!KEY)|\n---\s*\n|\Z)", re.DOTALL | re.MULTILINE),
    "TEACHING_SLIDES": re.compile(r"^## TEACHING SLIDES\s*\n(.*?)(?=\n## (?!\d|Slide)|\Z)", re.DOTALL | re.MULTILINE),
}


def extract_section(body: str, key: str) -> str | None:
    m = SECTION_RE[key].search(body)
    return m.group(1).strip() if m else None


def marp_wrap(title: str, chapter_label: str, takeaways: str | None, slides_source: str | None) -> str:
    header = f"""---
marp: true
theme: default
paginate: true
header: "{chapter_label}"
footer: "Generated by Claude Code"
style: |
  section {{ font-size: 24px; }}
  h1 {{ font-size: 36px; color: #1a5276; }}
  h2 {{ font-size: 30px; color: #2c3e50; }}
  li {{ font-size: 22px; line-height: 1.6; }}
---

# {title}
### {chapter_label}

---

"""
    body = header
    if takeaways:
        # Each bullet may be a long paragraph; auto-paginate at BULLETS_PER_SLIDE
        # to avoid Campbell-Ch01-style 17-bullet-on-one-slide overflow.
        BULLETS_PER_SLIDE = 4
        bullets = [b for b in takeaways.split("\n") if b.strip().startswith("-")]
        n = len(bullets)
        if n == 0:
            pass
        else:
            pages = [bullets[i:i + BULLETS_PER_SLIDE] for i in range(0, n, BULLETS_PER_SLIDE)]
            total = len(pages)
            body += "# KEY TAKEAWAYS\n\n---\n\n"
            for i, page in enumerate(pages, 1):
                body += f"## Key Takeaways ({i}/{total})\n" + "\n".join(page) + "\n\n---\n\n"
    if slides_source:
        # Auto-inject Marp page-break before each level-2 heading. Note authors
        # use `## NN section-name` headings but often forget `---` separators —
        # without them Marp renders 15 sections on a single slide. Idempotent:
        # if --- already present, the regex won't double up.
        fixed = re.sub(r'(?<!\n---\n)\n(## [^\n#])', r'\n\n---\n\n\1', slides_source)
        body += fixed.rstrip() + "\n"
    return body


def _safe_rel(p: Path) -> str:
    """Display path relative to VAULT if possible, else relative to HOME, else absolute."""
    try:
        return str(p.relative_to(VAULT))
    except ValueError:
        try:
            return "~/" + str(p.relative_to(Path.home()))
        except ValueError:
            return str(p)


def write_if_changed(dest: Path, content: str, dry: bool, verbose: bool) -> bool:
    if dest.exists() and dest.read_text() == content:
        return False
    if verbose:
        action = "would write" if dry else "write"
        print(f"  {action}: {_safe_rel(dest)}")
    if not dry:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content)
    return True


def sync_note(note_path: Path, fm: dict, body: str, dry: bool, verbose: bool) -> dict:
    target_name = fm.get("publish_to")
    if target_name not in ALLOWED_TARGETS:
        return {"error": f"unknown publish_to={target_name}"}
    target_root = ALLOWED_TARGETS[target_name]
    book_slug, chapter_slug = book_and_chapter(note_path)
    now = datetime.datetime.now().isoformat(timespec="seconds")
    rel_note = str(_safe_rel(note_path))
    sync_fm = {"_synced_from": rel_note, "_synced_at": now}

    takeaways = extract_section(body, "KEY_TAKEAWAYS")
    slides = extract_section(body, "TEACHING_SLIDES")
    title = fm.get("title", chapter_slug)
    chapter_label = f"{book_slug} — {chapter_slug}"
    written = []

    if target_name == "textbook-notes":
        if takeaways:
            kt_fm = {**sync_fm, "title": title, "book": book_slug, "chapter": chapter_slug}
            kt_out = build_frontmatter(kt_fm) + f"\n# {title}\n\n## KEY TAKEAWAYS\n\n{takeaways}\n"
            p = target_root / "takeaways" / book_slug / f"{chapter_slug}.md"
            if write_if_changed(p, kt_out, dry, verbose):
                written.append(str(_safe_rel(p)))
        if slides:
            slide_md = marp_wrap(title, chapter_label, takeaways, slides)
            p = target_root / "slides" / book_slug / f"{chapter_slug}.md"
            if write_if_changed(p, slide_md, dry, verbose):
                written.append(str(_safe_rel(p)))
    elif target_name == "nephro-cme":
        # Full note body for nephro-cme/note/
        full_fm = {**sync_fm, **{k: v for k, v in fm.items() if k not in {"publish", "publish_to"}}}
        full_out = build_frontmatter(full_fm) + body
        p = target_root / "note" / f"{chapter_slug}.md"
        if write_if_changed(p, full_out, dry, verbose):
            written.append(str(_safe_rel(p)))
        if slides:
            slide_md = marp_wrap(title, chapter_label, takeaways, slides)
            p = target_root / "slides" / book_slug / f"{chapter_slug}.md"
            if write_if_changed(p, slide_md, dry, verbose):
                written.append(str(_safe_rel(p)))

    return {"written": written, "target": target_name, "book": book_slug, "chapter": chapter_slug}


def sweep_orphans(active_mapping: dict[str, str], dry: bool, verbose: bool) -> list[str]:
    """Remove files in target repos that were previously synced but note no longer has publish=true.

    active_mapping: {target_repo_relpath: source_note_relpath}
    """
    removed = []
    for name, root in ALLOWED_TARGETS.items():
        for sub in ("takeaways", "slides", "note"):
            d = root / sub
            if not d.exists():
                continue
            for f in d.rglob("*.md"):
                try:
                    txt = f.read_text()
                except OSError:
                    continue
                fm, _ = parse_frontmatter(txt)
                if not fm or "_synced_from" not in fm:
                    continue  # human-authored, skip
                rel_target = _safe_rel(f)
                if rel_target not in active_mapping:
                    if verbose:
                        action = "would remove" if dry else "remove"
                        print(f"  {action} orphan: {rel_target}")
                    if not dry:
                        f.unlink()
                    removed.append(rel_target)
    return removed


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--verbose", "-v", action="store_true")
    args = p.parse_args()

    candidates: list[Path] = []
    for root in SCAN_ROOTS:
        if not root.exists():
            continue
        candidates.extend(root.rglob("*.md"))

    total = 0
    published = 0
    errors = 0
    active_mapping: dict[str, str] = {}
    written_count = 0

    for note_path in candidates:
        # Skip sidecar raw.md, skip archives
        parts = note_path.parts
        if "_archive" in parts or "raw.md" == note_path.name:
            continue
        try:
            txt = note_path.read_text()
        except OSError:
            continue
        fm, body = parse_frontmatter(txt)
        if not fm:
            continue
        total += 1
        if fm.get("publish") is not True:
            continue
        published += 1
        result = sync_note(note_path, fm, body, args.dry_run, args.verbose)
        if "error" in result:
            errors += 1
            print(f"ERR {_safe_rel(note_path)}: {result['error']}", file=sys.stderr)
            continue
        written_count += len(result.get("written", []))
        target_root = ALLOWED_TARGETS[result["target"]]
        # Register expected target paths for orphan sweep
        if result["target"] == "textbook-notes":
            active_mapping[_safe_rel(target_root / "takeaways" / result["book"] / f"{result['chapter']}.md")] = _safe_rel(note_path)
            active_mapping[_safe_rel(target_root / "slides" / result["book"] / f"{result['chapter']}.md")] = _safe_rel(note_path)
        elif result["target"] == "nephro-cme":
            active_mapping[_safe_rel(target_root / "note" / f"{result['chapter']}.md")] = _safe_rel(note_path)
            active_mapping[_safe_rel(target_root / "slides" / result["book"] / f"{result['chapter']}.md")] = _safe_rel(note_path)

    removed = sweep_orphans(active_mapping, args.dry_run, args.verbose)

    print(f"textbook-share-sync: scanned={total} published={published} wrote={written_count} removed={len(removed)} errors={errors}{' [dry-run]' if args.dry_run else ''}")
    return 0 if errors == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
