from app import emotion_classifier


def test_haven_emotion_classifier_uses_local_seed_model_and_returns_uncertain_candidates():
    emotion_classifier._build_model.cache_clear()
    summary = emotion_classifier.training_summary()
    result = emotion_classifier.classify("我失恋了，很难过，也觉得身边没有人理解我。")
    assert summary["samples"] >= 40
    assert "sadness" in summary["labels"]
    assert result["emotions"]
    assert result["method"] in {"tfidf_char_logistic_regression", "keyword_fallback"}
    assert all(0 <= item["confidence"] <= 1 for item in result["emotions"])
    assert "诊断" not in str(result)


def test_haven_emotion_classifier_has_safe_keyword_fallback(monkeypatch):
    monkeypatch.setenv("EUNOIA_EMOTION_CLASSIFIER", "off")
    emotion_classifier._build_model.cache_clear()
    result = emotion_classifier.classify("我现在很焦虑，也很害怕未来。")
    assert result["method"] == "keyword_fallback"
    assert {item["label"] for item in result["emotions"]} >= {"anxiety", "fear"}
    monkeypatch.delenv("EUNOIA_EMOTION_CLASSIFIER", raising=False)
    emotion_classifier._build_model.cache_clear()
