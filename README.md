# 🛒 Silposha — AI-помічник для покупок у Сільпо

Розумний помічник для покупок у [Сільпо](https://silpo.ua). Керуй кошиком, аналізуй історію покупок і отримуй AI-рекомендації — прямо з чату.
<img width="881" height="596" alt="image" src="https://github.com/user-attachments/assets/352ebf40-ede7-4011-aa34-c8cace0f56d4" />

## Що вміє

- 🔍 **Пошук товарів** — по назві, з цінами, акціями, рейтингами
- 🛒 **Управління кошиком** — додати, видалити, очистити, переглянути (<1с)
- 📊 **Аналіз покупок** — завантажує історію чеків, аналізує патерни та улюблені товари
- 🤖 **AI рекомендації** — формує розумний кошик на основі історії покупок
- 🍳 **Рецепти** — скажи "зроби борщ на 4 літри" і він підбере всі інгредієнти
- 📦 **Статус замовлення** — перевіряє поточні доставки
- 🔐 **Авторизація** — OTP через SMS, автоматичний рефреш токена кожні 12 годин
- 🖥️ **Headless сервер** — працює без монітора через віртуальний дисплей

## Приклади

```
> Додай молоко Яготинське в кошик
✅ Молоко «Яготинське» ультрапастеризоване 2,5% — 69.99 грн

> Що в кошику?
| 🥛 | Молоко «Яготинське» 2,5% | 69.99 грн | 1 шт |

> Підбери вечерю на двох за 500 грн
🍗 Куряче філе, 🍝 Спагеті, 🧀 Грана Падано, 🍅 Черрі, 🍷 Вино Коблево...

> Покажи історію покупок
📊 11 замовлень, 65,300 грн за 3 місяці. Завжди береш: Cola Zero ×6, хліб, картоплю...

> Який статус замовлення?
📦 #33606623 — зібрано, доставка сьогодні 16:00-19:00, 9,223 грн
```

## Розгортання через Claude Code

Найпростіший спосіб — [Claude Code](https://claude.ai/claude-code):

```bash
git clone https://github.com/denysosadchyi/silposha.git
cd silposha
claude
```

Скажи в чаті:

> Розгорни проект. Мій номер телефону +380XXXXXXXXX

Claude сам встановить все, авторизується через OTP і настроїть автозапуск.

---

## Ручне розгортання

### 1. Залежності

```bash
# Ubuntu/Debian, Python 3.12+
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

```bash
# Запусти віртуальний дисплей
Xvfb :99 -screen 0 1280x720x24 &
export DISPLAY=:99

# Запусти авторизацію
source venv/bin/activate
python scripts/login.py
# Введи номер телефону → отримай SMS → введи код
```

### 4. Автозапуск (systemd)

```bash
sudo cp scripts/xvfb.service /etc/systemd/system/
sudo cp scripts/silposha-refresh.service /etc/systemd/system/
sudo cp scripts/silposha-refresh.timer /etc/systemd/system/

sudo systemctl daemon-reload
sudo systemctl enable --now xvfb.service
sudo systemctl enable --now silposha-refresh.timer
```

- **Xvfb** — віртуальний дисплей, завжди активний
- **Token refresh** — кожні 12 годин перевіряє і оновлює токен

### 5. Використання

```bash
source venv/bin/activate
python -c "from backend.run import *; run(silpo_search('молоко'))"
python -c "from backend.run import *; run(silpo_add('молоко яготинське'))"
python -c "from backend.run import *; run(silpo_cart())"
python -c "from backend.run import *; run(silpo_clear())"
```

## Як це працює

```
Ти (чат)
  ↓
Claude Code ← CLAUDE.md (всі правила та промпти)
  ↓
backend/silpo/cart.py ← curl_cffi → sf-ecom-api.silpo.ua (0.3с)
  ↓ (раз на 12 годин)
backend/silpo/browser.py ← Playwright + Firefox → auth.silpo.ua (10с)
```

**Пошук і кошик** працюють через прямі HTTP-запити — без браузера, за 0.1-0.3с.

**Авторизація** потребує реальний Firefox у віртуальному дисплеї (Xvfb), щоб пройти Cloudflare. Це відбувається лише раз на добу для оновлення токена.

## Структура проекту

```
backend/
├── run.py                 # CLI runner — всі команди
├── silpo/
│   ├── cart.py            # Кошик та пошук (~0.3с)
│   ├── browser.py         # Firefox + авто-рефреш токена
│   └── client.py          # Каталог товарів
└── engine/
    ├── analyzer.py        # Аналіз історії покупок
    ├── recommender.py     # AI рекомендації (Claude API)
    └── cart_builder.py    # Збірка кошика
scripts/
├── login.py               # OTP авторизація
├── refresh_token.py       # Рефреш токена
├── xvfb.service           # Systemd: віртуальний дисплей
└── silposha-refresh.*     # Systemd: таймер рефрешу
CLAUDE.md                  # Промпти та правила для Claude Code
```

## Ресурси сервера

| Ресурс | Використання |
|---|---|
| RAM | ~62 MB постійно. Firefox ~300 MB на 15с під час рефрешу |
| Диск | ~1.6 GB (venv + Firefox) |
| CPU | ~0% |

## Ліцензія

MIT
