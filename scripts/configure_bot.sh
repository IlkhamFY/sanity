#!/usr/bin/env bash
# Configure a Hermes bot for its Sanity role: persona, shared protocol, wake word,
# loop guard, approvals. One command per bot; safe to run again.
#
#   APPROVERS=<id>,<id>,<id> bash scripts/configure_bot.sh reader     # or writer, verifier
#   bash scripts/configure_bot.sh check reader                              # only report, change nothing
#
# Where Hermes runs (environment variables):
#   HERMES_PROFILE     a Hermes profile name (adds -p <name>)               default: none
#   HERMES_CONTAINER   Docker container name, if Hermes runs in Docker       default: none (native)
#   SANITY_REPO        path of this repo *as the bot sees it*                default: this clone;
#                      in Docker: /opt/data/sanity (must exist inside the container)
#   HERMES_HOME        a different Hermes home (for testing)                 default: Hermes' own
#
# What it sets (backups of SOUL.md, config.yaml and .env first, as *.bak-<time>):
#   APPROVERS          comma-separated Telegram user IDs of the people who may approve the
#                      bot's risky commands: the three of us (not the bots). APPROVER_ID=<id>
#                      is the same for one person. Unset: approvals.approvers stays as it is.
#   SANITY_GROUP       the group as a `hermes send` target (telegram:-100...);
#                      default: the only Telegram group in `hermes send --list telegram`
#   KEEP_SOUL=1        keep your own persona; only list the communication sections to merge
#   NO_RESTART=1       do not restart the gateway at the end
#
# Not scriptable, done by you: in @BotFather switch on Bot-to-Bot Communication Mode
# (and group privacy off), and put the three people, the two other bots and the group
# into TELEGRAM_ALLOWED_USERS. The final check reports what is missing.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CONTAINER="${HERMES_CONTAINER:-}"
PROFILE="${HERMES_PROFILE:-}"
HOME_OVERRIDE="${HERMES_HOME:-}"
ROLES="reader writer verifier"

ok()   { printf '  \342\234\223 %s\n' "$*"; }
bad()  { printf '  ! %s\n' "$*"; ISSUES=$((ISSUES + 1)); }
say()  { printf '\n== %s\n' "$*"; }
die()  { printf 'error: %s\n' "$*" >&2; exit 1; }
ISSUES=0

# --- running things where Hermes is -------------------------------------------------

docker_env() {  # extra `docker exec` arguments, one per line
  [ -z "$HOME_OVERRIDE" ] || printf '%s\n' -e "HERMES_HOME=$HOME_OVERRIDE"
}

hermes_raw() {  # hermes with the profile, natively or in the container; Hermes' noise filtered
  local out code=0
  if [ -n "$CONTAINER" ]; then
    local envs=(); while IFS= read -r e; do [ -n "$e" ] && envs+=("$e"); done < <(docker_env)
    out="$(docker exec -i -u "$RUN_AS" ${envs[@]+"${envs[@]}"} "$CONTAINER" hermes ${PROFILE:+-p "$PROFILE"} "$@" 2>&1)" || code=$?
  elif [ -n "$HOME_OVERRIDE" ]; then
    out="$(HERMES_HOME="$HOME_OVERRIDE" hermes ${PROFILE:+-p "$PROFILE"} "$@" 2>&1)" || code=$?
  else
    out="$(hermes ${PROFILE:+-p "$PROFILE"} "$@" 2>&1)" || code=$?
  fi
  printf '%s\n' "$out" | grep -v -i -E 'pnpm|install out of sync|not logged in' || true
  return $code
}

in_place() {  # run a shell script (stdin) where the bot's files are, with our variables
  if [ -n "$CONTAINER" ]; then
    local envs=(); while IFS= read -r e; do [ -n "$e" ] && envs+=("$e"); done < <(docker_env)
    docker exec -i -u "$RUN_AS" ${envs[@]+"${envs[@]}"} \
      -e ROLE="$ROLE" -e REPO="$REPO" -e SOUL="$SOUL" -e CONFIG="$CONFIG" -e ENVF="$ENVF" \
      -e STAMP="$STAMP" -e GROUP="${GROUP:-}" -e KEEP_SOUL="${KEEP_SOUL:-}" \
      "$CONTAINER" sh -s
  else
    ROLE="$ROLE" REPO="$REPO" SOUL="$SOUL" CONFIG="$CONFIG" ENVF="$ENVF" STAMP="$STAMP" \
      GROUP="${GROUP:-}" KEEP_SOUL="${KEEP_SOUL:-}" sh -s
  fi
}

yaml_list() {  # "- a\n- b" or "[]" from `hermes config get` -> one item per line
  sed -n "s/^[[:space:]]*- *//p" | sed "s/^['\"]//; s/['\"]$//"
}

json_list() {  # items on stdin -> ["a", "b"]
  local first=1 item out="["
  while IFS= read -r item; do
    [ -n "$item" ] || continue
    [ $first = 1 ] || out="$out, "
    out="$out\"$item\""; first=0
  done
  printf '%s]' "$out"
}

locate() {
  case " $ROLES " in *" $ROLE "*) ;; *) die "role must be one of: $ROLES" ;; esac
  if [ -n "$CONTAINER" ]; then
    command -v docker >/dev/null || die "docker not found"
    [ "$(docker inspect -f '{{.State.Running}}' "$CONTAINER" 2>/dev/null)" = "true" ] || die "container '$CONTAINER' is not running"
    RUN_AS=root
    CONFIG="$(hermes_raw config path | tail -1)"
    RUN_AS="$(docker exec "$CONTAINER" stat -c %U "$(dirname "$CONFIG")")"
    REPO="${SANITY_REPO:-/opt/data/sanity}"
    docker exec "$CONTAINER" test -f "$REPO/agents/$ROLE/AGENT.md" || die "no $REPO/agents/$ROLE/AGENT.md inside the container; set SANITY_REPO"
  else
    command -v hermes >/dev/null || die "hermes not found on PATH (set HERMES_CONTAINER if it runs in Docker)"
    CONFIG="$(hermes_raw config path | tail -1)"
    REPO="${SANITY_REPO:-$ROOT}"
    [ -f "$REPO/agents/$ROLE/AGENT.md" ] || die "no $REPO/agents/$ROLE/AGENT.md; set SANITY_REPO"
  fi
  ENVF="$(hermes_raw config env-path | tail -1)"
  SOUL="$(dirname "$CONFIG")/SOUL.md"
  STAMP="$(date +%Y%m%d-%H%M%S)"
  echo "bot: role $ROLE, $( [ -n "$CONTAINER" ] && echo "container $CONTAINER (as $RUN_AS)" || echo native )${PROFILE:+, profile $PROFILE}"
  echo "     config $CONFIG"
  echo "     repo   $REPO"
}

# --- configure -------------------------------------------------------------------------

configure() {
  say "backups and persona"
  in_place <<'EOF'
set -eu
touch "$ENVF"
for f in "$SOUL" "$CONFIG" "$ENVF"; do [ -f "$f" ] && cp -p "$f" "$f.bak-$STAMP"; done
echo "  backups: *.bak-$STAMP next to SOUL.md, config.yaml, .env"
if [ -n "$KEEP_SOUL" ]; then
  echo "  persona: kept (KEEP_SOUL=1). Merge the communication parts of $REPO/agents/$ROLE/AGENT.md by hand:"
  case "$ROLE" in
    reader) echo "    Inputs, Outputs, the last line of Boundaries, Handoff (fetch_paper.py, then meta.json as its own document)" ;;
    writer) echo "    the Role line, the paragraph before step 1, step 6, the first four Boundaries lines" ;;
    verifier) echo "    the Messages section and section 4" ;;
  esac
else
  cp "$REPO/agents/$ROLE/AGENT.md" "$SOUL"
  echo "  persona: SOUL.md <- agents/$ROLE/AGENT.md"
fi
EOF

  say "skills"
  local dirs load
  dirs="$( { hermes_raw config get skills.external_dirs | yaml_list; echo "$REPO/skills"; } | awk '!seen[$0]++' | json_list)"
  load="$( { hermes_raw config get skills.auto_load | yaml_list; echo verify-math; echo sanity-protocol; } | awk '!seen[$0]++' | json_list)"
  hermes_raw config set skills.external_dirs "$dirs" >/dev/null
  hermes_raw config set skills.auto_load "$load" >/dev/null
  echo "  skills.external_dirs = $dirs"
  echo "  skills.auto_load     = $load"

  say ".env: mention-only, wake word, group"
  GROUP="${SANITY_GROUP:-}"
  if [ -z "$GROUP" ]; then
    local ids
    ids="$(hermes_raw send --list telegram | sed -n 's/.*\[\(-[0-9][0-9]*\)\].*/\1/p' | sort -u)"
    [ "$(printf '%s\n' "$ids" | grep -c .)" = 1 ] && GROUP="telegram:$ids"
  fi
  in_place <<'EOF'
set -eu
tmp="$ENVF.new.$$"
grep -v -E '^(TELEGRAM_REQUIRE_MENTION|TELEGRAM_MENTION_PATTERNS|SANITY_GROUP)=' "$ENVF" > "$tmp" || true
{
  echo "TELEGRAM_REQUIRE_MENTION=true"
  echo "TELEGRAM_MENTION_PATTERNS=sanity run=[^ ]+ .*to=$ROLE"
  [ -z "$GROUP" ] || echo "SANITY_GROUP=$GROUP"
} >> "$tmp"
cat "$tmp" > "$ENVF"; rm -f "$tmp"
echo "  TELEGRAM_REQUIRE_MENTION=true, wake word to=$ROLE${GROUP:+, SANITY_GROUP set}"
EOF
  [ -n "$GROUP" ] || echo "  ! SANITY_GROUP not set: the bot is in no group or several; re-run with SANITY_GROUP=telegram:<group id>" >&2

  say "loop guard and approvals"
  hermes_raw config set gateway.bot_loop_guard.bot_replies_expect_reply true >/dev/null
  hermes_raw config set gateway.bot_loop_guard.max_hops 8 >/dev/null
  echo "  gateway.bot_loop_guard: bot_replies_expect_reply true, max_hops 8"
  local approvers_in="${APPROVERS:-${APPROVER_ID:-}}"
  if [ -n "$approvers_in" ]; then
    approvers_in="$(printf '%s' "$approvers_in" | tr -d ' ')"
    printf '%s' "$approvers_in" | grep -Eq '^[0-9]{5,15}(,[0-9]{5,15})*$' \
      || die "APPROVERS must be comma-separated numeric Telegram user IDs"
    hermes_raw config set approvals.approvers "$(printf '%s\n' "$approvers_in" | tr ',' '\n' | json_list)" >/dev/null
    echo "  approvals.approvers = $approvers_in"
  else
    echo "  ! approvals.approvers unchanged: set APPROVERS=<id>,<id>,<id> (the three people) so bots cannot approve" >&2
  fi

  say "refresh running sessions"
  hermes_raw sessions refresh-prompts | tail -1 | sed 's/^/  /'

  if [ -n "${NO_RESTART:-}" ]; then
    say "restart skipped (NO_RESTART=1): restart the gateway yourself"
  elif [ -n "$CONTAINER" ]; then
    say "restarting container $CONTAINER"
    docker restart "$CONTAINER" >/dev/null && sleep 5
  else
    say "restarting the gateway"
    hermes_raw gateway restart | tail -2 | sed 's/^/  /' || echo "  ! could not restart; restart your gateway the way you normally do" >&2
  fi
}

# --- check -----------------------------------------------------------------------------

check() {
  say "check: $ROLE bot"
  local report
  report="$(in_place <<'EOF'
set -eu
n="$(wc -l < "$REPO/agents/$ROLE/AGENT.md")"
if head -n "$n" "$SOUL" 2>/dev/null | cmp -s - "$REPO/agents/$ROLE/AGENT.md"; then echo "OK persona = agents/$ROLE/AGENT.md"
elif grep -q "sanity-protocol" "$SOUL" 2>/dev/null && grep -q "NO_REPLY" "$SOUL"; then echo "OK persona is your own, mentions sanity-protocol and NO_REPLY"
else echo "BAD persona does not follow the protocol (no sanity-protocol / NO_REPLY in SOUL.md)"; fi
if [ "$ROLE" = reader ]; then
  if grep -q "fetch_paper.py" "$SOUL" 2>/dev/null && grep -q "meta.json" "$SOUL"; then echo "OK reader fetches the paper and posts meta.json"
  else echo "BAD reader SOUL.md has no fetch_paper.py / meta.json step; reconfigure copies agents/reader/AGENT.md"; fi
fi
v() { sed -n "s/^$1=//p" "$ENVF" 2>/dev/null | tail -1; }
[ "$(v TELEGRAM_REQUIRE_MENTION)" = true ] && echo "OK TELEGRAM_REQUIRE_MENTION=true" || echo "BAD TELEGRAM_REQUIRE_MENTION is not true: the bot answers every group message"
case "$(v TELEGRAM_MENTION_PATTERNS)" in *"to=$ROLE"*) echo "OK wake word to=$ROLE" ;; *) echo "BAD wake word to=$ROLE missing (TELEGRAM_MENTION_PATTERNS)" ;; esac
g="$(v SANITY_GROUP)"
case "$g" in telegram:-*) echo "OK SANITY_GROUP set" ;; *) echo "BAD SANITY_GROUP missing: no messages during long turns" ;; esac
allowed="$(v TELEGRAM_ALLOWED_USERS)"
count="$(printf '%s' "$allowed" | tr ',' '\n' | grep -c . || true)"
if [ "$count" -ge 6 ]; then echo "OK TELEGRAM_ALLOWED_USERS has $count IDs"
else echo "BAD TELEGRAM_ALLOWED_USERS has $count IDs: needs the 3 people, the 2 other bots and the group"; fi
if [ -n "$g" ]; then
  printf '%s' ",$allowed," | grep -q ",${g#telegram:}," && echo "OK group ID is in TELEGRAM_ALLOWED_USERS" || echo "BAD group ID ${g#telegram:} is not in TELEGRAM_ALLOWED_USERS"
fi
[ -n "$(v TELEGRAM_ALLOW_BOTS)$(v TELEGRAM_ALLOWED_BOTS)" ] && echo "BAD TELEGRAM_ALLOW_BOTS is set: it admits any bot; remove it" || true
EOF
)"
  printf '%s\n' "$report" | while IFS= read -r line; do
    case "$line" in OK\ *) printf '  \342\234\223 %s\n' "${line#OK }" ;; BAD\ *) printf '  ! %s\n' "${line#BAD }" ;; esac
  done
  ISSUES=$((ISSUES + $(printf '%s\n' "$report" | grep -c '^BAD ' || true)))

  local load expect hops approvers
  load="$(hermes_raw config get skills.auto_load | yaml_list | tr '\n' ' ')"
  case "$load" in *sanity-protocol*) ok "skills.auto_load: $load" ;; *) bad "skills.auto_load lacks sanity-protocol ($load)" ;; esac
  expect="$(hermes_raw config get gateway.bot_loop_guard.bot_replies_expect_reply | tail -1 | tr -d "' ")"
  hops="$(hermes_raw config get gateway.bot_loop_guard.max_hops | tail -1 | tr -d "' ")"
  if [ "$expect" = true ] && [ "$hops" -ge 8 ] 2>/dev/null; then ok "loop guard: bot_replies_expect_reply true, max_hops $hops"
  else bad "loop guard: bot_replies_expect_reply=$expect max_hops=$hops (needs true and 8)"; fi
  approvers="$(hermes_raw config get approvals.approvers | yaml_list | tr '\n' ' ')"
  case "$approvers" in
    *'*'*|"") bad "approvals.approvers = '${approvers:-*}': anyone allowed, bots included, may approve; set APPROVERS=<the three people's IDs>" ;;
    *) ok "approvals.approvers: $approvers($(printf '%s' "$approvers" | wc -w | tr -d ' ') person/people)" ;;
  esac
  printf '  ? @BotFather: Bot-to-Bot Communication Mode on, group privacy off (cannot be checked from here)\n'
  if [ "$ISSUES" = 0 ]; then echo; echo "ready: the $ROLE bot follows skills/sanity-protocol"; else echo; echo "$ISSUES thing(s) to fix (marked !)"; fi
}

main() {
  case "${1:-}" in
    check) ROLE="${2:-}"; locate; check; [ "$ISSUES" = 0 ] ;;
    reader|writer|verifier) ROLE="$1"; locate; configure; check; [ "$ISSUES" = 0 ] ;;
    *) awk 'NR == 1 { next } /^#/ { sub(/^# ?/, ""); print; next } { exit }' "$0"; exit 2 ;;
  esac
}

main "$@"
