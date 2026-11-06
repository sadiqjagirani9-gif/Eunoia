LEVELS = ((0, '极低'), (2, '较低'), (5, '中等'), (10, '较高'))

def confidence_label(evidence_count: int, has_counter_evidence: bool = False, distinct_contexts: int = 1) -> str:
    if has_counter_evidence or evidence_count < 3 or distinct_contexts < 2:
        return '极低'
    if evidence_count >= 10 and distinct_contexts >= 4:
        return '较高'
    if evidence_count >= 5 and distinct_contexts >= 3:
        return '中等'
    return '较低'

def can_form_observation(evidence_count: int, distinct_contexts: int) -> bool:
    return evidence_count >= 3 and distinct_contexts >= 2
