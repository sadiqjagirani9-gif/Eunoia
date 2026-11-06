"""Surface possible changes as questions, never as accusations."""
from collections.abc import Iterable

PAIRS = {
    '自由': ('稳定', '依赖', '亲密'),
    '独立': ('依赖', '陪伴', '支持'),
    '主动': ('等待', '被动'),
    '回避': ('沟通', '表达', '面对'),
    '不在意': ('在意', '重视', '嫉妒'),
}

def detect(previous: str, current: str) -> dict | None:
    for key, opposites in PAIRS.items():
        if key in previous and any(word in current for word in opposites):
            return {'past': previous, 'present': current, 'status': 'pending', 'question': f'我注意到你之前提到“{key}”，这次又谈到“{next(w for w in opposites if w in current)}”。这是最近的变化，还是两种需要一直同时存在？'}
        if key in current and any(word in previous for word in opposites):
            return {'past': previous, 'present': current, 'status': 'pending', 'question': f'你过去比较强调“{next(w for w in opposites if w in previous)}”，而现在提到了“{key}”。你觉得这是想法变化、情境不同，还是两者一直并存？'}
    return None

def compare(observations: Iterable[dict], current_text: str) -> list[dict]:
    found=[]
    for item in observations:
        result=detect(str(item.get('statement','')), current_text)
        if result:
            result['observation_id']=item.get('id')
            found.append(result)
    return found
