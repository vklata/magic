from datetime import datetime, timezone
print(f"ISO with timezone: {datetime.now(timezone.utc).isoformat()}")
