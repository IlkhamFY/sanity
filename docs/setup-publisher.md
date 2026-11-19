# Publisher

The publisher is a daemon, `scripts/publisher.py`. It is not a Hermes bot. It reads the Telegram group, runs `scripts/publish_run.py`, and is the only process that commits. The three LLM bots never hold a GitHub token or a deploy key.

It runs on Ilkham's Windows host, in its own clone, or in a container of its own. Both are below. The LLM bot containers never hold the key. Do not put the daemon or the deploy key in the Reader, Verifier, or Writer containers.

Commits are authored `Ilkham Yabbarov <ilkhamfy@gmail.com>` with message `site`. The push goes to branch `data` and is never a force push. `main` stays the reviewed code branch. Before each commit the daemon merges `origin/main` into `data`, so a code change on `main` reaches the live site on the next publish. Until `data` exists, GitHub Pages still deploys `main`. After `data` exists, Pages deploys `data` only, which keeps a later push to `main` from wiping published papers.

The same zip twice does not make a second commit. A bundle that fails the guard is not committed. The group reply is `published <slug> -> <url>` or the validation error.

## 1. Deploy key

On the machine that will run the daemon:

```bash
ssh-keygen -t ed25519 -f sanity_publisher -C "sanity-publisher" -N ""
```

Windows (PowerShell), if `ssh-keygen` is the OpenSSH client:

```powershell
ssh-keygen -t ed25519 -f "$env:USERPROFILE\.ssh\sanity_publisher" -C "sanity-publisher" -N ""
```

This writes a private key and `sanity_publisher.pub`. Leave the passphrase empty so the daemon can start unattended. `chmod 600` the private key on Linux.

In the repository on GitHub: **Settings → Deploy keys → Add deploy key**. Paste the contents of `sanity_publisher.pub`. Turn on **Allow write access**. Do not commit the private key.

The daemon pushes with:

```text
git push origin HEAD:data
```

`HEAD:data` updates `data` only. The script does not pass `--force`.

## 2. Telegram bot

1. Open [@BotFather](https://t.me/BotFather) and send `/newbot`. One token, used only by this daemon.
2. `/setprivacy` → this bot → **Disable**. Turn on **Bot-to-Bot Communication Mode**, so it can see the Writer.
3. Add the bot to the Sanity group. If it was already in the group when you changed privacy, remove it and add it again. Telegram keeps the old privacy setting until then.
4. Put the token in the environment. Do not commit it.

```bash
export SANITY_PUBLISHER_BOT_TOKEN='the token from BotFather'
export SANITY_DEPLOY_KEY="$HOME/.ssh/sanity_publisher"
```

Windows:

```powershell
$env:SANITY_PUBLISHER_BOT_TOKEN = "the token from BotFather"
$env:SANITY_DEPLOY_KEY = "$env:USERPROFILE\.ssh\sanity_publisher"
```

Those are the two variables. If `SANITY_PUBLISHER_BOT_TOKEN` is unset, the daemon reads the token from the file at `SANITY_PUBLISHER_BOT_TOKEN_FILE` (default `~/.sanity/publisher_token`) and strips whitespace and a leading BOM. Optional: `SANITY_SITE_URL` (default `https://ilkhamfy.github.io/sanity`) and `SANITY_PUBLISHER_STATE` (default `~/.sanity/publisher-state.json`, the seen message ids).

## 3. Run it on the Windows host

From a clean clone of this repo, on branch `main`:

```powershell
cd C:\path\to\sanity
python -m pip install -r agents\verifier\requirements.txt
python scripts\publisher.py
```

`python scripts\publisher.py --dry-run` reads one `getUpdates` batch, validates, and does not commit or send.

Leave the process running. The first publish creates branch `data` from the clone and pushes it.

## 4. Its own container

The other supported place is a container that runs only the publisher. Give that container its own clone and mount the deploy key into it. The environment variables are the same as on the Windows host. The process is `python scripts/publisher.py` in that clone, and `python scripts/publisher.py --dry-run` reads one batch without committing.

Do not start it with `docker exec` inside the `hermes` container, and do not copy the key there. The LLM bot containers never hold the key.

## What the daemon accepts

| Header | What is attached | What happens |
| --- | --- | --- |
| `sanity run=<slug> to=publisher stage=publish` | one `.zip`: `equations.json`, `verdicts.json`, `report.html`, `meta.json`, and the check scripts | validate, `publish_run.py`, commit `site`, push `data` |
| `sanity run=<slug> to=publisher stage=event` | one line, starting with Reader, Verifier, or Writer | append `activity.json` |

`meta.json` comes from `scripts/fetch_paper.py`, for an arXiv id, a DOI, or a pasted file. With no arXiv id and no DOI, `example` is true and the row is filed under Examples. The reply links to `papers.html?paper=<slug>`.
