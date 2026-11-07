from app.personas import DEBATE_STYLES, SPACE_PROMPTS, debate_instruction, normalize_mode, prompt_for, system_prompt_for


def test_six_spaces_have_separate_prompt_files_and_distinct_frameworks():
    prompts = {mode: prompt_for(mode) for mode in SPACE_PROMPTS}
    assert len({path.resolve() for path in SPACE_PROMPTS.values()}) == 6
    assert len(set(prompts.values())) == 6
    assert "情绪" in prompts["anatomy"]
    assert "证据" in prompts["debate"]
    assert "行动" in prompts["guidance"]
    assert "自我叙事" in prompts["self_exploration"]
    assert "文学艺术探索者 Lucien" in prompts["lucien"]
    assert "哲学讨论" in prompts["lucien"]
    assert "日常陪伴者 Felix" in prompts["felix"]
    assert "认真倾听" in prompts["felix"]


def test_new_persona_system_prompts_do_not_inherit_emotional_mentor_prompt():
    assert "情感导师" not in system_prompt_for("lucien")
    assert "情感导师" not in system_prompt_for("felix")
    assert "文学艺术探索者 Lucien" in system_prompt_for("lucien")
    assert "日常陪伴者 Felix" in system_prompt_for("felix")


def test_legacy_conversation_modes_remain_readable():
    assert normalize_mode("relationship") == "anatomy"
    assert normalize_mode("simulation") == "guidance"
    assert normalize_mode("self") == "self_exploration"
    assert normalize_mode("legacy-unknown") == "guidance"


def test_emotion_anatomy_uses_evelyn_persona_with_clinical_boundaries():
    prompt = prompt_for("anatomy")
    assert "情感导师 Evelyn" in prompt
    assert "Winnicott" in prompt and "Bowlby" in prompt
    assert "不进行疾病诊断" in prompt
    assert "每次最多提出两个" in prompt


def test_arthur_persona_and_four_debate_styles_are_distinct():
    prompt = prompt_for("debate")
    assert "理性辩论者 Arthur" in prompt
    assert "Popper" in prompt and "Kuhn" in prompt
    assert set(DEBATE_STYLES) == {"discussion", "opposition", "steelman", "both_sides"}
    assert len({debate_instruction(style) for style in DEBATE_STYLES}) == 4
    assert "最强、最合理且公平" in debate_instruction("steelman")


def test_sophia_persona_balances_practicality_and_structural_context():
    prompt = prompt_for("guidance")
    assert "人生顾问 Sophia" in prompt
    assert "机会成本" in prompt and "可逆性" in prompt
    assert "结构性困难" in prompt
    assert "不编造法规、数据或事实" in prompt


def test_iris_persona_uses_cited_evidence_for_long_term_reflection():
    prompt = prompt_for("self_exploration")
    assert "自我探索者 Iris" in prompt
    assert "Kierkegaard" in prompt and "Frankl" in prompt
    assert "没有来源证据时明确说暂时无法核实" in prompt
    assert "每次最多提出两个" in prompt
