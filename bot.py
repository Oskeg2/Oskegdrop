import asyncio
import os

from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import (
    Message,
    LabeledPrice,
    PreCheckoutQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton
)

import db
from store import get_product

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    raise RuntimeError("Не указан BOT_TOKEN в .env")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


@dp.message(CommandStart())
async def start(message: Message):
    user = message.from_user

    db.ensure_user(
        user.id,
        user.username or user.first_name or ""
    )

    webapp_url = os.getenv("WEBAPP_URL", "")

    if not webapp_url.startswith("https://"):
        await message.answer(
            "Mini App пока не настроен. "
            "Укажи HTTPS-адрес в WEBAPP_URL."
        )
        return

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[[
            InlineKeyboardButton(
                text="🚀 Открыть OskegDrop",
                web_app={"url": webapp_url}
            )
        ]]
    )

    await message.answer(
        "🌌 Добро пожаловать в OskegDrop!\n\n"
        "Собирай предметы, получай ежедневные монеты "
        "и посещай магазин.",
        reply_markup=keyboard
    )


@dp.pre_checkout_query()
async def pre_checkout(query: PreCheckoutQuery):
    order = db.get_order(query.invoice_payload)

    if not order:
        await query.answer(
            ok=False,
            error_message="Заказ не найден."
        )
        return

    if order["user_id"] != query.from_user.id:
        await query.answer(
            ok=False,
            error_message="Этот заказ принадлежит другому пользователю."
        )
        return

    if order["status"] != "pending":
        await query.answer(
            ok=False,
            error_message="Заказ уже обработан."
        )
        return

    product = get_product(order["product_id"])

    if not product:
        await query.answer(
            ok=False,
            error_message="Товар не найден."
        )
        return

    if query.currency != "XTR":
        await query.answer(
            ok=False,
            error_message="Неверная валюта."
        )
        return

    if query.total_amount != product["price"]:
        await query.answer(
            ok=False,
            error_message="Неверная сумма."
        )
        return

    await query.answer(ok=True)


@dp.message(F.successful_payment)
async def successful_payment(message: Message):
    payment = message.successful_payment
    order_id = payment.invoice_payload

    order = db.get_order(order_id)

    if not order:
        await message.answer(
            "Платёж получен, но заказ не найден. "
            "Обратись в поддержку."
        )
        return

    if order["user_id"] != message.from_user.id:
        await message.answer(
            "Не удалось проверить владельца заказа. "
            "Обратись в поддержку."
        )
        return

    product = get_product(order["product_id"])

    if not product:
        await message.answer("Товар заказа не найден.")
        return

    if payment.currency != "XTR":
        await message.answer("Ошибка проверки валюты.")
        return

    if payment.total_amount != product["price"]:
        await message.answer("Ошибка проверки суммы платежа.")
        return

    completed = db.fulfill_order(
        order_id,
        product["coins"],
        product["items"]
    )

    if not completed:
        await message.answer(
            "Этот заказ уже обработан или ожидает проверки."
        )
        return

    items = "\n".join(
        f"• {item}" for item in product["items"]
    )

    await message.answer(
        "✅ Покупка завершена!\n\n"
        f"Набор: {product['name']}\n"
        f"Монеты: +{product['coins']}\n\n"
        f"Предметы:\n{items}\n\n"
        "Открой Mini App, чтобы посмотреть инвентарь."
    )


async def main():
    db.init_db()
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
