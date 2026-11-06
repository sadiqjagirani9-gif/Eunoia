DIMENSIONS=('emotion','thinking','interpersonal','values','behavior','self_concept')

def profile_shape(observations: list[dict]) -> dict:
    result={key:[] for key in DIMENSIONS}
    for row in observations:
        if row.get('dimension') in result and row.get('status') in ('confirmed','partially_confirmed','pending','uncertain','disputed'):
            result[row['dimension']].append(row)
    return result
