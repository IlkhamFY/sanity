#!/usr/bin/env bash
# Copy one Sanity role into a Hermes profile and install Python deps.
# Tokens stay out of this script. HERMES_PROFILE_DIR is a placeholder path.
#
#   HERMES_PROFILE_DIR="$HOME/.hermes/profiles/sanity-reader" bash scripts/setup_bot.sh reader
set -euo pipefail

ROLE="${1:-}"
case "$ROLE" in
  reader|verifier|writer) ;;
  *)
    echo "usage: scripts/setup_bot.sh reader|verifier|writer" >&2
    exit 2
    ;;
esac

# Placeholder: where this role's Hermes profile should live.
HERMES_PROFILE_DIR="${HERMES_PROFILE_DIR:-"$HOME/.hermes/profiles/sanity-$ROLE"}"
SANITY_REPO_URL="${SANITY_REPO_URL:-}"

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

if [[ -n "${SANITY_WORKDIR:-}" ]]; then
  if [[ ! -d "$SANITY_WORKDIR/.git" ]]; then
    if [[ -z "$SANITY_REPO_URL" ]]; then
      echo "Set SANITY_REPO_URL to clone into $SANITY_WORKDIR" >&2
      exit 2
    fi
    git clone "$SANITY_REPO_URL" "$SANITY_WORKDIR"
  fi
  ROOT="$(cd "$SANITY_WORKDIR" && pwd)"
fi

cd "$ROOT"
if [[ -d .git ]]; then
  git pull --ff-only || echo "git pull did not fast-forward. Continuing with this checkout."
fi

python3 -m venv .venv
.venv/bin/python -m pip install -r agents/verifier/requirements.txt

mkdir -p "$HERMES_PROFILE_DIR"
cp -R "$ROOT/hermes/$ROLE/." "$HERMES_PROFILE_DIR/"
cp "$ROOT/agents/$ROLE/AGENT.md" "$HERMES_PROFILE_DIR/SOUL.md"

TOKEN_NAME="$(printf '%s' "$ROLE" | tr '[:lower:]' '[:upper:]')_TELEGRAM_TOKEN"

cat <<EOF

Profile copied to: $HERMES_PROFILE_DIR
Role prompt: agents/$ROLE/AGENT.md -> $HERMES_PROFILE_DIR/SOUL.md
Skill: skills/verify-math (see skills.external_dirs and skills.auto_load in config.yaml)
Python: $ROOT/.venv

Still manual:

1. In @BotFather, send /setprivacy, choose this bot, and choose Disable.
2. Remove the bot from the group and add it again. Privacy does not update until you do.
3. If the bot still shows "has no access to messages", privacy is still on. Repeat steps 1 and 2.
4. Set the team's numeric Telegram user IDs. Replace the placeholders in
   $HERMES_PROFILE_DIR/config.yaml and in the profile .env:
   TELEGRAM_ALLOWED_USERS=id1,id2,id3
   A starter list of names is hermes/$ROLE/env.example. Do not commit the filled-in file.
5. Set the BotFather token as an environment variable. Do not write it into the repo.
   Hermes reads TELEGRAM_BOT_TOKEN. On this machine you can keep it as $TOKEN_NAME
   and copy that value into TELEGRAM_BOT_TOKEN for this profile only.
6. Replace \${SANITY_REPO}, \${MODEL_PROVIDER}, \${MODEL_NAME}, and the user-id
   placeholders in $HERMES_PROFILE_DIR/config.yaml.
7. Start the Hermes gateway for this profile.

EOF
