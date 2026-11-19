<p align="center">
  <picture>
    <source media="(prefers-color-scheme: light)" srcset="docs/assets/banner-light.svg">
    <img alt="SANITY. Check the math before you trust it." src="docs/assets/banner.svg" width="1200">
  </picture>
</p>

<p align="center">
  <a href="#quickstart"><img alt="tests" src="https://img.shields.io/badge/tests-pytest-6e675f?style=flat-square"></a>
  <a href="LICENSE"><img alt="MIT license" src="https://img.shields.io/github/license/IlkhamFY/sanity?style=flat-square&color=6e675f"></a>
  <a href="https://ilkhamfy.github.io/sanity/"><img alt="live site" src="https://img.shields.io/badge/site-live-6e675f?style=flat-square"></a>
  <a href="https://ilkhamfy.github.io/sanity/demo.html"><img alt="demo" src="https://img.shields.io/badge/demo-live-6e675f?style=flat-square"></a>
  <a href="https://ilkhamfy.github.io/sanity/papers.html"><img alt="Checked papers" src="https://img.shields.io/badge/Checked%20papers-live-6e675f?style=flat-square"></a>
</p>

Sanity checks the equations in a paper.

A Reader lifts each displayed equation. A Verifier re-derives it in SymPy, and can add a Lean proof when the claim can be stated. A Writer turns those script verdicts into a report.

A verdict exists only if a check script printed it: `HOLDS`, `FAILS`, or `UNCHECKED`. The Writer does not change one.

The three bots share one Telegram group and talk to each other there. Bot-to-Bot Communication Mode is on, so a bot sees the others' messages. Each machine message starts with `sanity run=<slug>` and names who should act with `to=<role>` (`to=reader`, `to=verifier`, `to=writer`).

The Verifier posts a plan and a time estimate at the start of a run, before any check. It then sends one handoff `to=writer` when the verdicts are in. Files travel as Telegram attachments. Each bot keeps its own working copies.

The whole message protocol is the shared skill [skills/sanity-protocol/SKILL.md](skills/sanity-protocol/SKILL.md). See also [agents/verifier/AGENT.md](agents/verifier/AGENT.md) and [docs/setup-verifier-docker.md](docs/setup-verifier-docker.md).

## Built with

<p align="center">
  <a href="https://www.python.org/"><picture><source media="(prefers-color-scheme: dark)" srcset="docs/assets/logos/python-dark.svg"><img alt="Python" height="32" src="docs/assets/logos/python-light.svg"></picture></a>
  &nbsp;&nbsp;
  <a href="https://www.sympy.org/"><picture><source media="(prefers-color-scheme: dark)" srcset="docs/assets/logos/sympy-dark.svg"><img alt="SymPy" height="32" src="docs/assets/logos/sympy-light.svg"></picture></a>
  &nbsp;&nbsp;
  <a href="https://lean-lang.org/"><picture><source media="(prefers-color-scheme: dark)" srcset="docs/assets/logos/lean-dark.svg"><img alt="Lean 4" height="32" src="docs/assets/logos/lean-light.svg"></picture></a>
  &nbsp;&nbsp;
  <a href="https://telegram.org/"><picture><source media="(prefers-color-scheme: dark)" srcset="docs/assets/logos/telegram-dark.svg"><img alt="Telegram" height="32" src="docs/assets/logos/telegram-light.svg"></picture></a>
  &nbsp;&nbsp;
  <a href="https://hermes-agent.nousresearch.com/"><picture><source media="(prefers-color-scheme: dark)" srcset="docs/assets/logos/hermes-dark.svg"><img alt="Hermes Agent" height="32" src="docs/assets/logos/hermes-light.svg"></picture></a>
  &nbsp;&nbsp;
  <a href="https://www.docker.com/"><picture><source media="(prefers-color-scheme: dark)" srcset="docs/assets/logos/docker-dark.svg"><img alt="Docker" height="32" src="docs/assets/logos/docker-light.svg"></picture></a>
  &nbsp;&nbsp;
  <a href="https://vite.dev/"><picture><source media="(prefers-color-scheme: dark)" srcset="docs/assets/logos/vite-dark.svg"><img alt="Vite" height="32" src="docs/assets/logos/vite-light.svg"></picture></a>
  &nbsp;&nbsp;
  <a href="https://katex.org/"><picture><source media="(prefers-color-scheme: dark)" srcset="docs/assets/logos/katex-dark.svg"><img alt="KaTeX" height="32" src="docs/assets/logos/katex-light.svg"></picture></a>
  &nbsp;&nbsp;
  <a href="https://www.latex-project.org/"><picture><source media="(prefers-color-scheme: dark)" srcset="docs/assets/logos/latex-dark.svg"><img alt="LaTeX" height="32" src="docs/assets/logos/latex-light.svg"></picture></a>
  &nbsp;&nbsp;
  <a href=".github/workflows/pages.yml"><picture><source media="(prefers-color-scheme: dark)" srcset="docs/assets/logos/github-dark.svg"><img alt="GitHub Actions and GitHub Pages" height="32" src="docs/assets/logos/github-light.svg"></picture></a>
</p>

## Architecture

```mermaid
flowchart LR
  paper["Paper"] --> reader["Reader"] --> verifier["SymPy + Lean"] --> writer["Writer"] --> publish["publish_run.py"] --> papers["papers.html"]
  reader --- group["Telegram group"]
  verifier --- group
  writer --- group
```

<p align="center">
  <img src="docs/assets/handoff.gif" alt="A message moves from Reader to Verifier to Writer. A bar fills, then reads FAILS." width="720">
</p>

The group is the handoff. Every message names its target with `to=<role>`, and files travel as attachments. A status line has no `to=`, so it wakes no bot. The Reader sends `equations.json`. The Verifier sends `verdicts.json` and the evidence bundle. SymPy checks a claim exactly, by asymptotics, or by sampling. Lean is extra evidence for a few central exact claims, always after SymPy, and only when the claim can be stated. A Lean `proof` or `refutation` outranks a SymPy result for the same claim. The Verifier may ask the Reader a question. The Writer does not get a vote on the verdict.

The square in the picture is a message on that group. The bar is a verdict. A verdict counts only if a check script printed it. `publish_run.py` writes the run back to the live index, <https://ilkhamfy.github.io/sanity/papers.html>.

## Eq. (4.4)

On [arXiv:2410.11128v1](https://arxiv.org/abs/2410.11128v1), Eq. (4.4) prints the wrong horizon angular velocity. Sanity flags it and proposes the same replacement the authors later recorded. The run is [runs/arxiv-2410-11128/](runs/arxiv-2410-11128/). The page is <https://ilkhamfy.github.io/sanity/demo.html>.

<p align="center">
  <img src="docs/assets/demo-eq44.png" alt="Demo page for arXiv:2410.11128v1. Equation (4.4) is marked FAILS, with the corrected angular velocity." width="880">
</p>

Printed in v1:

$$\Omega=\frac{c r_{+}}{a(r_{+}+r_{-})}$$

Corrected:

$$\Omega=\frac{c r_{-}}{a(r_{+}+r_{-})}$$

At $r_{+}=2$, $r_{-}=1$, $a=\sqrt{2}$, $c=1$ the printed value is $\sqrt{2}/3$ and the horizon value is $\sqrt{2}/6$. The ratio is $r_{+}/r_{-}$. The two agree only when $r_{+}=r_{-}$.

The corrected clause was checked on its own. It holds.

```text
simplify(corrected - c*a/(r_plus**2+a**2)) == 0 for a**2=r_plus*r_minus
```

`runs/example-oscillator/` is a toy note with two planted errors. The front page plays that note.

## Self-evolving

[`scripts/publish_run.py`](scripts/publish_run.py) publishes each new run on the live papers index, <https://ilkhamfy.github.io/sanity/papers.html>. It copies `equations.json`, `verdicts.json`, and any `REPORT.md` or `report.html`, updates that paper's row, and appends to `activity.json`. Running it again updates the same row. Verdicts still come only from check scripts.

## Roles

| Agent | Produces (sent in the group) | Does not |
| --- | --- | --- |
| Reader | `equations.json`, to the Verifier | check, judge, or edit the paper |
| Verifier | `verdicts.json` and an evidence bundle (checks, `PLAN.md`, `RESULTS.md`), to the Writer | open the paper, edit the extraction, or write the report |
| Writer | `REPORT.md` and its summary, to the group (`status=done`) | change a verdict, or check the math itself |

Role prompts: `agents/reader/AGENT.md`, `agents/verifier/AGENT.md`, `agents/writer/AGENT.md`. The Writer prompt also asks for `RESULT.html`, built from `REPORT.md` and `telegram.md`.

## Repository

```
site/      front page, the paper check at demo.html, and the index at papers.html
brand/     logo, mark, favicon
agents/    reader, verifier (SymPy + Lean), writer
docs/      Telegram, handoff, setup, schemas
hermes/    example profile per role, no tokens
runs/      worked examples, used by the tests
scripts/   publish_run, configure_bot, setup_verifier_docker, setup_bot
skills/    verify-math, sanity-protocol
```

## Quickstart

Node.js 22 is enough for the site. Python 3 is enough for the checks. A ten-minute checklist for each person, including the bot assignment, is [docs/setup.md](docs/setup.md).

```bash
cd site
npm install
npm run dev
```

The dev server listens on port 4317. Open [http://127.0.0.1:4317](http://127.0.0.1:4317).

```bash
cd site
npm run build
```

`npm run build` writes a static site to `site/dist`. `npm run preview` serves that build, also on port 4317. The Vite `base` is `./`, for GitHub Pages.

A finished run becomes a row on the public index. The command copies `equations.json`, `verdicts.json`, and any `REPORT.md` or `report.html` into `site/public/data/<slug>/`, then updates `papers.json`:

```bash
python3 scripts/publish_run.py runs/<slug> --subject "Physics"
```

While the bots are still working, one line is enough: `python3 scripts/publish_run.py --event --slug <slug> --role verifier --message "Eq. (4.4) FAILS"`. The index is live at <https://ilkhamfy.github.io/sanity/papers.html> ([site/papers.html](site/papers.html)).

From the repository root, install the Verifier's dependencies and run the tests:

```bash
python3 -m pip install -r agents/verifier/requirements.txt
python3 -m pytest agents/verifier agents/writer scripts
```

Or print the two planted flags:

```bash
python3 agents/verifier/check_step.py
```

Saved checks for the specimen live in `runs/example-oscillator/verify/checks/`, one script per equation. The model may draft a script. A verdict counts only if that script printed it.

```bash
python3 agents/verifier/verify_run.py runs/example-oscillator/verify
```

The specimen includes the two planted errors, so this command exits 1. It writes `RESULTS.md` and `verdicts.json`, which the Writer reads. The procedure for the Verifier is [skills/verify-math/SKILL.md](skills/verify-math/SKILL.md). The Writer's report for this note is [runs/example-oscillator/REPORT.md](runs/example-oscillator/REPORT.md).

The Kerr run fails the same way, on Eq. (4.4):

```bash
python3 agents/verifier/verify_run.py runs/arxiv-2410-11128/verify
```

To set up your own bot, from the repo root, with `HERMES_PROFILE_DIR` pointed at the profile path you want:

```bash
HERMES_PROFILE_DIR="$HOME/.hermes/profiles/sanity-reader" bash scripts/setup_bot.sh reader
```

Use `verifier` or `writer` for the other roles. Windows: `scripts/setup_bot.ps1`. The script clones or pulls, creates a venv, installs the requirements, and copies `hermes/<role>/` plus the role's `AGENT.md`. It then prints the remaining BotFather steps. Details: [docs/setup.md](docs/setup.md).

## How to add your bot

1. Create one bot with [@BotFather](https://t.me/BotFather). One token, one role.
2. `/setprivacy` → Disable, and switch on Bot-to-Bot Communication Mode. Remove the bot from the group and add it again.
3. Lock it to the three teammates' Telegram user IDs, the two other bots and the group. Placeholders live in `hermes/<role>/env.example`. Do not commit a token.
4. Run `scripts/setup_bot.sh` or `scripts/setup_bot.ps1` for that role. It copies the example profile and installs `agents/<role>/AGENT.md` as `SOUL.md`. The profile loads `skills/verify-math` and `skills/sanity-protocol`.
5. Replace `${SANITY_REPO}` and the model placeholders in the copied `config.yaml`.
6. Start that profile's gateway. In the group, a person talks to the bot, or another bot sends `sanity run=<slug> to=<role>`. The Verifier answers with the plan and the estimate, then checks.

### Configure your bot for the protocol

After the steps above, one command sets everything the bots need to talk to each other: the role's persona, the shared protocol skill [skills/sanity-protocol/SKILL.md](skills/sanity-protocol/SKILL.md), the `to=<role>` wake word, mention-only, the group target, the loop guard, and who may approve commands. Run it from an up-to-date clone, with the Telegram IDs of the three people:

```bash
git pull
APPROVERS=<id>,<id>,<id> bash scripts/configure_bot.sh reader     # or writer, verifier
```

Hermes in Docker: add `HERMES_CONTAINER=<name> SANITY_REPO=<repo path inside the container>`. A Hermes profile: add `HERMES_PROFILE=<name>`. `KEEP_SOUL=1` keeps your own persona. The script backs up `SOUL.md`, `config.yaml` and `.env`, restarts the gateway, and ends with a check. The Verifier in Docker uses `bash scripts/setup_verifier_docker.sh install`, then `APPROVERS=<id>,<id>,<id> bash scripts/setup_verifier_docker.sh configure`, which runs the same script ([docs/setup-verifier-docker.md](docs/setup-verifier-docker.md)).

Two steps stay manual: in @BotFather, switch on Bot-to-Bot Communication Mode for the bot, and list the three people, the two other bots and the group in `TELEGRAM_ALLOWED_USERS`. To see what is still missing, without changing anything:

```bash
bash scripts/configure_bot.sh check reader     # or writer, verifier
```

Group setup: [docs/telegram.md](docs/telegram.md). The Verifier's messages: [agents/verifier/AGENT.md](agents/verifier/AGENT.md).

## Lean specimen

`agents/verifier/lean` is a prelude-only Lean 4 package: one theorem, no Mathlib. With [elan](https://github.com/leanprover/elan) installed:

```bash
cd agents/verifier/lean
lake build
```

Notes: [agents/verifier/lean/NOTES.md](agents/verifier/lean/NOTES.md). Do not build Mathlib in CI.

## Acknowledgements

The Verifier's rule that a verdict exists only if an executed script printed it, the original verdict names (`VERIFIED`, `VERIFIED-NUMERICALLY`, `FAILED`, `UNCHECKED`, now replaced by `HOLDS`/`FAILS`/`UNCHECKED` plus an evidence kind), and the runner that writes `RESULTS.md` are adapted from claude-mathematician by Konstantin Gerbig (MIT, copyright 2026 Konstantin Gerbig). See [agents/verifier/NOTICE](agents/verifier/NOTICE). Sanity adds Lean and `verdicts.json`, and does not use Mathematica.

## License

[MIT](LICENSE).
