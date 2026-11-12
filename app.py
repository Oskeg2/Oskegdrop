import os
import hmac
import json
import hashlib
import time

from urllib.parse import parse_qsl
from uuid import uuid4

from dotenv import load_dotenv

load_dotenv()

import db
from store import get_products, get_product

from fastapi import FastAPI, HTTPException, Header
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from aiogram.types import LabeledPrice
import asyncio
from bot import bot, dp, BOT_TOKEN


app = FastAPI(title="OskegDrop API")

os.makedirs("web", exist_ok=True)

app.mount(
    "/static",
    StaticFiles(directory="web"),
    name="static"
)


class InvoiceRequest(BaseModel):
    product_id: str


def current_user(authorization: str | None):
    if not authorization:
        raise HTTPException(
            status_code=401,
            detail="Требуется авторизация Telegram"
        )

    if not authorization.startswith("tma "):
        raise HTTPException(
            status_code=401,
            detail="Неверный формат авторизации"
        )

    init_data = authorization[4:]

    if not init_data:
        raise HTTPException(401, "Нет данных Telegram")

    values = dict(parse_qsl(init_data))

    received_hash = values.pop("hash", None)

    if not received_hash:
        raise HTTPException(401, "Отсутствует подпись Telegram")

    data_check_string = "\n".join(
        f"{key}={value}"
        for key, value in sorted(values.items())
    )

    secret_key = hmac.new(
        b"WebAppData",
        BOT_TOKEN.encode(),
        hashlib.sha256
    ).digest()

    calculated_hash = hmac.new(
        secret_key,
        data_check_string.encode(),
        hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(calculated_hash, received_hash):
        raise HTTPException(401, "Проверка подписи не пройдена")

    try:
        auth_date = int(values.get("auth_date", "0"))
    except ValueError:
        raise HTTPException(401, "Неверная дата авторизации")

    now = int(time.time())

    if auth_date > now + 60 or now - auth_date > 86400:
        raise HTTPException(401, "Данные авторизации устарели")

    try:
        user = json.loads(values["user"])
        user_id = int(user["id"])
    except (KeyError, ValueError, TypeError, json.JSONDecodeError):
        raise HTTPException(401, "Не удалось определить пользователя")

    db.ensure_user(
        user_id,
        user.get("username") or user.get("first_name", "")
    )

    return user


polling_task = None


@app.on_event("startup")
async def startup():
    global polling_task

    db.init_db()
    polling_task = asyncio.create_task(
        dp.start_polling(bot)
    )


@app.on_event("shutdown")
async def shutdown():
    if polling_task:
        await dp.stop_polling()
        await polling_task

    await bot.session.close()


@app.get("/")
def index():
    return FileResponse("web/index.html")


@app.get("/api/me")
def me(
    authorization: str | None = Header(default=None)
):
    user = current_user(authorization)
    user_id = int(user["id"])

    account = db.get_user(user_id)

    return {
        "username": account["username"],
        "coins": account["coins"],
        "inventory": db.get_inventory(user_id)
    }


@app.get("/api/shop")
def shop():
    return {
        "products": get_products()
    }


@app.post("/api/bonus")
def daily_bonus(
    authorization: str | None = Header(default=None)
):
    user = current_user(authorization)
    user_id = int(user["id"])

    claimed = db.claim_daily_bonus(user_id)
    account = db.get_user(user_id)

    return {
        "claimed": claimed,
        "coins": account["coins"],
        "message": (
            "Получено 100 монет!"
            if claimed
            else "Сегодня бонус уже получен."
        )
    }


@app.get("/api/leaderboard")
def get_leaderboard():
    return {
        "players": db.leaderboard()
    }


@app.post("/api/invoice")
async def create_invoice(
    body: InvoiceRequest,
    authorization: str | None = Header(default=None)
):
    user = current_user(authorization)

    product = get_product(body.product_id)

    if not product:
        raise HTTPException(
            status_code=404,
            detail="Товар не найден"
        )

    order_id = str(uuid4())

    db.create_order(
        order_id,
        int(user["id"]),
        product["id"]
    )

    try:
        invoice_url = await bot.create_invoice_link(
            title=product["name"],
            description=product["description"],
            payload=order_id,
            provider_token="",
            currency="XTR",
            prices=[
                LabeledPrice(
                    label=product["name"],
                    amount=product["price"]
                )
            ]
        )

        return {
            "invoice_url": invoice_url
        }

    except Exception:
        raise HTTPException(
            status_code=500,
            detail="Не удалось создать ссылку оплаты"
      )
