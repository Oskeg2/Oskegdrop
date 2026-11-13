import secrets

# value - стоимость подарка в звёздах (цена продажи в игре).
# NFT-подарки: значения условные, поменяй под себя.
GIFTS = {
    "heart":     {"name": "Heart",          "emoji": "💝", "value": 15,    "type": "gift"},
    "bear":      {"name": "Bear",           "emoji": "🧸", "value": 15,    "type": "gift"},
    "box":       {"name": "Gift",           "emoji": "🎁", "value": 25,    "type": "gift"},
    "rose":      {"name": "Rose",           "emoji": "🌹", "value": 25,    "type": "gift"},
    "cake":      {"name": "Cake",           "emoji": "🎂", "value": 50,    "type": "gift"},
    "bouquet":   {"name": "Bouquet",        "emoji": "💐", "value": 50,    "type": "gift"},
    "rocket":    {"name": "Rocket",         "emoji": "🚀", "value": 50,    "type": "gift"},
    "champagne": {"name": "Champagne",      "emoji": "🍾", "value": 50,    "type": "gift"},
    "trophy":    {"name": "Trophy",         "emoji": "🏆", "value": 100,   "type": "gift"},
    "ring":      {"name": "Ring",           "emoji": "💍", "value": 100,   "type": "gift"},
    "diamond":   {"name": "Diamond",        "emoji": "💎", "value": 100,   "type": "gift"},
    "peach":     {"name": "Precious Peach", "emoji": "🍑", "value": 300,   "type": "nft"},
    "signet":    {"name": "Signet Ring",    "emoji": "💠", "value": 500,   "type": "nft"},
    "swiss":     {"name": "Swiss Watch",    "emoji": "⌚", "value": 1000,  "type": "nft"},
    "loot":      {"name": "Loot Bag",       "emoji": "👜", "value": 2000,  "type": "nft"},
    "cap":       {"name": "Durov's Cap",    "emoji": "🧢", "value": 10000, "type": "nft"},
    "pepe":      {"name": "Plush Pepe",     "emoji": "🐸", "value": 50000, "type": "nft"},
}

for _key, _gift in GIFTS.items():
    _gift["key"] = _key

# drops: подарок -> вес (в процентах, в сумме 100).
# RTP (возврат игроку) ~ 85-90%, остальное - комиссия.
CASES = {
    "basic": {
        "id": "basic", "name": "Базовый кейс", "emoji": "📦", "price": 25,
        "drops": {"heart": 30, "bear": 30, "box": 15, "rose": 14,
                  "cake": 6, "rocket": 4.5, "trophy": 0.5},
    },
    "mid": {
        "id": "mid", "name": "Серебряный кейс", "emoji": "🎁", "price": 100,
        "drops": {"box": 3, "rose": 3, "cake": 10, "bouquet": 10, "rocket": 10,
                  "champagne": 10, "trophy": 20, "ring": 15, "diamond": 13,
                  "peach": 6},
    },
    "premium": {
        "id": "premium", "name": "Золотой кейс", "emoji": "👑", "price": 300,
        "drops": {"cake": 4, "champagne": 4, "trophy": 14, "ring": 14,
                  "diamond": 14, "peach": 34, "signet": 12, "swiss": 3.5,
                  "loot": 0.45, "cap": 0.05},
    },
    "legend": {
        "id": "legend", "name": "NFT кейс", "emoji": "🌌", "price": 1000,
        "drops": {"trophy": 2, "ring": 2, "diamond": 2, "peach": 8,
                  "signet": 39, "swiss": 30, "loot": 16.6, "cap": 0.38,
                  "pepe": 0.02},
    },
}

DEPOSITS = [25, 50, 100, 250, 500, 1000]

_ACH = [
    ("first_deposit", "Первый шаг",       "💳", "Пополни баланс",              "deposited",  1),
    ("first_case",    "Первый кейс",      "📦", "Открой кейс",                 "cases",      1),
    ("cases_10",      "Коллекционер",     "🗃️", "Открой 10 кейсов",            "cases",      10),
    ("cases_100",     "Кейсовый маньяк",  "🏭", "Открой 100 кейсов",           "cases",      100),
    ("big_drop",      "Крутой дроп",      "💎", "Выбей подарок от 300 ⭐",     "best_drop",  300),
    ("nft_drop",      "NFT-охотник",      "🖼️", "Выбей NFT-подарок",           "nft_drops",  1),
    ("upgrade_win",   "Апгрейднул",       "⚡", "Выиграй апгрейд",             "upgrades",   1),
    ("upgrade_5",     "Мастер апгрейда",  "🔥", "Выиграй 5 апгрейдов",         "upgrades",   5),
    ("mines_cash",    "Сапёр",            "💣", "Забери выигрыш в сапёре",     "mines_wins", 1),
    ("mines_x5",      "Стальные нервы",   "🧠", "Забери x5 в сапёре",          "mines_best", 500),
    ("crash_win",     "Взлёт",            "🚀", "Выиграй в краше",             "crash_wins", 1),
    ("crash_x10",     "На луну",          "🌙", "Забери x10 в краше",          "crash_best", 1000),
    ("wager_1000",    "Игрок",            "🎰", "Сделай ставок на 1000 ⭐",    "wagered",    1000),
]

ACHIEVEMENTS = [
    {"key": k, "title": t, "emoji": e, "desc": d, "stat": s, "need": n}
    for k, t, e, d, s, n in _ACH
]


def pick_drop(drops: dict) -> str:
    total = int(sum(drops.values()) * 1000)
    roll = secrets.randbelow(total)
    acc = 0
    for key, weight in drops.items():
        acc += int(weight * 1000)
        if roll < acc:
            return key
    return next(iter(drops))


def cases_public():
    result = []
    for case in CASES.values():
        total = sum(case["drops"].values())
        drops = [
            {**GIFTS[k], "chance": round(w / total * 100, 3)}
            for k, w in sorted(case["drops"].items(), key=lambda x: -GIFTS[x[0]]["value"])
        ]
        result.append({k: case[k] for k in ("id", "name", "emoji", "price")} | {"drops": drops})
    return result
