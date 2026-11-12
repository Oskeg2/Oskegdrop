const tg = window.Telegram?.WebApp;

if (tg) {
    tg.ready();
    tg.expand();
    tg.setHeaderColor("#090710");
    tg.setBackgroundColor("#090710");
}

const initData = tg?.initData || "";

const headers = {
    "Content-Type": "application/json",
    "Authorization": `tma ${initData}`
};

const $ = (id) => document.getElementById(id);

function toast(message) {
    const element = $("toast");
    element.textContent = message;
    element.classList.add("show");

    setTimeout(() => {
        element.classList.remove("show");
    }, 2500);
}

async function api(url, options = {}) {
    const response = await fetch(url, {
        ...options,
        headers: {
            ...headers,
            ...(options.headers || {})
        }
    });

    const data = await response.json().catch(() => ({}));

    if (!response.ok) {
        throw new Error(data.detail || "Произошла ошибка");
    }

    return data;
}

function escapeHTML(value) {
    return String(value).replace(/[&<>"']/g, char => ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#039;"
    })[char]);
}

function switchPage(pageName) {
    document.querySelectorAll(".page").forEach(page => {
        page.classList.toggle("active", page.id === pageName);
    });

    document.querySelectorAll(".tab").forEach(tab => {
        tab.classList.toggle(
            "active",
            tab.dataset.page === pageName
        );
    });

    if (pageName === "inventory") loadProfile();
    if (pageName === "rating") loadLeaderboard();
    if (pageName === "shop") loadShop();
}

document.querySelectorAll(".tab").forEach(tab => {
    tab.addEventListener("click", () => {
        switchPage(tab.dataset.page);
    });
});

async function loadProfile() {
    try {
        const data = await api("/api/me");

        $("balance").textContent = data.coins;
        $("username").textContent = data.username || "Игрок";

        const items = $("items");

        if (!data.inventory.length) {
            items.innerHTML = `
                <p class="muted">
                    Инвентарь пока пуст. Посети магазин!
                </p>
            `;
            return;
        }

        items.innerHTML = data.inventory.map(item => `
            <div class="item-card">
                <span class="item-icon">✨</span>
                <span>${escapeHTML(item)}</span>
            </div>
        `).join("");

    } catch (error) {
        toast(error.message);
    }
}

async function loadShop() {
    try {
        const data = await api("/api/shop");

        $("products").innerHTML = data.products.map(product => `
            <article class="product-card">
                <h3>${escapeHTML(product.name)}</h3>
                <p>${escapeHTML(product.description)}</p>

                <ul class="product-items">
                    ${product.items.map(item => `
                        <li>${escapeHTML(item)}</li>
                    `).join("")}
                </ul>

                <p class="product-price">
                    +${product.coins} монет
                    · ${product.price} ⭐
                </p>

                <button
                    class="primary-button"
                    onclick="buyProduct('${escapeHTML(product.id)}')"
                >
                    Купить за ${product.price} ⭐
                </button>
            </article>
        `).join("");

    } catch (error) {
        $("products").innerHTML = `
            <p class="muted">${escapeHTML(error.message)}</p>
        `;
    }
}

async function buyProduct(productId) {
    if (!tg || !initData) {
        toast("Открой Mini App через Telegram.");
        return;
    }

    try {
        const data = await api("/api/invoice", {
            method: "POST",
            body: JSON.stringify({
                product_id: productId
            })
        });

        tg.openInvoice(data.invoice_url, async (status) => {
            if (status === "paid") {
                toast("Покупка завершена!");
                await loadProfile();
                await loadShop();
            } else if (status === "cancelled") {
                toast("Покупка отменена.");
            } else if (status === "failed") {
                toast("Не удалось провести оплату.");
            }
        });

    } catch (error) {
        toast(error.message);
    }
}

window.buyProduct = buyProduct;

$("bonusButton").addEventListener("click", async () => {
    const button = $("bonusButton");
    button.disabled = true;

    try {
        const data = await api("/api/bonus", {
            method: "POST"
        });

        $("balance").textContent = data.coins;
        toast(data.message);

        if (data.claimed) {
            button.textContent = "Бонус получен";
        }

    } catch (error) {
        toast(error.message);
    } finally {
        button.disabled = false;
    }
});

async function loadLeaderboard() {
    try {
        const data = await api("/api/leaderboard");

        if (!data.players.length) {
            $("leaderboard").innerHTML = `
                <p class="muted">Пока нет игроков.</p>
            `;
            return;
        }

        $("leaderboard").innerHTML = data.players.map(
            (player, index) => `
                <div class="leader-row">
                    <span>
                        ${index + 1}. ${escapeHTML(player.username || "Игрок")}
                    </span>
                    <strong>🪙 ${player.coins}</strong>
                </div>
            `
        ).join("");

    } catch (error) {
        $("leaderboard").innerHTML = `
            <p class="muted">${escapeHTML(error.message)}</p>
        `;
    }
}

async function init() {
    if (!tg || !initData) {
        toast("Открой приложение через Telegram-бота.");
        return;
    }

    await loadProfile();
    await loadShop();
}

init();
