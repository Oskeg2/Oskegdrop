import os
import hashlib

from dotenv import load_dotenv

load_dotenv()

import re
_m = re.search(r"\d{5,}:[A-Za-z0-9_-]{20,}", os.getenv("BOT_TOKEN", ""))
BOT_TOKEN = _m.group(0) if _m else ""
print("TOKEN CHECK:", len(os.getenv("BOT_TOKEN", "")), bool(_m), flush=True)

WEBAPP_URL = os.getenv("WEBAPP_URL", "").rstrip("/")

# Если задан DATABASE_URL (Postgres) - данные живут там и не пропадают
# при "спячке" Render. Если нет - используется локальный SQLite файл.
DATABASE_URL = os.getenv("DATABASE_URL", "")
DATABASE_PATH = os.getenv("DATABASE_PATH", "oskegdrop_v2.db")

ADMIN_ID = int(os.getenv("ADMIN_ID", "0") or 0)
DEV_MODE = os.getenv("DEV_MODE", "false").lower() == "true"

WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET") or hashlib.sha256(
    (BOT_TOKEN or "dev").encode()
).hexdigest()[:40]

BONUS_STARS = int(os.getenv("BONUS_STARS", "5"))

MAX_BET = 5000
MINES_EDGE = 0.05      # комиссия сапёра
CRASH_EDGE = 0.04      # комиссия краша
CRASH_GROWTH = 0.1     # скорость роста множителя (в секунду)
UPGRADE_EDGE = 0.05    # комиссия апгрейда
MAX_WIN = 50000      # максимум выплаты за одну игру
