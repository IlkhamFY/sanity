# Handoff

Telegram bots in a group do not receive each other's messages. The git repo is the bus. A bot learns that the previous one finished by pulling `runs/<paper-slug>/`.

## Files

```
runs/<paper-slug>/
  equations.json     Reader
  status.json        the bot that owns the current stage
  note.tex           optional source the Reader extracted (the specimen has one)
  verify/            Verifier only
    checks/
    PLAN.md
    RESULTS.md
  REPORT.md          Writer
  telegram.md        Writer
```

`equations.json` matches [docs/schemas/equations.schema.json](schemas/equations.schema.json). `status.json` matches [docs/schemas/status.schema.json](schemas/status.schema.json).

`status.json` fields:

| Field | Meaning |
| --- | --- |
| `paper` | Slug, same as the directory name. |
| `stage` | `reader`, `verifier`, `writer`, or `done`. |
| `owner_bot` | Role or bot name that may write now. |
| `updated_at` | When this status was written. |
| `commit` | Commit being published with this status. |
| `notes` | One line for the next bot. Not a verdict. |

## Who writes what

Only the stage owner writes its files.

| Stage | May write | Then sets stage to |
| --- | --- | --- |
| `reader` | `equations.json`, `status.json` | `verifier` |
| `verifier` | `verify/**`, `status.json` | `writer` |
| `writer` | `REPORT.md`, `telegram.md`, `status.json` | `done` |
| `done` | nobody, until a person sets a stage back | |

The Verifier does not edit `equations.json` or the report. The Writer does not edit `verify/` and does not change a verdict. The Reader does not check math.

## What each bot does

1. `git pull`.
2. Read `runs/<paper-slug>/status.json`. If `stage` is not this bot's role, stop. Do not "help" with another stage.
3. Do the work in the files that role owns.
4. Update `status.json` to the next stage, with `owner_bot`, `updated_at`, `commit`, and a short `notes` string.
5. Commit and push.
6. Post one line in the group.

The line names the next bot and the run:

```
@<next-bot> runs/<paper-slug> ready
```

The Reader mentions the Verifier. The Verifier mentions the Writer. The Writer has no next bot, and posts:

```
runs/<paper-slug> ready
```

Humans steer by @mentioning the bot that should act. That mention is the trigger. Bots still pull and push the repo; they do not read each other's chat.

## Optional poller

`scripts/watch_runs.py` pulls on an interval and prints runs whose `stage` matches a role. It does not write, commit, or post. Use it if a bot should notice a handoff without a fresh mention. The mention stays the main trigger.

```bash
python3 scripts/watch_runs.py --role verifier --interval 15
python3 scripts/watch_runs.py --role reader --once --no-pull
```

The worked example is [runs/example-oscillator/](../runs/example-oscillator/). Its stage is `done`.
