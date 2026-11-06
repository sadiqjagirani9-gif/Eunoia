"""Lightweight, transparent signal extraction to complement (not replace) the LLM."""
from dataclasses import dataclass


EMOTION_TERMS = {
    "焦虑": ("焦虑", "担心", "不安", "忐忑"),
    "悲伤": ("难过", "伤心", "悲伤", "想哭"),
    "愤怒": ("生气", "愤怒", "恼火", "气死"),
    "恐惧": ("害怕", "恐惧", "怕失去", "恐慌"),
    "羞耻": ("羞耻", "丢脸", "难堪"),
    "内疚": ("内疚", "愧疚", "自责"),
    "嫉妒": ("嫉妒", "吃醋"),
    "羡慕": ("羡慕",),
    "孤独": ("孤独", "孤单", "没人理解"),
    "失落": ("失落", "落空"),
    "失望": ("失望", "心凉"),
    "不甘": ("不甘", "不服", "释怀不了"),
    "依恋": ("依恋", "放不下", "很在意", "喜欢"),
    "无力感": ("无力", "没办法", "无能为力"),
    "空虚": ("空虚", "麻木"),
    "喜悦": ("开心", "高兴", "幸福", "愉快"),
}

NEEDS = {
    "被理解": ("理解", "懂我", "解释自己"),
    "被重视": ("在意我", "重视", "主动找我", "被关注"),
    "安全感": ("安全感", "怕失去", "稳定", "确定"),
    "情感回应": ("回应", "回复", "表达", "主动"),
    "独立自主": ("自由", "空间", "独立", "控制"),
    "归属感": ("归属", "融入", "被接纳"),
    "自我价值确认": ("认可", "价值", "不够好", "肯定"),
}

CONFLICT_PAIRS = (("想靠近", "害怕靠近"), ("希望被关注", "不愿暴露需求"), ("希望对方主动", "不愿主动表达"), ("希望自由", "害怕失去关系"), ("希望被理解", "不愿解释"), ("喜欢", "抗拒"), ("在意", "装作不在意"))
COGNITIONS = {
    "读心式推断": ("他一定觉得", "她肯定认为", "一定是不喜欢我", "就是故意"),
    "灾难化": ("肯定会失去", "一切都完了", "永远不会", "再也不会"),
    "非黑即白": ("要么", "不是...就是", "全都是", "从来都"),
    "过度概括": ("每次都", "所有人都", "总是这样", "从来没有"),
    "情绪化推理": ("我感觉所以一定", "让我觉得就说明"),
    "过度自责": ("都是我的错", "全怪我", "我毁了一切"),
}
RISK_TERMS = ("想自杀", "不想活", "结束生命", "自残", "伤害自己", "伤害他", "杀了他", "被打", "被威胁", "跟踪我", "强迫我")


def analyze(text: str) -> dict:
    lower = text.lower()
    emotions = [name for name, terms in EMOTION_TERMS.items() if any(t in lower for t in terms)]
    needs = [name for name, terms in NEEDS.items() if any(t in lower for t in terms)]
    conflicts = [f"{a} / {b}" for a, b in CONFLICT_PAIRS if a in text or b in text]
    cognitions = [name for name, terms in COGNITIONS.items() if any(t in lower for t in terms)]
    return {
        "emotions": emotions,
        "needs": needs,
        "conflicts": conflicts,
        "cognitive_patterns": cognitions,
        "safety_signal": any(term in lower for term in RISK_TERMS),
        "note": "这些只是文本线索，可能不完整或不准确；请以用户自己的描述为准。",
    }
