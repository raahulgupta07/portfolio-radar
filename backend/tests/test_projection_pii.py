from app.mcp.pii import redact, redact_text
from app.mcp.projection import project


def test_projection_on_list_dict_and_nested_lists():
    data = {"total": 2, "projects": [{"code": "A", "health": "on_track", "owner": {"name": "X", "id": 1}},
                                     {"code": "B", "health": "at_risk", "owner": {"name": "Y", "id": 2}}]}
    assert project(data, ["projects[].code", "total"]) == {"total": 2, "projects": [{"code": "A"}, {"code": "B"}]}
    assert project(data, ["projects.owner.name"]) == {"projects": [{"owner": {"name": "X"}}, {"owner": {"name": "Y"}}]}
    assert project(data["projects"], ["code"]) == [{"code": "A"}, {"code": "B"}]


def test_projection_ignores_unknown_paths_and_never_adds_data():
    assert project({"a": 1}, ["b", "a.c", "zz[].y"]) == {}
    assert project({"a": 1}, None) == {"a": 1}
    assert project("text", ["a"]) == "text"


def test_pii_removes_emails_and_phones_but_not_dates_or_codes():
    text = ("Owner aung.aung@cityholdings.com.mm, call +95 9 450 123 456 or 09451234567. "
            "Due 2026-10-19, code CHL-IT-DAAI-GPT03, 40 tasks, budget 1200000.")
    out = redact_text(text)
    assert "aung.aung@" not in out and "450 123" not in out and "09451234567" not in out
    assert "2026-10-19" in out and "CHL-IT-DAAI-GPT03" in out and "1200000" in out


def test_pii_walks_nested_structures():
    assert redact({"a": ["x@y.io", {"b": "+66 2 123 4567"}], "n": 5}) == {
        "a": ["[email removed]", {"b": "[phone removed]"}], "n": 5}
