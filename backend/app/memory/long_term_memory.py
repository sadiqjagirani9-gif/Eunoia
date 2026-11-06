ALLOWED_TYPES={'fact','self_report','confirmed_value','relationship'}

def validate(kind: str, confirmed: bool) -> None:
    if kind not in ALLOWED_TYPES:
        raise ValueError('unsupported long-term memory type')
    if kind in {'fact','confirmed_value','relationship'} and not confirmed:
        raise ValueError('this memory requires user confirmation')
