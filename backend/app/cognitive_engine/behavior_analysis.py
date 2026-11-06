def extract(text: str) -> dict:
    cues={'direct_action':('我主动','我去沟通','我提出了'),'avoidance':('我躲开','我回避','一直没说'),'rumination':('反复想','一直在想','想了很多次'),'external_advice':('问了朋友','听听别人意见'),'delayed_decision':('还没决定','拖到现在','再等等')}
    return {'dimension':'behavior','signals':[name for name,terms in cues.items() if any(term in text for term in terms)]}
