import asyncio

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    PreCheckoutQuery,
)

import config
import db
import games

if not config.BOT_TOKEN:
    raise RuntimeError("Не указан BOT_TOKEN")

BOT_TOKEN = config.BOT_TOKEN
bot = Bot(token="9060799786:AAF4jBS6DsQGzkzoreLYMJe7g33rc3PjWxk")
dp = Dispatcher()


def is_admin(message: Message) -> bool:
    return bool(config.ADMIN_ID) and message.from_user.id == config.ADMIN_ID


@dp.message(CommandStart())
async def start(message: Message):
    user = message.from_user
    db.ensure_user(user.id, user.username or user.first_name or "")

    if not config.WEBAPP_URL.startswith("https://"):
        await message.answer("Mini App пока не настроен. Укажи HTTPS-адрес в WEBAPP_URL.")
        return

    keyboard = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🚀 Открыть OskegDrop", web_app={"url": config.WEBAPP_URL})
    ]])
    await message.answer(
        "🌌 Добро пожаловать в OskegDrop!\n\n"
        "Открывай кейсы за ⭐, выбивай подарки Telegram и NFT, "
        "делай апгрейды, играй в сапёр и краш.",
        reply_markup=keyboard,
    )


@dp.pre_checkout_query()
async def pre_checkout(query: PreCheckoutQuery):
    order = games.get_order(query.invoice_payload)
    if not order:
        return await query.answer(ok=False, error_message="Заказ не найден.")
    if order["user_id"] != query.from_user.id:
        return await query.answer(ok=False, error_message="Заказ другого пользователя.")
    if order["status"] != "pending":
        return await query.answer(ok=False, error_message="Заказ уже обработан.")
    if query.currency != "XTR" or query.total_amount != order["amount"]:
        return await query.answer(ok=False, error_message="Неверная сумма.")
    await query.answer(ok=True)


@dp.message(F.successful_payment)
async def successful_payment(message: Message):
    payment = message.successful_payment
    order = games.get_order(payment.invoice_payload)

    if (not order or order["user_id"] != message.from_user.id
            or payment.currency != "XTR" or payment.total_amount != order["amount"]):
        await message.answer("Платёж получен, но проверка не прошла. Напиши в поддержку.")
        return

    result = games.fulfill_deposit(
        payment.invoice_payload, payment.telegram_payment_charge_id)
    if not result:
        await message.answer("Этот платёж уже зачислен.")
        return

    await message.answer(
        f"✅ Баланс пополнен на {result['amount']} ⭐\n"
        f"Сейчас у тебя: {result['stars']} ⭐"
    )


# ---------- команды админа ----------

@dp.message(Command("withdrawals"))
async def cmd_withdrawals(message: Message):
    if not is_admin(message):
        return
    rows = games.pending_withdrawals()
    if not rows:
        await message.answer("Заявок на вывод нет.")
        return
    text = "\n".join(
        f"#{r['id']} · {r['gift_key']} · @{r['username'] or '-'} (id {r['user_id']})"
        for r in rows
    )
    await message.answer(
        text + "\n\nОтправь подарок игроку вручную, потом /done <номер>.\n"
        "Отклонить: /reject <номер>"
    )


async def _finish(message: Message, approve: bool):
    if not is_admin(message):
        return
    parts = (message.text or "").split()
    if len(parts) != 2 or not parts[1].isdigit():
        await message.answer("Формат: /done 12")
        return
    w = games.finish_withdrawal(int(parts[1]), approve)
    if not w:
        await message.answer("Заявка не найдена или уже закрыта.")
        return
    await message.answer("Готово.")
    try:
        await bot.send_message(
            w["user_id"],
            "🎁 Твой подарок отправлен!" if approve
            else "Вывод отклонён, предмет вернулся в инвентарь.",
        )
    except Exception:
        pass


@dp.message(Command("done"))
async def cmd_done(message: Message):
    await _finish(message, True)


@dp.message(Command("reject"))
async def cmd_reject(message: Message):
    await _finish(message, False)


@dp.message(Command("addstars"))
async def cmd_addstars(message: Message):
    if not is_admin(message):
        return
    parts = (message.text or "").split()
    try:
        user_id, amount = int(parts[1]), int(parts[2])
    except (IndexError, ValueError):
        await message.answer("Формат: /addstars <user_id> <сумма>")
        return
    stars = games.admin_add_stars(user_id, amount)
    await message.answer("Игрок не найден." if stars is None else f"Баланс игрока: {stars} ⭐")


async def main():
    """Локальный запуск через polling (на Render используется webhook)."""
    db.init_db()
    await bot.delete_webhook()
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
