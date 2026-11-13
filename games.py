import json
import math
import secrets
import time
from uuid import uuid4

import config
import db
from store import ACHIEVEMENTS, CASES, DEPOSITS, GIFTS, pick_drop


class GameError(Exception):
    pass


# ---------- общие помощники ----------

def _int(value, name="Значение"):
    try:
        return int(value)
    except (TypeError, ValueError):
        raise GameError(f"{name}: неверное число")


def _bet(value):
    bet = _int(value, "Ставка")
    if bet < 1 or bet > config.MAX_BET:
        raise GameError(f"Ставка от 1 до {config.MAX_BET} ⭐")
    return bet


def item_view(row):
    gift = GIFTS[row["gift_key"]]
    return {
        "id": row["id"], "key": gift["key"], "name": gift["name"],
        "emoji": gift["emoji"], "value": gift["value"], "type": gift["type"],
        "status": row.get("status", "owned"),
    }


def add_item(c, user_id, gift_key):
    row = c.one(
        "INSERT INTO inventory (user_id, gift_key, status, created_at) "
        "VALUES (?, ?, 'owned', ?) RETURNING id",
        (user_id, gift_key, db.now()),
    )
    return row["id"]


def check_achievements(c, user_id):
    stats = {r["stat"]: r["value"] for r in
             c.all("SELECT stat, value FROM stats WHERE user_id = ?", (user_id,))}
    have = {r["key"] for r in
            c.all("SELECT key FROM achievements WHERE user_id = ?", (user_id,))}
    new = []
    for a in ACHIEVEMENTS:
        if a["key"] not in have and stats.get(a["stat"], 0) >= a["need"]:
            c.run(
                "INSERT INTO achievements (user_id, key, unlocked_at) VALUES (?, ?, ?) "
                "ON CONFLICT DO NOTHING",
                (user_id, a["key"], db.now()),
            )
            new.append({"key": a["key"], "title": a["title"], "emoji": a["emoji"]})
    return new


def _wager(c, user_id, amount):
    db.bump(c, user_id, "wagered", amount)


# ---------- профиль ----------

def profile(user_id):
    with db.tx() as c:
        user = c.one("SELECT * FROM users WHERE user_id = ?", (user_id,))
        inventory = [item_view(r) for r in c.all(
            "SELECT * FROM inventory WHERE user_id = ? ORDER BY id DESC", (user_id,))
            if r["gift_key"] in GIFTS]
        stats = {r["stat"]: r["value"] for r in
                 c.all("SELECT stat, value FROM stats WHERE user_id = ?", (user_id,))}
        have = {r["key"] for r in
                c.all("SELECT key FROM achievements WHERE user_id = ?", (user_id,))}
    achievements = [{
        "key": a["key"], "title": a["title"], "emoji": a["emoji"], "desc": a["desc"],
        "need": a["need"], "progress": min(stats.get(a["stat"], 0), a["need"]),
        "unlocked": a["key"] in have,
    } for a in ACHIEVEMENTS]
    return {
        "username": user["username"], "stars": user["stars"],
        "inventory": inventory, "achievements": achievements,
    }


def daily_bonus(user_id):
    with db.tx() as c:
        changed = c.run(
            "UPDATE users SET last_bonus = ? WHERE user_id = ? AND last_bonus != ?",
            (db.today(), user_id, db.today()),
        )
        if changed == 1 and config.BONUS_STARS > 0:
            db.add_stars(c, user_id, config.BONUS_STARS, "daily_bonus")
        return changed == 1, db.balance(c, user_id)


def leaderboard(limit=10):
    with db.tx() as c:
        return c.all(
            "SELECT username, stars FROM users ORDER BY stars DESC LIMIT ?", (limit,))


# ---------- пополнение ----------

def create_deposit(user_id, amount):
    amount = _int(amount, "Сумма")
    if amount not in DEPOSITS:
        raise GameError("Неверная сумма пополнения")
    order_id = str(uuid4())
    with db.tx() as c:
        c.run(
            "INSERT INTO orders (order_id, user_id, amount, status, created_at) "
            "VALUES (?, ?, ?, 'pending', ?)",
            (order_id, user_id, amount, db.now()),
        )
    return order_id, amount


def get_order(order_id):
    with db.tx() as c:
        return c.one("SELECT * FROM orders WHERE order_id = ?", (order_id,))


def fulfill_deposit(order_id, charge_id=""):
    with db.tx() as c:
        order = c.one("SELECT * FROM orders WHERE order_id = ?", (order_id,))
        if not order:
            return None
        changed = c.run(
            "UPDATE orders SET status = 'paid', charge_id = ? "
            "WHERE order_id = ? AND status = 'pending'",
            (charge_id or "", order_id),
        )
        if changed != 1:
            return None
        db.add_stars(c, order["user_id"], order["amount"], f"deposit:{order_id}")
        db.bump(c, order["user_id"], "deposited", order["amount"])
        check_achievements(c, order["user_id"])
        return {"user_id": order["user_id"], "amount": order["amount"],
                "stars": db.balance(c, order["user_id"])}


# ---------- кейсы ----------

def open_case(user_id, case_id):
    case = CASES.get(case_id)
    if not case:
        raise GameError("Кейс не найден")
    with db.tx() as c:
        if not db.spend(c, user_id, case["price"], f"case:{case_id}"):
            raise GameError("Недостаточно звёзд")
        key = pick_drop(case["drops"])
        item_id = add_item(c, user_id, key)
        gift = GIFTS[key]
        db.bump(c, user_id, "cases")
        _wager(c, user_id, case["price"])
        db.set_max(c, user_id, "best_drop", gift["value"])
        if gift["type"] == "nft":
            db.bump(c, user_id, "nft_drops")
        new = check_achievements(c, user_id)
        stars = db.balance(c, user_id)
    item = item_view({"id": item_id, "gift_key": key, "status": "owned"})
    return {"item": item, "stars": stars, "achievements": new}


def sell_item(user_id, item_id):
    item_id = _int(item_id, "Предмет")
    with db.tx() as c:
        row = c.one(
            "SELECT * FROM inventory WHERE id = ? AND user_id = ? AND status = 'owned'",
            (item_id, user_id),
        )
        if not row or row["gift_key"] not in GIFTS:
            raise GameError("Предмет не найден")
        if c.run("DELETE FROM inventory WHERE id = ? AND user_id = ? AND status = 'owned'",
                 (item_id, user_id)) != 1:
            raise GameError("Предмет уже продан")
        value = GIFTS[row["gift_key"]]["value"]
        db.add_stars(c, user_id, value, f"sell:{row['gift_key']}")
        return {"sold": value, "stars": db.balance(c, user_id)}


# ---------- вывод подарков (вручную админом) ----------

def request_withdraw(user_id, item_id):
    item_id = _int(item_id, "Предмет")
    with db.tx() as c:
        row = c.one(
            "SELECT * FROM inventory WHERE id = ? AND user_id = ? AND status = 'owned'",
            (item_id, user_id),
        )
        if not row:
            raise GameError("Предмет не найден")
        if c.run("UPDATE inventory SET status = 'withdraw' WHERE id = ? AND user_id = ? "
                 "AND status = 'owned'", (item_id, user_id)) != 1:
            raise GameError("Предмет уже в выводе")
        req = c.one(
            "INSERT INTO withdrawals (user_id, item_id, gift_key, status, created_at) "
            "VALUES (?, ?, ?, 'pending', ?) RETURNING id",
            (user_id, item_id, row["gift_key"], db.now()),
        )
        return {"withdrawal_id": req["id"], "gift": GIFTS[row["gift_key"]]}


def pending_withdrawals():
    with db.tx() as c:
        return c.all(
            "SELECT w.id, w.user_id, w.gift_key, u.username FROM withdrawals w "
            "LEFT JOIN users u ON u.user_id = w.user_id "
            "WHERE w.status = 'pending' ORDER BY w.id")


def finish_withdrawal(withdrawal_id, approve=True):
    with db.tx() as c:
        w = c.one("SELECT * FROM withdrawals WHERE id = ? AND status = 'pending'",
                  (withdrawal_id,))
        if not w:
            return None
        c.run("UPDATE withdrawals SET status = ? WHERE id = ?",
              ("done" if approve else "rejected", withdrawal_id))
        if approve:
            c.run("DELETE FROM inventory WHERE id = ?", (w["item_id"],))
        else:
            c.run("UPDATE inventory SET status = 'owned' WHERE id = ?", (w["item_id"],))
        return w


def admin_add_stars(user_id, amount):
    with db.tx() as c:
        if not c.one("SELECT user_id FROM users WHERE user_id = ?", (user_id,)):
            return None
        db.add_stars(c, user_id, amount, "admin")
        return db.balance(c, user_id)


# ---------- апгрейд ----------

def upgrade_chance(value_in, value_target):
    return min(0.75, value_in / value_target * (1 - config.UPGRADE_EDGE))


def upgrade(user_id, item_ids, target_key):
    try:
        ids = list(dict.fromkeys(int(i) for i in item_ids))
    except (TypeError, ValueError):
        raise GameError("Неверные предметы")
    if not 1 <= len(ids) <= 5:
        raise GameError("Выбери от 1 до 5 предметов")
    target = GIFTS.get(target_key)
    if not target:
        raise GameError("Цель не найдена")
    marks = ",".join("?" * len(ids))
    with db.tx() as c:
        rows = c.all(
            f"SELECT id, gift_key FROM inventory WHERE user_id = ? AND status = 'owned' "
            f"AND id IN ({marks})", (user_id, *ids))
        if len(rows) != len(ids) or any(r["gift_key"] not in GIFTS for r in rows):
            raise GameError("Предметы не найдены")
        value_in = sum(GIFTS[r["gift_key"]]["value"] for r in rows)
        if target["value"] <= value_in:
            raise GameError("Цель должна быть дороже выбранных предметов")
        chance = upgrade_chance(value_in, target["value"])
        if chance < 0.01:
            raise GameError("Шанс слишком мал, выбери цель подешевле")
        if c.run(f"DELETE FROM inventory WHERE user_id = ? AND status = 'owned' "
                 f"AND id IN ({marks})", (user_id, *ids)) != len(ids):
            raise GameError("Предметы уже использованы")
        _wager(c, user_id, value_in)
        win = secrets.randbelow(10000) < int(chance * 10000)
        item = None
        if win:
            item_id = add_item(c, user_id, target_key)
            item = item_view({"id": item_id, "gift_key": target_key, "status": "owned"})
            db.bump(c, user_id, "upgrades")
        new = check_achievements(c, user_id)
        stars = db.balance(c, user_id)
    return {"win": win, "chance": round(chance * 100, 2), "item": item,
            "target": target, "stars": stars, "achievements": new}


# ---------- сапёр ----------

SIZE = 25


def mines_multiplier(mines, opened):
    if opened == 0:
        return 1.0
    return (1 - config.MINES_EDGE) * math.comb(SIZE, opened) / math.comb(SIZE - mines, opened)


def _mines_view(game, **extra):
    revealed = json.loads(game["revealed"])
    mult = mines_multiplier(game["mines"], len(revealed))
    safe_total = SIZE - game["mines"]
    nxt = mines_multiplier(game["mines"], len(revealed) + 1) if len(revealed) < safe_total else None
    view = {
        "active": game["status"] == "active", "bet": game["bet"], "mines": game["mines"],
        "revealed": revealed, "multiplier": round(mult, 4),
        "payout": min(math.floor(game["bet"] * mult), config.MAX_WIN),
        "next_multiplier": round(nxt, 4) if nxt else None,
    }
    view.update(extra)
    return view


def mines_state(user_id):
    with db.tx() as c:
        game = c.one("SELECT * FROM mines_games WHERE user_id = ? AND status = 'active' "
                     "ORDER BY id DESC LIMIT 1", (user_id,))
    return _mines_view(game) if game else {"active": False}


def mines_start(user_id, bet, mines):
    bet = _bet(bet)
    mines = _int(mines, "Мины")
    if not 1 <= mines <= 20:
        raise GameError("Мин должно быть от 1 до 20")
    with db.tx() as c:
        if c.one("SELECT id FROM mines_games WHERE user_id = ? AND status = 'active'", (user_id,)):
            raise GameError("Сначала закончи текущую игру")
        if not db.spend(c, user_id, bet, "mines_bet"):
            raise GameError("Недостаточно звёзд")
        cells = sorted(secrets.SystemRandom().sample(range(SIZE), mines))
        c.run("INSERT INTO mines_games (user_id, bet, mines, mine_cells, revealed, status, created_at) "
              "VALUES (?, ?, ?, ?, '[]', 'active', ?)",
              (user_id, bet, mines, json.dumps(cells), db.now()))
        _wager(c, user_id, bet)
        stars = db.balance(c, user_id)
        game = c.one("SELECT * FROM mines_games WHERE user_id = ? AND status = 'active' "
                     "ORDER BY id DESC LIMIT 1", (user_id,))
    return _mines_view(game, stars=stars)


def _mines_cashout(c, user_id, game):
    revealed = json.loads(game["revealed"])
    mult = mines_multiplier(game["mines"], len(revealed))
    payout = min(math.floor(game["bet"] * mult), config.MAX_WIN)
    if c.run("UPDATE mines_games SET status = 'cashed' WHERE id = ? AND status = 'active'",
             (game["id"],)) != 1:
        raise GameError("Игра уже завершена")
    db.add_stars(c, user_id, payout, "mines_win")
    db.bump(c, user_id, "mines_wins")
    db.set_max(c, user_id, "mines_best", int(mult * 100))
    return payout, mult


def mines_reveal(user_id, cell):
    cell = _int(cell, "Клетка")
    if not 0 <= cell < SIZE:
        raise GameError("Нет такой клетки")
    with db.tx() as c:
        game = c.one("SELECT * FROM mines_games WHERE user_id = ? AND status = 'active' "
                     "ORDER BY id DESC LIMIT 1", (user_id,))
        if not game:
            raise GameError("Нет активной игры")
        revealed = json.loads(game["revealed"])
        mine_cells = json.loads(game["mine_cells"])
        if cell in revealed:
            raise GameError("Клетка уже открыта")
        if cell in mine_cells:
            if c.run("UPDATE mines_games SET status = 'lost' WHERE id = ? AND status = 'active'",
                     (game["id"],)) != 1:
                raise GameError("Игра уже завершена")
            game["status"] = "lost"
            new = check_achievements(c, user_id)
            return _mines_view(game, result="lost", mine_cells=mine_cells, cell=cell,
                               win=0, stars=db.balance(c, user_id), achievements=new)
        updated = revealed + [cell]
        if c.run("UPDATE mines_games SET revealed = ? WHERE id = ? AND status = 'active' "
                 "AND revealed = ?", (json.dumps(updated), game["id"], game["revealed"])) != 1:
            raise GameError("Повтори нажатие")
        game["revealed"] = json.dumps(updated)
        if len(updated) == SIZE - game["mines"]:
            payout, _ = _mines_cashout(c, user_id, game)
            game["status"] = "cashed"
            new = check_achievements(c, user_id)
            return _mines_view(game, result="cashed", mine_cells=mine_cells, win=payout,
                               stars=db.balance(c, user_id), achievements=new)
        return _mines_view(game, result="safe", cell=cell)


def mines_cashout(user_id):
    with db.tx() as c:
        game = c.one("SELECT * FROM mines_games WHERE user_id = ? AND status = 'active' "
                     "ORDER BY id DESC LIMIT 1", (user_id,))
        if not game:
            raise GameError("Нет активной игры")
        if not json.loads(game["revealed"]):
            raise GameError("Открой хотя бы одну клетку")
        mine_cells = json.loads(game["mine_cells"])
        payout, _ = _mines_cashout(c, user_id, game)
        game["status"] = "cashed"
        new = check_achievements(c, user_id)
        return _mines_view(game, result="cashed", mine_cells=mine_cells, win=payout,
                           stars=db.balance(c, user_id), achievements=new)


# ---------- краш ----------

def new_crash_point():
    r = secrets.randbelow(10 ** 9) / 10 ** 9
    point = (1 - config.CRASH_EDGE) / (1 - r)
    return max(1.0, min(math.floor(point * 100) / 100, 1000.0))


def mult_at(elapsed):
    return math.exp(config.CRASH_GROWTH * max(0.0, elapsed))


def _crash_finish(c, game, status, mult):
    """Фиксирует итог раунда. Возвращает dict или None, если уже закрыт."""
    mult = math.floor(mult * 100) / 100
    payout = min(math.floor(game["bet"] * mult), config.MAX_WIN) if status == "cashed" else 0
    if c.run("UPDATE crash_games SET status = ?, payout = ?, final_mult = ? "
             "WHERE id = ? AND status = 'active'", (status, payout, mult, game["id"])) != 1:
        return None
    if status == "cashed":
        db.add_stars(c, game["user_id"], payout, "crash_win")
        db.bump(c, game["user_id"], "crash_wins")
        db.set_max(c, game["user_id"], "crash_best", int(mult * 100))
    new = check_achievements(c, game["user_id"])
    return {"status": status, "multiplier": mult, "payout": payout,
            "crash_point": game["crash_point"], "bet": game["bet"],
            "stars": db.balance(c, game["user_id"]), "achievements": new}


def _crash_settle(c, game, now):
    """None - раунд ещё идёт; иначе итог (авто-вывод или крэш)."""
    elapsed = now - game["started_at"]
    current = mult_at(elapsed)
    auto = game["auto_cashout"]
    if auto and auto < game["crash_point"] and current >= auto:
        return _crash_finish(c, game, "cashed", auto) or {"status": "closed"}
    if current >= game["crash_point"]:
        return _crash_finish(c, game, "crashed", game["crash_point"]) or {"status": "closed"}
    return None


def _active_crash(c, user_id):
    return c.one("SELECT * FROM crash_games WHERE user_id = ? AND status = 'active' "
                 "ORDER BY id DESC LIMIT 1", (user_id,))


def crash_start(user_id, bet, auto=None):
    bet = _bet(bet)
    if auto in (None, "", 0):
        auto = None
    else:
        try:
            auto = float(auto)
        except (TypeError, ValueError):
            raise GameError("Неверный авто-вывод")
        if auto < 1.01 or auto > 1000:
            raise GameError("Авто-вывод от 1.01 до 1000")
        auto = math.floor(auto * 100) / 100
    with db.tx() as c:
        old = _active_crash(c, user_id)
        if old and _crash_settle(c, old, time.time()) is None:
            raise GameError("Раунд уже идёт")
        if not db.spend(c, user_id, bet, "crash_bet"):
            raise GameError("Недостаточно звёзд")
        _wager(c, user_id, bet)
        c.run("INSERT INTO crash_games (user_id, bet, crash_point, auto_cashout, started_at, status) "
              "VALUES (?, ?, ?, ?, ?, 'active')",
              (user_id, bet, new_crash_point(), auto, time.time()))
        stars = db.balance(c, user_id)
    return {"status": "running", "multiplier": 1.0, "elapsed": 0.0,
            "bet": bet, "auto": auto, "stars": stars}


def crash_state(user_id):
    with db.tx() as c:
        game = _active_crash(c, user_id)
        if not game:
            return {"status": "idle"}
        now = time.time()
        done = _crash_settle(c, game, now)
        if done:
            return done
        elapsed = now - game["started_at"]
        return {"status": "running", "multiplier": round(mult_at(elapsed), 4),
                "elapsed": round(elapsed, 3), "bet": game["bet"], "auto": game["auto_cashout"]}


def crash_cashout(user_id):
    with db.tx() as c:
        game = _active_crash(c, user_id)
        if not game:
            raise GameError("Нет активного раунда")
        now = time.time()
        done = _crash_settle(c, game, now)
        if done:
            return done
        result = _crash_finish(c, game, "cashed", mult_at(now - game["started_at"]))
        if not result:
            raise GameError("Раунд уже завершён")
        return result
