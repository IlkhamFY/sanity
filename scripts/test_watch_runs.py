"""The poller matches stage to role and ignores other files."""

import json

from watch_runs import matching_runs, scan


def _status(path, stage, owner="bot"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "paper": path.parent.name,
                "stage": stage,
                "owner_bot": owner,
                "updated_at": "2026-11-18T00:00:00Z",
                "commit": "abc",
                "notes": "",
            }
        ),
        encoding="utf-8",
    )


def test_only_the_matching_stage_is_listed(tmp_path):
    runs = tmp_path / "runs"
    _status(runs / "alpha" / "status.json", "verifier", "HermesAgent")
    _status(runs / "beta" / "status.json", "reader", "Hermes PI")
    _status(runs / "gamma" / "status.json", "done", "writer")
    (runs / "broken").mkdir()
    (runs / "broken" / "status.json").write_text("{", encoding="utf-8")

    found = matching_runs(runs, "verifier")
    assert [row["slug"] for row in found] == ["alpha"]
    assert "HermesAgent" in scan(runs, "verifier")[0]
    assert scan(runs, "writer") == []
    assert scan(runs, "reader")[0].startswith("runs/beta")
