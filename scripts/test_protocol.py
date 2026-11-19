"""The shared protocol (skills/sanity-protocol) and the bots' settings agree.

Every header in the protocol's message table wakes exactly the bot it addresses
(`to=<role>`), and status/done messages wake none. All three bots load the skill.
"""

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SKILL = REPO / "skills" / "sanity-protocol" / "SKILL.md"
ROLES = ("reader", "verifier", "writer")


def wake_word(role: str) -> re.Pattern:
    text = (REPO / "hermes" / role / "env.example").read_text(encoding="utf-8")
    value = re.search(r"^TELEGRAM_MENTION_PATTERNS=(.+)$", text, re.M).group(1)
    return re.compile(value, re.I)  # Hermes compiles its patterns case-insensitively


def table_headers() -> list[str]:
    section = SKILL.read_text(encoding="utf-8").split("## 3. The messages")[1].split("## 4.")[0]
    headers = []
    for row in section.splitlines():
        if not row.startswith("| ") or row.startswith("| #"):
            continue
        cells = [c.strip() for c in row.strip("|").split("|")]
        headers += [h for h in re.findall(r"`(sanity run=[^`]+)`", cells[2])]
    return headers


def test_skill_has_frontmatter_name():
    assert SKILL.read_text(encoding="utf-8").startswith("---\nname: sanity-protocol\n")


def test_every_table_header_wakes_exactly_its_role():
    headers = table_headers()
    assert len(headers) >= 9
    patterns = {role: wake_word(role) for role in ROLES}
    for header in headers:
        target = re.search(r"\bto=(\w+)", header)
        woken = {role for role, p in patterns.items() if p.search(header)}
        if target and target.group(1) in ROLES:
            assert woken == {target.group(1)}, (header, woken)
        elif target:
            # publisher is a daemon. It has no Hermes wake word.
            assert target.group(1) == "publisher", header
            assert woken == set(), (header, woken)
        else:
            assert woken == set(), (header, woken)


@pytest.mark.parametrize("text", [
    "please send this to=verifier",           # no sanity header
    "sanity run=x status=done attempt=1",     # done message
    "NO_REPLY",
])
def test_plain_text_and_status_wake_nobody(text):
    assert not any(wake_word(role).search(text) for role in ROLES)


@pytest.mark.parametrize("role", ROLES)
def test_every_bot_loads_the_protocol_and_sets_the_loop_guard(role):
    config = (REPO / "hermes" / role / "config.yaml").read_text(encoding="utf-8")
    assert "- sanity-protocol" in config
    if role != "verifier":  # the Verifier's loop guard is set by scripts/setup_verifier_docker.sh
        assert "bot_replies_expect_reply: true" in config and "max_hops: 8" in config


@pytest.mark.parametrize("role", ROLES)
def test_every_role_prompt_points_to_the_protocol(role):
    """Each role prompt refers to the shared skill; the rules themselves (NO_REPLY etc.) live there."""
    prompt = (REPO / "agents" / role / "AGENT.md").read_text(encoding="utf-8")
    assert "sanity-protocol" in prompt


def test_reader_fetch_step_is_what_reconfigure_installs():
    prompt = (REPO / "agents" / "reader" / "AGENT.md").read_text(encoding="utf-8")
    assert "python scripts/fetch_paper.py <id>" in prompt
    assert "runs/<slug>/source/meta.json" in prompt
    assert "Telegram allows one file per message" in prompt
    assert "publisher files the run under Examples" in prompt
    configure = (REPO / "scripts" / "configure_bot.sh").read_text(encoding="utf-8")
    assert 'cp "$REPO/agents/$ROLE/AGENT.md" "$SOUL"' in configure
    assert "fetch_paper.py" in configure and "meta.json" in configure
    setup = (REPO / "scripts" / "setup_bot.sh").read_text(encoding="utf-8")
    assert 'cp "$ROOT/agents/$ROLE/AGENT.md" "$HERMES_PROFILE_DIR/SOUL.md"' in setup
    windows = (REPO / "scripts" / "setup_bot.ps1").read_text(encoding="utf-8")
    assert 'Join-Path $ProfileDir "SOUL.md"' in windows


def test_configure_script_writes_the_same_wake_word_as_the_protocol():
    script = (REPO / "scripts" / "configure_bot.sh").read_text(encoding="utf-8")
    written = re.search(r'TELEGRAM_MENTION_PATTERNS=(sanity run=[^"]+to=)\$ROLE', script).group(1)
    for role in ROLES:
        assert wake_word(role).pattern == written + role
