from ..analysis import analyze

def extract(text: str) -> dict:
    signal=analyze(text)
    return {'dimension':'emotion','signals':signal['emotions'],'needs':signal['needs'],'safety_signal':signal['safety_signal']}
