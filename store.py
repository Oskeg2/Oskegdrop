PRODUCTS = {
    "starter": {
        "id": "starter",
        "name": "Starter Pack",
        "description": "Стартовый набор: 500 монет и 2 предмета",
        "price": 30,
        "coins": 500,
        "items": [
            "Purple Sword",
            "Neon Badge"
        ]
    },
    "purple": {
        "id": "purple",
        "name": "Purple Pack",
        "description": "Фиолетовый набор: 1500 монет и 3 предмета",
        "price": 75,
        "coins": 1500,
        "items": [
            "Purple Sword",
            "Neon Wings",
            "Dark Crown"
        ]
    },
    "elite": {
        "id": "elite",
        "name": "Elite Pack",
        "description": "Элитный набор: 4000 монет и 4 предмета",
        "price": 150,
        "coins": 4000,
        "items": [
            "Elite Sword",
            "Neon Wings",
            "Dark Crown",
            "Galaxy Aura"
        ]
    }
}


def get_product(product_id: str):
    return PRODUCTS.get(product_id)


def get_products():
    return list(PRODUCTS.values())
