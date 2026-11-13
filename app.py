import hashlib
import hmac
import json
import time
from urllib.parse import parse_qsl

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from aiogram.types import LabeledPrice, Update

import config
import db
import games
from bot import bot, dp
from games import GameError
from store import CASES, DEPOSITS, GIFTS, cases_public

app = FastAPI(title="OskegDrop API")

import asyncio

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(dp.start_polling(bot))

app.mount("/static", StaticFiles(directory="web"), name="static")


@app.exception_handler(GameError)
async def game_error_handler(request: Request, exc: GameError):
    return JSONResponse(status_code=400, content={"detail": str(exc)})


# ---------- авторизация Telegram ----------

def current_user(authorization: str | None):
    if not authorization or not authorization.startswith("tma "):
        if config.DEV_MODE:
            db.ensure_user(1, "dev")
            return {"id": 1, "username": "dev"}
        raise HTTPException(401, "Открой Mini App через Telegram")

    values = dict(parse_qsl(authorization[4:]))
    received_hash = values.pop("hash", None)
    if not received_hash:
        raise HTTPException(401, "Отсутствует подпись Telegram")

    check = "\n".join(f"{k}={v}" for k, v in sorted(values.items()))
    secret = hmac.new(b"WebAppData", config.BOT_TOKEN.encode(), hashlib.sha256).digest()
    calculated = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(calculated, received_hash):
        raise HTTPException(401, "Проверка подписи не пройдена")

    try:
        auth_date = int(values.get("auth_date", "0"))
    except ValueError:
        raise HTTPException(401, "Неверная дата авторизации")
    now = int(time.time())
    if auth_date > now + 60 or now - auth_date > 86400:
        raise HTTPException(401, "Данные авторизации устарели, перезапусти Mini App")

    try:
        user = json.loads(values["user"])
        user_id = int(user["id"])
    except (KeyError, ValueError, TypeError, json.JSONDecodeError):
        raise HTTPException(401, "Не удалось определить пользователя")

    db.ensure_user(user_id, user.get("username") or user.get("first_name", ""))
    return user


def uid(authorization):
    return int(current_user(authorization)["id"])


# ---------- запуск / webhook ----------

@app.on_event("startup")
async def startup():
    db.init_db()
    if config.WEBAPP_URL.startswith("https://"):
        await bot.set_webhook(
            f"{config.WEBAPP_URL}/webhook/{config.WEBHOOK_SECRET}",
            secret_token=config.WEBHOOK_SECRET,
            allowed_updates=dp.resolve_used_update_types(),
        )


@app.on_event("shutdown")
async def shutdown():
    await bot.session.close()


@app.post("/webhook/{secret}")
async def webhook(secret: str, request: Request):
    header = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    if secret != config.WEBHOOK_SECRET or header != config.WEBHOOK_SECRET:
        raise HTTPException(403, "Forbidden")
    update = Update.model_validate(await request.json(), context={"bot": bot})
    await dp.feed_update(bot, update)
    return {"ok": True}


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/")
def index():
    return FileResponse("web/index.html")


# ---------- профиль / конфиг ----------

@app.get("/api/config")
def get_config():
    return {
        "cases": cases_public(),
        "gifts": list(GIFTS.values()),
        "deposits": DEPOSITS,
        "max_bet": config.MAX_BET,
        "upgrade_edge": config.UPGRADE_EDGE,
        "crash_growth": config.CRASH_GROWTH,
        "bonus": config.BONUS_STARS,
    }


@app.get("/api/me")
def me(authorization: str | None = Header(default=None)):
    return games.profile(uid(authorization))


@app.post("/api/bonus")
def bonus(authorization: str | None = Header(default=None)):
    claimed, stars = games.daily_bonus(uid(authorization))
    return {
        "claimed": claimed, "stars": stars,
        "message": f"Получено {config.BONUS_STARS} ⭐!" if claimed else "Сегодня бонус уже получен.",
    }


@app.get("/api/leaderboard")
def leaderboard():
    return {"players": games.leaderboard()}


# ---------- пополнение ----------

class DepositBody(BaseModel):
    amount: int


@app.post("/api/invoice")
async def invoice(body: DepositBody, authorization: str | None = Header(default=None)):
    user_id = uid(authorization)
    order_id, amount = games.create_deposit(user_id, body.amount)
    try:
        url = await bot.create_invoice_link(
            title=f"Пополнение {amount} ⭐",
            description=f"Пополнение баланса OskegDrop на {amount} ⭐",
            payload=order_id,
            provider_token="",
            currency="XTR",
            prices=[LabeledPrice(label=f"{amount} ⭐", amount=amount)],
        )
    except Exception:
        raise HTTPException(500, "Не удалось создать ссылку оплаты")
    return {"invoice_url": url}


# ---------- кейсы / инвентарь ----------

class CaseBody(BaseModel):
    case_id: str


class ItemBody(BaseModel):
    item_id: int


class UpgradeBody(BaseModel):
    item_ids: list[int]
    target: str


@app.post("/api/case/open")
def case_open(body: CaseBody, authorization: str | None = Header(default=None)):
    return games.open_case(uid(authorization), body.case_id)


@app.post("/api/sell")
def sell(body: ItemBody, authorization: str | None = Header(default=None)):
    return games.sell_item(uid(authorization), body.item_id)


@app.post("/api/withdraw")
async def withdraw(body: ItemBody, authorization: str | None = Header(default=None)):
    user = current_user(authorization)
    result = games.request_withdraw(int(user["id"]), body.item_id)
    if config.ADMIN_ID:
        try:
            await bot.send_message(
                config.ADMIN_ID,
                f"🎁 Заявка на вывод #{result['withdrawal_id']}\n"
                f"{result['gift']['emoji']} {result['gift']['name']}\n"
                f"Игрок: @{user.get('username') or '-'} (id {user['id']})\n\n"
                f"Отправь подарок вручную и напиши /done {result['withdrawal_id']}",
            )
        except Exception:
            pass
    return {"ok": True}


@app.post("/api/upgrade")
def upgrade(body: UpgradeBody, authorization: str | None = Header(default=None)):
    return games.upgrade(uid(authorization), body.item_ids, body.target)


# ---------- сапёр ----------

class MinesStart(BaseModel):
    bet: int
    mines: int


class MinesReveal(BaseModel):
    cell: int


@app.get("/mines_state")
def mines_state(authorization: str | None = Header(default=None)):
    return games.mines_state(uid(authorization))


@app.post("/mines_bet")
def mines_start(body: MinesStart, authorization: str | None = Header(default=None)):
    return games.mines_start(uid(authorization), body.bet, body.mines)


@app.post("/mines_reveal")
def mines_reveal(body: MinesReveal, authorization: str | None = Header(default=None)):
    return games.mines_reveal(uid(authorization), body.cell)


@app.post("/mines_cashout")
def mines_cashout(authorization: str | None = Header(default=None)):
    return games.mines_cashout(uid(authorization))


# ---------- краш ----------

class CrashStart(BaseModel):
    bet: int
    auto: float | None = None


@app.get("/crash_state")
def crash_state(authorization: str | None = Header(default=None)):
    return games.crash_state(uid(authorization))


@app.post("/crash_bet")
def crash_start(body: CrashStart, authorization: str | None = Header(default=None)):
    return games.crash_start(uid(authorization), body.bet, body.auto)


@app.post("/crash_cashout")
def crash_cashout(authorization: str | None = Header(default=None)):
    return games.crash_cashout(uid(authorization))
