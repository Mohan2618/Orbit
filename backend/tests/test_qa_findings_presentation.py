from app.services.qa_findings_presentation import group_findings


def finding(category, title, location):
    return {"category": category, "title": title, "location": location}


def test_repeated_compatibility_warnings_group_without_losing_locations():
    items = [
        finding("compatibility", "Pydantic deprecated API", "schema_a.py:10"),
        finding("security", "Possible embedded credential", "test_a.py:11"),
        finding("compatibility", "Pydantic deprecated API", "schema_b.py:20"),
    ]
    groups = group_findings(items)
    assert len(groups) == 2
    assert [item["location"] for item in groups[0]["members"]] == [
        "schema_a.py:10", "schema_b.py:20"
    ]
    assert len(groups[1]["members"]) == 1


def test_security_findings_are_never_grouped():
    items = [finding("security", "Possible embedded credential", "a.py"),
             finding("security", "Possible embedded credential", "b.py")]
    assert len(group_findings(items)) == 2


def test_empty_findings():
    assert group_findings([]) == []
