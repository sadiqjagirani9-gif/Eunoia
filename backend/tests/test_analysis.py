from app.analysis import analyze


def test_multiple_emotions_needs_and_conflict_are_detected():
    result = analyze("我很喜欢她，但又害怕靠近。她不主动找我让我焦虑，我希望被理解。")
    assert "依恋" in result["emotions"]
    assert "焦虑" in result["emotions"]
    assert "被理解" in result["needs"]
    assert any("想靠近" in conflict and "害怕靠近" in conflict for conflict in result["conflicts"])
    assert result["safety_signal"] is False


def test_potential_safety_signal_is_flagged():
    assert analyze("我最近不想活了")["safety_signal"] is True


def test_analysis_does_not_invent_signals():
    result = analyze("今天下雨了。")
    assert result["emotions"] == []
    assert result["needs"] == []
    assert result["cognitive_patterns"] == []
