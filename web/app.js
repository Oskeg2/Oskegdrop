
const tg = window.Telegram?.WebApp;
if (tg) {
  tg.ready();
  tg.expand();
}

const API = "";
let player = null;

const gameArea = document.getElementById("game-area");
const balanceElement = document.getElementById("balance");

async function api(path, options = {}) {
  const response = await fetch(`${API}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      "Authorization": `tma ${tg?.initData || ""}`,
      ...options.headers
    }
  });

  if (!response.ok) {
    throw new Error(`Ошибка сервера: ${response.status}`);
  }

  return response.json();
}

function showMessage(message) {
  alert(message);
}

function updatePlayer(data) {
  player = data;

  if (balanceElement) {
    balanceElement.textContent = data.balance ?? 0;
  }

  const username = document.getElementById("username");
  if (username) {
    username.textContent =
      data.username || tg?.initDataUnsafe?.user?.first_name || "Игрок";
  }

  const items = document.getElementById("total-items");
  if (items) {
    items.textContent = data.inventory_count ?? 0;
  }

  const level = document.getElementById("player-level");
  if (level) {
    level.textContent = data.level ?? 1;
  }
}

async function loadProfile() {
  try {
    const data = await api("/api/me");
    updatePlayer(data);
  } catch (error) {
    console.error(error);
    showMessage("Не удалось загрузить профиль. Попробуй открыть приложение через Telegram.");
  }
}

async function claimBonus() {
  const button = document.getElementById("bonus-button");
  if (button) button.disabled = true;

  try {
    const result = await api("/api/bonus", {
      method: "POST"
    });

    if (result.user) {
      updatePlayer(result.user);
    }

    showMessage(result.message || "Бонус получен!");
  } catch (error) {
    showMessage("Не удалось получить бонус. Попробуй позже.");
  } finally {
    if (button) button.disabled = false;
  }
}

function renderGame(page) {
  if (!gameArea) return;

  const pages = {
    home: `
      <h2>Добро пожаловать!</h2>
      <p>Выбирай игру и получай игровые очки.</p>
    `,

    games: `
      <h2>Мини-игры</h2>
      <p>Выбери одну из доступных игр.</p>
      <button class="main-button" data-page="upgrade">Апгрейдер</button>
      <button class="main-button" data-page="crash">Crash</button>
      <button class="main-button" data-page="mines">Сапёр</button>
    `,

    upgrade: `
      <h2>⚡ Апгрейдер</h2>
      <p>Улучшай свои игровые предметы.</p>
      <button class="main-button" id="upgrade-info">Посмотреть улучшения</button>
    `,

    crash: `
      <h2>📈 Crash Arcade</h2>
      <p>Тренируй реакцию: следи за множителем и нажми кнопку до окончания раунда.</p>
      <div class="crash-multiplier" id="multiplier">1.00x</div>
      <button class="main-button" id="crash-start">Начать раунд</button>
      <button class="main-button" id="crash-stop" disabled>Завершить раунд</button>
      <p id="crash-result">Игра на виртуальные очки без ставок.</p>
    `,

    mines: `
      <h2>💣 Сапёр</h2>
      <p>Открывай безопасные клетки. Игра на внимательность.</p>
      <div class="mines-grid" id="mines-grid"></div>
      <button class="main-button" id="mines-reset">Новая игра</button>
    `,

    cases: `
      <h2>🎁 Кейсы</h2>
      <p>Награды и содержимое кейсов будут указаны заранее.</p>
      <button class="main-button" id="cases-info">Посмотреть кейсы</button>
    `,

    profile: `
      <h2>👤 Профиль</h2>
      <p>Твой баланс и прогресс сохраняются на сервере.</p>
    `
  };

  gameArea.innerHTML = pages[page] || pages.home;

  if (page === "crash") initCrash();
  if (page === "mines") initMines();

  gameArea.querySelectorAll("[data-page]").forEach(button => {
    button.addEventListener("click", () => {
      renderGame(button.dataset.page);
    });
  });

  document.getElementById("upgrade-info")?.addEventListener("click", () => {
    showMessage("Система улучшений будет подключена к серверу следующим этапом.");
  });

  document.getElementById("cases-info")?.addEventListener("click", () => {
    showMessage("Скоро здесь появятся кейсы с заранее известными наградами.");
  });
}

// Аркадный Crash без ставок и денежных выигрышей.
function initCrash() {
  const multiplier = document.getElementById("multiplier");
  const start = document.getElementById("crash-start");
  const stop = document.getElementById("crash-stop");
  const result = document.getElementById("crash-result");

  let value = 1;
  let timer = null;

  start.addEventListener("click", () => {
    value = 1;
    multiplier.textContent = "1.00x";
    result.textContent = "Раунд начался!";
    start.disabled = true;
    stop.disabled = false;

    timer = setInterval(() => {
      value += 0.01 + Math.random() * 0.04;
      multiplier.textContent = value.toFixed(2) + "x";

      if (value >= 5) {
        clearInterval(timer);
        start.disabled = false;
        stop.disabled = true;
        result.textContent = "Раунд завершён!";
      }
    }, 100);
  });

  stop.addEventListener("click", () => {
    clearInterval(timer);
    start.disabled = false;
    stop.disabled = true;
    result.textContent = `Ты завершил раунд на ${value.toFixed(2)}x`;
  });
}

// Сапёр: безопасная мини-игра без денежных ставок.
function initMines() {
  const grid = document.getElementById("mines-grid");
  const reset = document.getElementById("mines-reset");

  function createBoard() {
    grid.innerHTML = "";

    const safeCells = new Set();

    while (safeCells.size < 16) {
      safeCells.add(Math.floor(Math.random() * 25));
    }

    for (let i = 0; i < 25; i++) {
      const cell = document.createElement("button");
      cell.className = "mine-cell";
      cell.textContent = "?";

      cell.addEventListener("click", () => {
        if (cell.disabled) return;

        cell.disabled = true;

        if (safeCells.has(i)) {
          cell.textContent = "✦";
          cell.classList.add("safe");
        } else {
          cell.textContent = "×";
          cell.classList.add("miss");
        }
      });

      grid.appendChild(cell);
    }
  }

  reset.addEventListener("click", createBoard);
  createBoard();
}

document.getElementById("bonus-button")?.addEventListener("click", claimBonus);

document.querySelectorAll(".game-card, .bottom-nav button").forEach(button => {
  button.addEventListener("click", () => {
    renderGame(button.dataset.page);
  });
});

loadProfile();
