from ..cognitive_engine import behavior_analysis, emotion_patterns, interpersonal_patterns, self_concept, thinking_patterns, value_analysis

EXTRACTORS=(emotion_patterns.extract,thinking_patterns.extract,interpersonal_patterns.extract,value_analysis.extract,behavior_analysis.extract,self_concept.extract)

def extract_signals(text: str) -> list[dict]:
    results=[]
    for extractor in EXTRACTORS:
        data=extractor(text)
        signals=data.get('signals') or data.get('self_statements') or []
        for signal in signals:
            results.append({'dimension':data['dimension'],'statement':str(signal),'evidence':text[:1200]})
    return results
