"""Haven's isolated text emotion classifier.

The reference project uses a cleaned text pipeline, fixed-length text features
and a multi-label classifier. Its bundled model predicts English Big Five
personality traits, so it is not used here. Haven instead trains a small local
Chinese emotion model from explicitly bundled, non-user seed examples. The
classifier is a support signal only: it never creates memory, profile data, or
medical conclusions.
"""
from __future__ import annotations

import json
import os
import re
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import Any

MODEL_VERSION = "haven-text-emotion-tfidf-char-logreg-v1"
SEED_PATH = Path(__file__).with_name("emotion_seed.json")
EMOTION_LABELS = (
    "sadness", "loneliness", "anxiety", "anger", "self_negation", "shame",
    "guilt", "fear", "disappointment", "grief", "existential_confusion",
    "hurt", "joy", "stress",
)
EMOTION_NAMES = {
    "sadness": "悲伤", "loneliness": "孤独", "anxiety": "焦虑", "anger": "愤怒",
    "self_negation": "自我否定", "shame": "羞耻", "guilt": "内疚", "fear": "恐惧",
    "disappointment": "失望", "grief": "哀伤与失去", "existential_confusion": "存在性困惑",
    "hurt": "受伤与委屈", "joy": "喜悦", "stress": "压力",
}
_KEYWORDS = {
    "sadness": ("悲伤", "难过", "哭", "心碎", "低落", "痛苦"),
    "loneliness": ("孤独", "孤单", "没人理解", "没人陪", "被忽视"),
    "anxiety": ("焦虑", "担心", "不安", "紧张", "忐忑", "过度担忧"),
    "anger": ("生气", "愤怒", "火大", "气死", "不公平", "冒犯"),
    "self_negation": ("没用", "失败者", "做不好", "不够好", "自我否定"),
    "shame": ("羞耻", "丢脸", "出丑", "难堪"),
    "guilt": ("内疚", "自责", "后悔", "对不起"),
    "fear": ("害怕", "恐惧", "不敢", "失控", "危险"),
    "disappointment": ("失望", "落空", "挫败", "没有回报"),
    "grief": ("失去", "离世", "去世", "葬礼", "想念", "告别", "失恋"),
    "existential_confusion": ("人生意义", "虚无", "为什么活", "没方向", "不知道为何继续"),
    "hurt": ("委屈", "受伤", "背叛", "被排斥", "不被尊重"),
    "joy": ("开心", "高兴", "喜悦", "幸福", "顺利", "成就感"),
    "stress": ("压力", "累", "喘不过气", "紧绷", "放松不下来"),
}


def normalize_text(text: str) -> str:
    """Normalize text while preserving Chinese characters and emotional cues."""
    normalized = unicodedata.normalize("NFKC", str(text or "")).lower()
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def _load_seed() -> tuple[list[str], list[list[str]]]:
    rows = json.loads(SEED_PATH.read_text(encoding="utf-8"))
    texts = [normalize_text(row["text"]) for row in rows if str(row.get("text", "")).strip()]
    labels = [[label for label in row.get("labels", []) if label in EMOTION_LABELS] for row in rows]
    return texts, labels


@lru_cache(maxsize=1)
def _build_model() -> tuple[Any, Any] | None:
    if os.environ.get("EUNOIA_EMOTION_CLASSIFIER", "on").lower() in {"0", "off", "false", "disabled"}:
        return None
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.linear_model import LogisticRegression
        from sklearn.multiclass import OneVsRestClassifier
        from sklearn.preprocessing import MultiLabelBinarizer
    except ImportError:
        return None
    try:
        texts, labels = _load_seed()
        encoder = MultiLabelBinarizer(classes=list(EMOTION_LABELS))
        targets = encoder.fit_transform(labels)
        # Character n-grams preserve Chinese words, punctuation and short
        # phrases without requiring a tokenizer or downloading a model.
        vectorizer = TfidfVectorizer(
            analyzer="char", ngram_range=(2, 5), min_df=1,
            max_features=16000, sublinear_tf=True,
        )
        features = vectorizer.fit_transform(texts)
        classifier = OneVsRestClassifier(
            LogisticRegression(max_iter=400, class_weight="balanced", random_state=17),
        )
        classifier.fit(features, targets)
        return vectorizer, classifier
    except (OSError, ValueError, TypeError):
        return None


def _fallback(text: str) -> list[tuple[str, float]]:
    normalized = normalize_text(text)
    scores = []
    for label, terms in _KEYWORDS.items():
        hits = sum(1 for term in terms if term in normalized)
        if hits:
            scores.append((label, min(0.55 + 0.12 * hits, 0.92)))
    scores.sort(key=lambda item: item[1], reverse=True)
    return scores[:4]


def classify(text: str, top_k: int = 4) -> dict[str, Any]:
    """Return cautious emotion candidates for Haven support routing.

    The result is intentionally probabilistic and explicitly non-diagnostic.
    It is never persisted by this module.
    """
    normalized = normalize_text(text)
    if not normalized:
        return {"emotions": [], "method": "empty", "model_version": MODEL_VERSION, "uncertain": True}
    model = _build_model()
    predictions: list[tuple[str, float]] = []
    method = "keyword_fallback"
    if model is not None:
        vectorizer, classifier = model
        try:
            probabilities = classifier.predict_proba(vectorizer.transform([normalized]))[0]
            predictions = sorted(
                ((label, float(probability)) for label, probability in zip(EMOTION_LABELS, probabilities)),
                key=lambda item: item[1], reverse=True,
            )[:top_k]
            method = "tfidf_char_logistic_regression"
        except (ValueError, TypeError, IndexError):
            predictions = []
    if not predictions or predictions[0][1] < 0.28:
        predictions = _fallback(normalized) or predictions[:top_k]
        if method != "tfidf_char_logistic_regression":
            method = "keyword_fallback"
    emotions = [
        {"label": label, "name": EMOTION_NAMES[label], "confidence": round(max(0.0, min(score, 1.0)), 4)}
        for label, score in predictions[:top_k]
        if score >= 0.25
    ]
    confidence = emotions[0]["confidence"] if emotions else 0.0
    return {
        "emotions": emotions,
        "top_emotion": emotions[0]["label"] if emotions else None,
        "confidence": confidence,
        "method": method,
        "model_version": MODEL_VERSION,
        "uncertain": confidence < 0.55,
    }


def training_summary() -> dict[str, Any]:
    try:
        texts, labels = _load_seed()
        return {"samples": len(texts), "labels": list(EMOTION_LABELS), "model_version": MODEL_VERSION}
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return {"samples": 0, "labels": list(EMOTION_LABELS), "model_version": MODEL_VERSION}
