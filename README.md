# 🛒 Silposha — AI-помічник для покупок у Сільпо

Розумний помічник для покупок у [Сільпо](https://silpo.ua). Керуй кошиком, аналізуй історію покупок і отримуй AI-рекомендації — прямо з чату.
<img width="881" height="596" alt="image" src="https://github.com/user-attachments/assets/352ebf40-ede7-4011-aa34-c8cace0f56d4" />

## Що вміє

- 🔍 **Пошук товарів** — по назві, з цінами, акціями, рейтингами
- 🛒 **Управління кошиком** — додати, видалити, очистити, переглянути (<1с)
- 📊 **Аналіз покупок** — завантажує історію чеків, аналізує патерни та улюблені товари
- 🤖 **AI рекомендації** — формує розумний кошик на основі історії покупок
- 🔐 **Авторизація** — OTP через SMS, автоматичний рефреш токена кожні 12 годин
- 🖥️ **Headless сервер** — працює без монітора через віртуальний дисплей

## Розгортання через Claude Code

Найпростіший спосіб — [Claude Code](https://claude.ai/claude-code):

```bash
git clone https://github.com/denysosadchyi/silposha.git
cd silposha
claude
```

Скажи в чаті:

> Розгорни проект. Мій номер телефону +380XXXXXXXXX

Claude сам встановить все, авторизується через OTP і настроїть автозапуск. Після цього:

- *"Додай молоко в кошик"*
- *"Що в кошику?"*
- *"Підбери вечерю на двох за 500 грн"*
- *"Покажи історію покупок"*
- *"Очисти кошик"*

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

Після логіну створяться:
- `.silpo_auth.json` — access token (24 години)
- `.browser_state.json` — cookies сесії
- `.ls_dump.json` — дані localStorage

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

Silpo.ua — це Angular SPA за Cloudflare. Прямі HTTP-запити блокуються.

**Авторизація:** Firefox запускається у віртуальному дисплеї (Xvfb), проходить Cloudflare challenge як звичайний браузер, логіниться через OTP і зберігає токен. Потім токен оновлюється автоматично кожні 12 годин.

**Операції з кошиком:** після отримання токена, пошук і кошик працюють через прямі HTTP-запити (`curl_cffi`) — без браузера, за 0.1-0.3 секунди.

## Структура проекту

```
backend/
├── run.py                 # CLI runner
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
```

## Ресурси сервера

| Ресурс | Використання |
|---|---|
| RAM | ~62 MB (Xvfb). Firefox запускається тільки для рефрешу (~300 MB на 15с) |
| Диск | ~1.6 GB (venv + Firefox) |
| CPU | ~0% (все спить між запитами) |

## Ліцензія

MIT
