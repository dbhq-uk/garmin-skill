"""SKILL.md is what the agent reads, so what it claims has to be what the code does.

It drifted before: it told the agent to log in again on a rate limit, promised
an auto-refresh and a timeout that did not exist, and described an MFA flow
that could not work. These tests tie its claims to the code.
"""

import re
from pathlib import Path

SKILL_DIR = Path(__file__).parent.parent
SKILL_MD = (SKILL_DIR / "SKILL.md").read_text()
SOURCE = "\n".join(p.read_text() for p in (SKILL_DIR / "scripts").glob("*.py"))


def _body() -> str:
    return SKILL_MD.split("---", 2)[2]


def _failure_rows() -> list[str]:
    section = SKILL_MD.split("## When a script fails", 1)[1].split("\n## ", 1)[0]
    return [line for line in section.splitlines() if line.startswith("| `")]


def test_every_message_it_tells_the_agent_to_match_is_one_the_code_prints():
    rows = _failure_rows()
    assert rows
    for row in rows:
        for message in re.findall(r"`([^`]+)`", row.split("|")[1]):
            if message == "Error: ... failed":
                # Put together at run time: fetch() raises "<call> failed: ...",
                # and every script prints what it catches as "Error: ...".
                assert '{name} failed' in SOURCE
                assert 'f"Error: {e}' in SOURCE
            else:
                assert message in SOURCE, f"SKILL.md tells the agent to match {message!r}, which no script prints"


def test_a_rate_limit_is_never_answered_with_a_login():
    row = next(r for r in _failure_rows() if "rate-limiting" in r)
    assert "Do not log in" in row
    for line in SKILL_MD.splitlines():
        if "rate" in line.lower() and "log in" in line.lower():
            assert "not log in" in line.lower() or "do not" in line.lower(), line


def test_every_script_it_names_exists():
    for name in set(re.findall(r"\$\{CLAUDE_SKILL_DIR\}/scripts/([\w.]+)", SKILL_MD)):
        assert (SKILL_DIR / "scripts" / name).is_file(), name


def test_units_setting_matches_the_code():
    assert '"units"' in SKILL_MD
    assert 'config.setdefault("units", "imperial")' in SOURCE
    assert '"imperial"` (default' in SKILL_MD
    assert 'if units == "metric"' in SOURCE


def test_has_when_not_to_use_and_interpretation_rules():
    assert "## When not to use" in SKILL_MD
    assert "## Reading the numbers" in SKILL_MD
    assert "Never diagnose" in SKILL_MD


def test_stays_short():
    assert len(_body().split()) <= 500


def test_every_flag_it_names_is_one_a_script_defines():
    flags = set(re.findall(r"(?<![\w-])--[a-z][\w-]*", _body()))
    assert "--json" in flags
    for flag in flags:
        assert f'"{flag}"' in SOURCE, f"SKILL.md names {flag}, which no script defines"
    for line in SKILL_MD.splitlines():
        match = re.search(r"\$\{CLAUDE_SKILL_DIR\}/scripts/([\w.]+)(.*)", line)
        if match:
            source = (SKILL_DIR / "scripts" / match.group(1)).read_text()
            for flag in re.findall(r"(?<![\w-])--[a-z][\w-]*", match.group(2).split("#")[0]):
                assert f'"{flag}"' in source, f"SKILL.md passes {flag} to {match.group(1)}, which does not define it"
