from pathlib import Path

PROMPT_DIR = Path(__file__).with_name("persona_prompts")

SPACE_PROMPTS = {
    "anatomy": PROMPT_DIR / "emotion_anatomy.txt",
    "debate": PROMPT_DIR / "rational_debate.txt",
    "guidance": PROMPT_DIR / "life_guidance.txt",
    "self_exploration": PROMPT_DIR / "self_exploration.txt",
}

SPACE_LABELS = {
    "anatomy": "情感解剖",
    "debate": "理性辩论",
    "guidance": "生活指导",
    "self_exploration": "自我探索",
}

DEBATE_STYLES = {
    "discussion": "采用正常讨论：双方共同探索问题，澄清概念、证据和分歧。",
    "opposition": "采用反方辩论：主动寻找用户观点的薄弱环节、反例和未验证前提，同时公平承认论点的优势；不为反驳而反驳。",
    "steelman": "采用钢人论证：先将用户观点重构为最强、最合理且公平的版本，并简要说明重构假设，再检验这个强版本。",
    "both_sides": "采用双方辩论：分别构建正方和反方的完整论证，比较前提、证据、解释力和代价，最后给出综合判断。",
}


def debate_instruction(style: str | None) -> str:
    return DEBATE_STYLES.get(style or "discussion", DEBATE_STYLES["discussion"])

LEGACY_MODE_MAP = {
    "reflect": "guidance",
    "relationship": "anatomy",
    "simulation": "guidance",
    "vent": "anatomy",
    "self": "self_exploration",
}


def normalize_mode(mode: str | None) -> str:
    if mode in SPACE_PROMPTS:
        return mode
    return LEGACY_MODE_MAP.get(mode or "", "guidance")


def prompt_for(mode: str) -> str:
    return SPACE_PROMPTS[normalize_mode(mode)].read_text(encoding="utf-8").strip()
