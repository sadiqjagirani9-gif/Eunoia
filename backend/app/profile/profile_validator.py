from .cognitive_profile import DIMENSIONS, LEGACY_DIMENSIONS

ALLOWED_DIMENSIONS=set(DIMENSIONS)|set(LEGACY_DIMENSIONS)
STATUSES={'pending','confirmed','partially_confirmed','rejected','disputed','uncertain'}
SOURCES={'user_report','observed_event','ai_inference'}

def validate(dimension: str, status: str, source_type: str) -> None:
    if dimension not in ALLOWED_DIMENSIONS or status not in STATUSES or source_type not in SOURCES:
        raise ValueError('invalid cognitive observation fields')
