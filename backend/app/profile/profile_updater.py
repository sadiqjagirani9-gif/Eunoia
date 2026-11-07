"""Conservative incremental extraction of user statements.

This is deliberately rule based: a single message yields a candidate tied to
its exact wording, never a personality verdict. Model calls are unnecessary.
"""
import hashlib
import re

RULES = (
    ('growth', ('以前', '过去', '从前'), ('现在', '最近', '如今')),
    ('background', ('我在读', '我学过', '我的专业', '我从事', '我住在', '我喜欢', '我的兴趣')),
    ('values', ('我重视', '我看重', '对我来说', '我认为重要', '我珍惜')),
    ('self_concept', ('我觉得自己', '我是一个', '我希望成为', '我想成为', '我对自己的评价')),
    ('decisions', ('我决定', '我选择', '我已经', '我做了', '我计划', '我打算', '我还没决定', '我犹豫')),
    ('interpersonal', ('我跟朋友', '我和家人', '我对伴侣', '我在关系里', '我不敢说', '我主动沟通')),
    ('thinking', ('我习惯先', '我总会分析', '我反复想', '我倾向于思考', '我很难接受不确定')),
    ('emotion', ('我感到', '我最近感到', '我觉得很', '我很焦虑', '我很生气', '我很难过', '我害怕', '我嫉妒')),
)


def normalize_statement(value: str) -> str:
    return re.sub(r'[^\w\u4e00-\u9fff]', '', value).lower()


def fingerprint(value: str) -> str:
    return hashlib.sha256(normalize_statement(value).encode('utf-8')).hexdigest()


def similar(left: str, right: str, threshold: float = 0.72) -> bool:
    a, b = normalize_statement(left), normalize_statement(right)
    if a == b:
        return True
    if min(len(a), len(b)) < 8:
        return False
    grams_a = {a[i:i + 2] for i in range(len(a) - 1)}
    grams_b = {b[i:i + 2] for i in range(len(b) - 1)}
    return len(grams_a & grams_b) / max(1, len(grams_a | grams_b)) >= threshold


def extract_signals(text: str) -> list[dict]:
    results = []
    for raw in re.split(r'[。！？!?\n；;]', text):
        clause = raw.strip(' ，,：:「」“”\"')
        if not 8 <= len(clause) <= 300 or '我' not in clause:
            continue
        if clause.startswith(('他说', '她说', '他们说', '假如', '如果我')):
            continue
        for rule in RULES:
            dimension = rule[0]
            matched = all(any(cue in clause for cue in group) for group in rule[1:]) if dimension == 'growth' else any(cue in clause for cue in rule[1])
            if not matched:
                continue
            action_kind = 'reported_action' if dimension == 'decisions' and any(cue in clause for cue in ('我已经', '我做了', '我选择')) else 'intention' if dimension == 'decisions' else ''
            context_note = '用户在当前情境中的自述，尚需核对适用范围。'
            if action_kind == 'reported_action':
                context_note += '用户描述的是已经发生的行动。'
            elif action_kind == 'intention':
                context_note += '用户描述的是计划、意愿或尚未完成的决定，不能视为已采取行动。'
            results.append({
                'dimension': dimension, 'statement': clause, 'evidence': clause,
                'evidence_class': 'situational', 'context_note': context_note,
                'action_kind': action_kind, 'fingerprint': fingerprint(clause),
            })
            break
        if len(results) >= 3:
            break
    return results
