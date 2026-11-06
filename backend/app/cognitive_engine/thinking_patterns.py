from ..analysis import analyze

def extract(text: str) -> dict:
    signal=analyze(text)
    return {'dimension':'thinking','signals':signal['cognitive_patterns'],'conflicts':signal['conflicts']}
