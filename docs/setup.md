# Setup

About ten minutes for each person. Do this once, then use the group.

The assignment below is **editable**. If a bot moves to someone else, change this table and the `owner_bot` notes you care about. The roles do not move: Reader, then Verifier, then Writer.

| Person | Role | Bot | Profile to create |
| --- | --- | --- | --- |
| Ilkham | Reader | Hermes PI | `sanity-reader` |
| Konstantin | Verifier | HermesAgent | `sanity-verifier` |
| Lloyd | Writer | Lloyd The Hermes | `sanity-writer` |

Fill in the real @username from BotFather next to the bot name when you have it. The handoff line is `@<that-username> runs/<slug> ready`.

## Checklist

Do these in order for your own row.

1. Install [Hermes Agent](https://hermes-agent.nousresearch.com/) and Python 3. Clone this repo, or pull if you already have it.
2. Run the setup script from the repo root. It pulls, creates a virtualenv, installs `agents/verifier/requirements.txt` (SymPy, used by the Verifier's checks), and copies `hermes/<role>/` into the Hermes profile directory.

   macOS or Linux:

   ```bash
   HERMES_PROFILE_DIR="$HOME/.hermes/profiles/sanity-reader" bash scripts/setup_bot.sh reader
   ```

   Windows (PowerShell):

   ```powershell
   $env:HERMES_PROFILE_DIR = "$env:USERPROFILE\.hermes\profiles\sanity-reader"
   .\scripts\setup_bot.ps1 reader
   ```

   Swap `reader` for `verifier` or `writer`, and the profile folder name to match your row. `HERMES_PROFILE_DIR` is a placeholder path: point it at the profile you want Hermes to use.

3. In [@BotFather](https://t.me/BotFather), send `/setprivacy`, choose your bot, and choose **Disable**.
4. Remove the bot from the group and add it again. Privacy mode does not flip for a bot that is already in the group.
5. **Lloyd The Hermes** still shows "has no access to messages". Privacy must be disabled for that bot, then it has to be removed and added again. Check the other two bots for the same line. If the line is still there, privacy is still on.
6. Get each teammate's numeric Telegram user ID (for example from @userinfobot). Put all three IDs in the profile `.env` as `TELEGRAM_ALLOWED_USERS`, comma-separated, and replace the placeholders in the copied `config.yaml`. Do not leave the bot open to every account.
7. Put the BotFather token in the profile environment as `TELEGRAM_BOT_TOKEN`. Do not commit it. A handy name on your machine, matching the role, is `READER_TELEGRAM_TOKEN`, `VERIFIER_TELEGRAM_TOKEN`, or `WRITER_TELEGRAM_TOKEN`.
8. Replace `${SANITY_REPO}` in the copied config with the absolute path of this clone. Copy `agents/<role>/AGENT.md` is already done by the script: it is the profile `SOUL.md`. The verify-math skill is loaded from `skills/` via `skills.external_dirs` and `skills.auto_load`.
9. Start that one profile's gateway. In the group, @mention your bot with a paper slug. It should pull, act only when `stage` matches, push, and post one line. See [docs/handoff.md](handoff.md) and [docs/telegram.md](telegram.md).

The Verifier's machine also needs [elan](https://github.com/leanprover/elan) if a flagged step is going to Lean. Do not build Mathlib in CI. SymPy is enough for the specimen in `runs/example-oscillator/`.

## One shared host (optional)

Use this only if the team wants **one** Lean toolchain. Otherwise each person runs their own bot, and GitHub is the shared state. That is the default, and it is enough.

If you do want one machine to run all three Hermes bots, plus Lean and SymPy:

1. Install [Tailscale](https://tailscale.com/download) on that host and on each laptop.
2. On each machine, `tailscale up` and join the same tailnet.
3. Share the host (Tailscale share, or an invite to the tailnet) so Ilkham, Konstantin, and Lloyd can see it.
4. From a laptop, SSH to the host's MagicDNS name (`ssh <user>@<host>.<tailnet>.ts.net`).
5. On the host, run the setup script three times, once per role, with three profile directories. Run three gateways. Lean and SymPy stay on that host.

The laptops do not need elan. They still use git pull and push, and the Telegram group, the same way. Tailscale is only the path to the shared toolchain.
