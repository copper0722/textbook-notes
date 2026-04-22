---
marp: false
---

# Textbook Teaching Slides

> 📺 **Rendered slides + takeaways** at https://copper0722.github.io/textbook-notes/
> 📝 Source `.md` files at https://github.com/copper0722/textbook-notes/

## Scope (2026-04-19 rescope)

**Non-nephrology** textbook teaching slides. Nephrology slides (Brenner, Daugirdas, Nissenson, Henrich, Pediatric Nephrology) have moved to [`copper0722/nephro-cme`](https://github.com/copper0722/nephro-cme) (centralizes all nephrology teaching: `/note/`, `/slides/`, `/cme/`, `/nephrology-cme-wiki/`).

## Current corpus (updated 2026-04-22)

| book | takeaways (rendered) | slides (rendered) |
|---|---|---|
| **Campbell Biology 13e** | [Ch01 Evolution Themes Scientific Inquiry](takeaways/2026_Campbell_13e/Ch01_Evolution_Themes_Scientific_Inquiry.html) | [Ch01](slides/2026_Campbell_13e/Ch01_Evolution_Themes_Scientific_Inquiry.html) |
| **Harrison 22e (non-nephro chapters)** | [folder](takeaways/2025_Harrison_22e/) | [folder](slides/2025_Harrison_22e/) |

(Source `.md` available in [GitHub repo](https://github.com/copper0722/textbook-notes/tree/main).)

Roadmap (待 vault note publish): Mankiw Economics · Netter Anatomy · Gray's Anatomy · Molecular Biology of the Cell · Wash Manual internal medicine chapters · remaining Harrison 22e non-nephro chapters.

## Moved content (Daugirdas)

All 39 Daugirdas 6e chapter slides live at [`nephro-cme/slides/daugirdas/`](https://github.com/copper0722/nephro-cme/tree/main/slides/daugirdas). GitHub Pages: `copper0722.github.io/nephro-cme/slides/daugirdas/{chapter}.html`.

Previous redirect stubs (planned 2026-04-19 → 2026-05-19 retirement) removed early on 2026-04-22 — repo cleanly scoped to non-nephro from this date.

## Generation Pipeline

Driven by `textbook-share-sync.py` (hm4 launchd hourly :15) reading vault notes with frontmatter:

```yaml
publish: true
publish_to: textbook-notes   # non-nephro only
```

Extracts `## KEY TAKEAWAYS` + `## TEACHING SLIDES` sections → writes here. Previous sync (`brenner-slides-sync.py`) retired 2026-04-19 (hardcoded Brenner+Daugirdas, replaced with frontmatter-driven routing).
