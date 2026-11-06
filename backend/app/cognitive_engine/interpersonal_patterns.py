def extract(text: str) -> dict:
    cues={'hides_needs':('不想解释','不敢说','装作不在意'),'seeks_direct_talk':('我跟他沟通','我告诉她','我表达了'),'approach_avoidance':('想靠近','又抗拒','害怕靠近'),'conflict_avoidance':('不想冲突','忍下来','没说出来')}
    return {'dimension':'interpersonal','signals':[name for name,terms in cues.items() if any(term in text for term in terms)]}
