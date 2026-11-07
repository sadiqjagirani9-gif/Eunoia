"""Canonical dimensions for the user's editable cognitive profile.

Persona observations remain privately scoped. This module only shapes the
user-requested profile view and never grants a persona access to another's data.
"""

DIMENSION_LABELS = {
    'background': '身份与个人背景',
    'thinking': '思维结构',
    'emotion': '情绪与心理机制',
    'personality': '人格与行为倾向',
    'values': '价值观与信念',
    'blindspots': '认知盲点',
    'interpersonal': '人际关系与社会认知',
    'decisions': '决策与行动',
    'self_concept': '自我认知与内在矛盾',
    'growth': '成长轨迹',
}
DIMENSIONS = tuple(DIMENSION_LABELS)
LEGACY_DIMENSIONS = {'behavior': 'decisions'}
DIMENSION_PERSONAS = {
    'background': 'self_exploration', 'thinking': 'debate',
    'emotion': 'anatomy', 'personality': 'self_exploration',
    'values': 'self_exploration', 'blindspots': 'debate',
    'interpersonal': 'anatomy', 'decisions': 'guidance',
    'self_concept': 'self_exploration', 'growth': 'self_exploration',
}
PERSONA_NAMES = {
    'anatomy': 'Evelyn', 'debate': 'Arthur', 'guidance': 'Sophia',
    'self_exploration': 'Iris', 'lucien': 'Lucien', 'felix': 'Felix',
}


def canonical_dimension(value: str) -> str:
    return LEGACY_DIMENSIONS.get(value, value)


def profile_shape(observations: list[dict]) -> dict[str, list[dict]]:
    result = {key: [] for key in DIMENSIONS}
    for row in observations:
        dimension = canonical_dimension(row.get('dimension', ''))
        if dimension in result and row.get('status') in ('confirmed', 'partially_confirmed', 'pending', 'uncertain', 'disputed'):
            result[dimension].append(row)
    return result
