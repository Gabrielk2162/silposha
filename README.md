# 🛒 Silposha — AI-помічник для покупок у Сільпо

Автоматизація кошика в українському супермаркеті [Сільпо](https://silpo.ua) через reverse-engineered API. Працює без офіційного API — все зареверсено з веб-версії сайту.
<img width="881" height="596" alt="image" src="https://github.com/user-attachments/assets/352ebf40-ede7-4011-aa34-c8cace0f56d4" />

## Що вміє

- 🔍 **Пошук товарів** — по назві, з цінами, акціями, рейтингами
- 🛒 **Управління кошиком** — додати, видалити, очистити, переглянути (через API, <1с)
- 📊 **Аналіз покупок** — завантажує історію чеків з програми лояльності, аналізує патерни
- 🤖 **AI рекомендації** — Claude API формує розумний кошик на основі історії
- 🔐 **Авторизація** — OTP через SMS, автоматичний рефреш токена
- 🖥️ **Без GUI** — працює на headless сервері через Xvfb + headed Firefox

## Архітектура

```
Ти (чат з Claude Code)
  ↓
backend/run.py          — CLI runner
  ↓
backend/silpo/cart.py   — пошук, кошик (direct API, curl_cffi)
backend/silpo/browser.py — авторизація, токен рефреш (Playwright + Firefox)
backend/engine/         — AI аналітика та рекомендації
```

**Ключовий інсайт:** cart/search працюють через прямі API виклики (<1с), а браузер потрібен тільки для авторизації та рефрешу токена (раз на 12 годин).

## Розгортання через Claude Code (найпростіший спосіб)

Якщо у тебе є [Claude Code](https://claude.ai/claude-code), просто:

```bash
git clone https://github.com/denysosadchyi/silposha.git
cd silposha
claude
```

І скажи в чаті:

> Розгорни проект. Мій номер телефону +380XXXXXXXXX

Claude сам встановить залежності, налаштує Xvfb, авторизується через OTP, настроїть systemd таймери і буде готовий до роботи. Після цього просто пиши в чаті:

- *"Додай молоко в кошик"*
- *"Що в кошику?"*
- *"Підбери вечерю на двох за 500 грн"*
- *"Покажи історію покупок"*
- *"Очисти кошик"*

---

## Ручне розгортання

### 1. Залежності

```bash
# Python 3.12+
sudo apt-get install -y xvfb libxdamage1 libgtk-3-0t64 libpangocairo-1.0-0 \
  libpango-1.0-0 libatk1.0-0t64 libcairo-gobject2 libasound2t64

python -m venv venv
source venv/bin/activate
pip install -r backend/requirements.txt
pip install playwright curl_cffi
playwright install firefox
```

### 2. Конфігурація

```bash
cp .env.example .env
# Відредагуй .env:
#   SILPOSHA_CLAUDE_API_KEY=sk-ant-...  (опційно, для AI рекомендацій)
```

### 3. Авторизація в Сільпо

Потрібен реальний акаунт Сільпо (номер телефону).

```bash
# Запусти віртуальний дисплей
Xvfb :99 -screen 0 1280x720x24 &
export DISPLAY=:99

# Запусти авторизацію
source venv/bin/activate
python scripts/login.py
# Введи номер телефону → отримай SMS → введи код
```

Після успішного логіну створяться файли:
- `.silpo_auth.json` — access token (24 години)
- `.browser_state.json` — cookies для сесії
- `.ls_dump.json` — дані з localStorage

### 4. Systemd сервіси (автозапуск)

```bash
sudo cp scripts/xvfb.service /etc/systemd/system/
sudo cp scripts/silposha-refresh.service /etc/systemd/system/
sudo cp scripts/silposha-refresh.timer /etc/systemd/system/

sudo systemctl daemon-reload
sudo systemctl enable --now xvfb.service
sudo systemctl enable --now silposha-refresh.timer
```

Це забезпечує:
- **Xvfb** — завжди працює (для Firefox)
- **Token refresh** — кожні 12 годин перевіряє токен, оновлює якщо < 4 годин

### 5. Використання

```python
source venv/bin/activate
python -c "from backend.run import *; run(silpo_search('молоко'))"
python -c "from backend.run import *; run(silpo_add('молоко яготинське'))"
python -c "from backend.run import *; run(silpo_cart())"
python -c "from backend.run import *; run(silpo_clear())"
```

Або через Claude Code як чат-інтерфейс — просто скажи "додай молоко в кошик".

## API Endpoints (reverse-engineered)

| Операція | Метод | URL |
|---|---|---|
| Пошук | GET | `sf-ecom-api.silpo.ua/v1/uk/branches/{branchId}/products?search=...` |
| Кошик | GET | `sf-ecom-api.silpo.ua/v2/uk/shopping-cart/{basketId}?strictValidation=false` |
| Додати в кошик | POST | `sf-ecom-api.silpo.ua/v2/shopping-cart/{basketId}/products` |
| Очистити кошик | POST | `sf-ecom-api.silpo.ua/v1/shopping-cart/{basketId}/clear` |
| Замовлення | GET | `ecom-api.silpo.ua/v3/store-front/orders?filter[business][]=silpo` |
| Чеки | POST | `loyalty-platform-public-api.silpo.ua/api/v1/profile/my/cheque/cheque-headers` |
| Деталі чеку | POST | `loyalty-platform-public-api.silpo.ua/api/v1/profile/my/cheque/cheque-info` |

**Важливо:** GET кошика має `/uk/` в шляху, POST — ні.

## Cloudflare обхід

Silpo.ua захищений Cloudflare. Headless браузери блокуються. Єдиний робочий спосіб:

1. **Xvfb** — віртуальний дисплей
2. **Firefox headed** — через Xvfb, не headless
3. **WebDriver disabled** — `dom.webdriver.enabled: false` + патч `navigator.webdriver`

Для API-запитів (cart, search) використовується `curl_cffi` з `impersonate='chrome131'` — це обходить Cloudflare TLS fingerprinting.

## Структура проекту

```
backend/
├── config.py              # Налаштування (.env)
├── database.py            # SQLAlchemy async engine
├── models.py              # User, Preference, PurchaseHistory, CartSuggestion
├── main.py                # FastAPI app (не використовується, чат = UI)
├── run.py                 # CLI runner для всіх функцій
├── silpo/
│   ├── cart.py            # Кошик через direct API (~0.3с)
│   ├── browser.py         # Firefox + Xvfb + auto token refresh
│   ├── client.py          # Legacy catalog API
│   └── auth.py            # OTP auth (legacy, не використовується)
└── engine/
    ├── analyzer.py        # Аналіз історії покупок
    ├── recommender.py     # AI рекомендації через Claude API
    └── cart_builder.py    # Збірка кошика з рекомендацій
scripts/
├── xvfb.service           # Systemd: virtual display
├── silposha-refresh.*     # Systemd: token refresh timer
├── refresh_token.py       # Token refresh script
└── login.py               # Manual OTP login script
```

## Ліцензія

MIT. Використовує неофіційний API Сільпо — на свій ризик.
