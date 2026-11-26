# EDGE design system — where it lives and how to change it

- **Source (this folder):** read by every Claude Code session that opens this repository (`SKILL.md` is the entry).
- **claude.ai copy:** the Design System artifact **https://claude.ai/artifact/SQwji2RLWXAf8ZKEcfcNww** (private to the
  owner until shared from its Share menu). Any claude.ai chat or session of the account can read it as a reference
  ("use the EDGE Design System"). It is built from this folder by `tools/build_artifact.py`; never edit it on its own.

## Decisions it encodes (user, 2026-11-18; `EXEC.md` EXEC-DESIGN-SYSTEM)
"C" (both places), then "v1.2, contoh pola disesuaikan token, 11 usulan setuju, go": spec v1.2 is the base, the 11
canonical choices of `SKILL.md`, and the user's design proposals taken as patterns adapted to the tokens.

## Where it came from
- `assets/spec-v1.2.css`: EDGE Design Spec v1.2, verbatim (`edge-design-spec-type-A.css` given by the user 2026-11-17).
- `assets/edge-canonical.css`: the Overview/Radar state layer (`apps/edge-bff/overview/src/styles/overview.css`, the
  "State layer" block), the Watchlist underline tabs (`watchlist.css`, `.bar1 .tabs`), the Overview KPI tile and
  tooltips, and the patterns of the proposals (`edge-homepage-cards_3.html`, `right-panel-candidates_screener_dan_backtest.html`,
  `1_2.html` Foreign × Domestic window, `2_2.html` Verdict change drivers, `flow_day_count_options.html`).
- `assets/edge-ds.js`: the formatters of `apps/edge-bff/overview/src/model.ts` and the chart helpers of
  `overview/src/app.ts` and `watchlist/src/model.ts`.
- `assets/icons.svg`: the sprite of `apps/edge-bff/overview/index.html`.
- The full as-is capture of every page (offline pages, screenshots, per-chart and per-component inventories,
  literal values outside the spec) is the "EDGE Reference Pack" of 2026-11-17, kept outside Git (it holds market data).

## Changing it
1. Get the user's approval when a change alters how pages look (a token value, a canonical choice).
2. Edit this folder (`assets/`, `reference/`, `SKILL.md`); open `assets/showcase.html` at 1440 and 390 px, light and
   `?theme=dark`: no console error, no sideways scroll.
   A page may hold `assets/*.css` as it is (the Admin page, `apps/edge-bff/admin/src/styles/`, checked by
   `apps/edge-bff/admin/tests/styles.test.mjs`): find every such copy by its name,
   `find apps -path '*/node_modules' -prune -o -path '*/dist*' -prune -o \( -name spec-v1.2.css -o -name edge-canonical.css \) -print`,
   copy the change into each in the same commit (its leading usage note stays) and run that page's tests (ERRORS M571).
   The Overview, Watchlist and Radar carry spec v1.2 inside their own CSS (`grep -rl "Design Spec v1  (sumber" apps`):
   a change of `spec-v1.2.css` is weighed there too, with the user's approval when it changes their look.
3. Rebuild the claude.ai copy: `python3 .claude/skills/edge-design-system/tools/build_artifact.py <dir>`, then publish
   `<dir>/project/…` to the artifact url (Artifact tool, `root` = `<dir>`, `file_path` = `project/design-system.json`,
   the rest in `files`; `components/index.d.ts` as `text/plain`). Read the artifact first if someone edited it there.
4. Record the change in `EXEC.md` (EXEC-DESIGN-SYSTEM) with the user's words.
