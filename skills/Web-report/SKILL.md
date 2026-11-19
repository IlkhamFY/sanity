---
name: Web-report
description: Build report.html, the single-file web view of a Sanity run. Use when the Writer publishes a checked paper as a page.
---

# Writer: final report as a website

After REPORT.md is done, build `report.html`. It is the face of the run.
One person opens it on a projector or a phone and gets the verdict in 2 seconds,
then can drill into any equation. Simplicity first: one page, one idea per block.

## Hard rules
- One self-contained file, `report.html`. Inline all CSS and JS. No build step.
  Allowed CDNs only: KaTeX (css + js) and Google Fonts (Schibsted Grotesk, IBM Plex Mono).
- Embed the data: put `equations.json` and `verdicts.json` verbatim inside
  `<script type="application/json" id="equations">` and `id="verdicts"`. Render from them with JS.
- Every number, value, claim, line number and correction on the page comes from those two files.
  Never invent a counterexample, a correction, a line number or a count. If a field is missing, leave that part out.
- Logos: use only SVGs that exist on disk (for example `site/public/logos/`), inlined. If none exist, use mono text
  badges (SymPy, Python, Lean 4). Never draw or guess a logo.
- UNCHECKED is shown as UNCHECKED. Never soften FAILS or upgrade UNCHECKED.
- Verdict is never shown by colour alone. Always also the word (HOLDS / FAILS / UNCHECKED / ERROR).
- No external search. Base everything on the two files, like REPORT.md.
- No em dashes in REPORT.md, telegram.md or the page. Use short sentences.

## Summary and judgement wording
- Name only equations whose verdict is FAILS in the summary and the judgement. Build that list from verdicts.json
  (`[c.claim for c in claims if c.verdict == "FAILS"]`), never from prose. A HOLDS equation with a caveat is not named there.
- The judgement is one sentence. It goes into telegram.md and the masthead, and must match the list.

## Design (copy the main Sanity site exactly)
```css
:root{
  --bg:#12263a; --ink:#f3efe6; --muted:#d5cec2; --faint:#b7ad9e;
  --line:rgba(243,239,230,.22);
  --holds:#8fa87a; --fails:#c47a6a; --unchecked:var(--faint); --error:#c9a46a;
  --sans:"Schibsted Grotesk","Avenir Next","Segoe UI",sans-serif;
  --mono:"IBM Plex Mono",ui-monospace,monospace;
}
body{background:var(--bg);color:var(--ink);font:1.125rem/1.5 var(--sans)}
```
- Background: the faint 96px grid of the main site
  (`linear-gradient(rgba(243,239,230,.045) 1px,transparent 1px)` both directions, `background-size:96px 96px`).
- Labels, tags, counts: `var(--mono)`, 0.78rem, uppercase, letter-spacing .06em, colour `--faint`.
- Content width `min(68rem, calc(100% - 2rem))`, centred. Thin 1px `--line` rules between sections.
- Verdict rows: 3px left border in the verdict colour, background = that colour at 10% alpha.
  ERROR uses a dashed border. UNCHECKED has no tint, only the faint border.
- No gradients, glow, neon, emoji, shadows, cards-in-cards or decorative icons.

## KaTeX
- Render with `katex.render(s, el, {displayMode: true, throwOnError: false, macros: MACROS})`.
- Macros needed for the Sanity equation files: `{"\\dd": "\\mathrm{d}", "\\kB": "k_{\\mathrm{B}}"}`. Add any other
  unknown macro the same way.
- Check each rendered row. KaTeX puts TeX source in MathML `<annotation>`, so read the visible text from
  `.katex-html`, not from the whole element. If it still shows a backslash, or the element has `.katex-error`,
  show the raw LaTeX in mono instead and mark the row `data-fallback="1"`. Report the fallback count.
- Render SymPy residuals as KaTeX too. Example: `difference theta**6/2880` becomes `\Delta = \theta_0^6/2880`.
  Do not show raw `**`.

## Highlighting the change (the catch and expanded FAILS rows)
- Show two lines: `WHAT WE FOUND` (printed equation) and `SHOULD READ` (correction). Use the same left side and the
  same middle term, so the change is the only thing that differs.
- Diff the two strings on LaTeX atoms, not characters: a command with its following `{...}` groups is one atom.
  Wrap only differing runs: `\textcolor{#c47a6a}{...}` in FAILS, `\textcolor{#8fa87a}{...}` in should read.
  Skip a run whose braces do not balance, and say so.

## Page, top to bottom
1. **Masthead.** Small mono label `SANITY · RUN <slug> · ATTEMPT <n>`. Paper title as h1 (from equations.json `title`).
   Source line: the source file name from `source` (and an arXiv id only if the data has one).
   Date from `generated_at`, code commit from the handoff header.
   Three bot chips: `Reader: N equations lifted`, `Verifier: N checks, H hold, F fail`, `Writer: wrote this page`.
   Then the one-sentence judgement in `--muted`, max 38em.
2. **Score line and bar.** One mono line: `12 claims · 8 holds · 4 fails · 0 unchecked`.
   Under it, a thin segmented bar (10px high), one segment per claim, in paper order, coloured by verdict.
   Each segment links to its row and opens it. Hover (`title`) shows `(n) VERDICT`. On load the segments fill left
   to right, 40ms apart.
   Directly under the bar, a legend: holds `proof > symbolic > asymptotic > numerical`, fails
   `refutation > symbolic > asymptotic > counterexample`, each with its tool badge.
3. **The catch** (only if any claim FAILS). Pick the FAILS claim whose failure matters most, and say why in one plain
   sentence built from the verdict detail (for example: the bound points the wrong way, so the paper's inequality is
   reversed). Big, centred, lots of space: `WHAT WE FOUND`, `SHOULD READ` (highlighted as above), then the why sentence.
4. **The paper, checked.** Rows in paper order, or failures first when the reader toggles the sort (two buttons,
   `aria-pressed`). Each row: `(n)` in mono, verdict word and evidence kind (`FAILS · counterexample`), a tool badge
   (SymPy, Python, Lean 4), the rendered equation, and a `copy link` button that copies `#eq-n`.
   - FAILS rows open by default. HOLDS and UNCHECKED rows start collapsed. Click or Enter toggles; `aria-expanded` is set.
   - Expanded row shows: check ID, script name (from the data, never invented), source line (`line` from
     equations.json), the residual or counterexample values in mono, and for FAILS the correction and its check.
   - Rows are 44px+ tall and keyboard reachable.
5. **How it was checked.** One line per agent, real counts from the files only:
   `Reader  lifted N equations` · `Verifier  ran H holding and F failing checks (SymPy, Python, Lean 4)` ·
   `Writer  wrote this page and changed no verdict`.
6. **Footer.** `The LLM proposes. The math decides.` Then `Verdicts come only from check scripts. The Writer does not
   change one.` Then, in mono and faint, the sha256 of equations.json and verdicts.json (from the handoff header),
   and the link https://ilkhamfy.github.io/sanity/.

## Must work
- 1280px desktop: masthead, score line and the catch fit on the first screen.
- 375px phone: one column; long equations scroll inside their row only; no page-level horizontal scroll.
- Print (Ctrl+P): white background, black text, verdict words kept (not colour alone), all rows expanded.
- Opens straight from the Telegram file with no server.

## Before sending, check
- [ ] Counts on the page equal counts in verdicts.json (claims and checks, separately).
- [ ] Summary and judgement name only the FAILS equations, from verdicts.json.
- [ ] Rendering check: 0 `.katex-error`, and the fallback count is reported.
- [ ] No text, number or claim that is not in the two files.
- [ ] No em dashes in REPORT.md, telegram.md or the page.
- [ ] Opened at 375px and 1280px wide (or say which were not checked).

## Send
Step 6: post the one-sentence judgement (telegram.md) to the group.
Step 8: post `REPORT.md` and `report.html` to the group as attachments (`MEDIA:<absolute path>`).
Then one message to the publisher, the header as the caption of a single `.zip` (a caption rides on one file only):

```
sanity run=<slug> to=publisher stage=publish
```

The zip contains `equations.json`, `verdicts.json`, `report.html`, `meta.json`, and the check scripts under `verify/checks/`. Summary and catch name only FAILS equations. You do not commit or push. Only the publisher touches GitHub. The LLM bots never hold GitHub credentials.
A send that returns exit 0 is not proof the message arrived: say so, and ask the operator to check.
