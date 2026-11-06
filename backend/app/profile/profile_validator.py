DIMENSIONS={'emotion','thinking','interpersonal','values','behavior','self_concept'}
STATUSES={'pending','confirmed','partially_confirmed','rejected','disputed','uncertain'}
SOURCES={'user_report','observed_event','ai_inference'}

def validate(dimension: str, status: str, source_type: str) -> None:
    if dimension not in DIMENSIONS or status not in STATUSES or source_type not in SOURCES:
        raise ValueError('invalid cognitive observation fields')
