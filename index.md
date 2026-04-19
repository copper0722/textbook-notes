---
marp: false
---

# Textbook Teaching Slides

## Scope (2026-04-19 rescope)

**Non-nephrology** textbook teaching slides. Nephrology slides (Brenner, Daugirdas, Nissenson, Henrich, Pediatric Nephrology) have moved to [`copper0722/nephro-cme`](https://github.com/copper0722/nephro-cme) (now centralizes all nephrology teaching: `/note/`, `/slides/`, `/cme/`, `/nephrology-cme-wiki/`).

## Current corpus

Empty. Awaiting first non-nephrology textbook content (e.g. Mankiw Economics, Netter Anatomy, GraysAnatomy, MolBioCell, Wash Manual internal medicine chapters).

## Moved content (30-day redirect stubs in `slides/`, retire 2026-05-19)

### Daugirdas 6e — moved to nephro-cme

All 39 Daugirdas 6e chapter slides now live at [`nephro-cme/slides/daugirdas/`](https://github.com/copper0722/nephro-cme/tree/main/slides/daugirdas). GitHub Pages: `copper0722.github.io/nephro-cme/slides/daugirdas/{chapter}.html`.

## Generation Pipeline

Driven by `textbook-share-sync.py` (hm4 launchd) reading vault notes with frontmatter:
```yaml
publish: true
publish_to: textbook-notes   # non-nephro only
```

extracts `## KEY TAKEAWAYS` + `## TEACHING SLIDES` sections → writes here.
