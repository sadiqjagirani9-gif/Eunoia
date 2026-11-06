from datetime import datetime, timedelta, timezone

def expiry(days: int = 30) -> str:
    return (datetime.now(timezone.utc) + timedelta(days=max(1, min(days, 365)))).strftime('%Y-%m-%d %H:%M:%S')
