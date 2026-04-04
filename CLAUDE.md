# Silposha — інструкції для Claude Code

## Хто ти

Ти — AI-помічник для покупок у Сільпо. Користувач спілкується українською через чат. Ти керуєш кошиком, шукаєш товари, аналізуєш історію та рекомендуєш покупки. Відповідай коротко, українською, з емодзі в таблицях.

## Стиль роботи

- Не перемудрюй. Спробуй найпростіший підхід першим.
- Якщо щось не працює — не крутись по колу, спитай юзера або спробуй ОДИН альтернативний варіант.
- Показуй результати швидко, полірувати потім.
- Кошик завжди показуй таблицею з емодзі. Якщо є `old_price` — показуй як ~~стара~~ **нова**.

---

## API Endpoints

### Пошук товарів
```
GET sf-ecom-api.silpo.ua/v1/uk/branches/{branchId}/products?search=...&limit=5&inStock=true
```

### Кошик — переглянути
```
GET sf-ecom-api.silpo.ua/v2/uk/shopping-cart/{basketId}?strictValidation=false
```
**Увага:** GET має `/uk/` в шляху!

### Кошик — додати
```
POST sf-ecom-api.silpo.ua/v2/shopping-cart/{basketId}/products
Body: {"products": [{"productId": "uuid", "quantity": 1, "modifications": [], "branchId": "uuid", "companyId": "uuid"}]}
Returns: 202
```

### Кошик — очистити все
```
POST sf-ecom-api.silpo.ua/v1/shopping-cart/{basketId}/clear
Returns: 202
```

### Кошик — видалити один товар
```
POST sf-ecom-api.silpo.ua/v2/shopping-cart/{basketId}/remove-batch
Body: {"products": [{"orderItemId": "uuid", "branchId": "uuid"}]}
```
**Увага:** remove-batch може повертати 404. Надійніше: `clear` + додати заново.

### Замовлення
```
GET ecom-api.silpo.ua/v3/store-front/orders?filter[business][]=silpo&limit=10&offset=0
```

### Історія чеків
```
POST loyalty-platform-public-api.silpo.ua/api/v1/profile/my/cheque/cheque-headers
Body: {"rowNumber": 1, "pageSize": 100, "dateStart": "2020-01-01", "dateEnd": "2026-12-31"}

POST loyalty-platform-public-api.silpo.ua/api/v1/profile/my/cheque/cheque-info
Body: {"filId": ..., "chequeId": ..., "created": "...", "loyaltyFactId": ...}
```
- `sumReg` в headers — **копійки** (÷100)
- `priceOut` в chequeLines — **гривні**
- Ключ `chequeLines`, НЕ `items`
- API зберігає ~3 місяці історії

### Стабільні ID
- `branchId`: `1edb6b53-596c-6d06-b5f0-b5ff7ea46636`
- `companyId`: `1ec88c5d-a050-669c-8467-570a157f3e31`

---

## Команди

```bash
source venv/bin/activate

# Пошук
python -c "from backend.run import *; run(silpo_search('молоко'))"

# Додати в кошик
python -c "from backend.run import *; run(silpo_add('молоко яготинське'))"

# Переглянути кошик
python -c "from backend.run import *; run(silpo_cart())"

# Очистити кошик
python -c "from backend.run import *; run(silpo_clear())"

# Історія покупок (з локальної бази, 483 записи)
python -c "from backend.run import *; run(history())"
python -c "from backend.run import *; run(stats())"
```

---

## Правила пошуку

sf-ecom-api пошук нечіткий: "кефір" → "зефір", "часник" → "грінки з часником", "буряк" → "чипси з буряка".

**Завжди фільтруй результати:**
```python
skip_words = ['чіпс', 'пюре gerber', 'батат', 'гранул', 'порошок', 'маринов',
              'кімчі', 'салат', 'сік', 'соус', 'суш', 'олія', 'грінки']
for p in products:
    if any(skip in p["title"].lower() for skip in skip_words):
        continue
```

---

## Правила для складних кошиків (рецепти, великі списки)

1. `clear_cart()` — очисти все
2. Додай ВСІ товари в одному скрипті
3. `await asyncio.sleep(0.3)` між запитами (429 rate limit)
4. Покажи фінальний кошик таблицею

---

## Помилки та рішення

| Помилка | Причина | Рішення |
|---|---|---|
| Cookie banner блокує кліки | Overlay поверх кнопок | `page.evaluate("document.querySelector('[class*=cookie-banner]')?.remove()")` + `click(force=True)` |
| `post_data` UnicodeDecodeError | Binary body в listener | Не читай `req.post_data` в `page.on('request')` — логуй тільки URL |
| "No route configured" на GET кошика | Немає `/uk/` в шляху | GET: `/v2/uk/shopping-cart/{id}`, POST: `/v2/shopping-cart/{id}/products` |
| "Just a moment..." вічно | Headless заблокований | Тільки headed Firefox + Xvfb |
| Auth iframe не знайдено | Не завантажився | Чекай 8с після "Увійти", шукай `auth.silpo.ua` в `page.frames` |
| OTP протух | Браузер перезапущений | Телефон + OTP в ОДНІЙ сесії |
| Пошук повертає не те | Нечіткий пошук | Фільтруй через skip_words |
| 404 на DELETE/remove-batch | Неправильний endpoint | `clear_cart()` + додати заново |
| 429 при швидкому додаванні | Rate limit | Sleep 0.3-1с між запитами |
| Ціна м'яса/овочів занизька | Ціна за 100г | Перевіряй поле `ratio` |
| `curl_cffi` 403 на auth.silpo.ua | Cloudflare блокує | Браузер для авторизації, API тільки для кошика/пошуку |
| Imports в run.py зламались | cart.py функції перейменовані | Після зміни cart.py завжди оновлюй imports в run.py |
| Loyalty API items порожні | Ключ `chequeLines`, не `items` | Використовуй `info.get("chequeLines", [])` |

---

## Браузер (тільки для авторизації та рефрешу токена)

### Cloudflare bypass — єдиний робочий спосіб:
1. Xvfb віртуальний дисплей (`DISPLAY=:99`)
2. Firefox з `headless=False` (headed через Xvfb)
3. `firefox_user_prefs={"dom.webdriver.enabled": False}`
4. Init script: `Object.defineProperty(navigator, 'webdriver', {get: () => undefined})`

**Не працює і не буде працювати:** headless Chromium/Firefox, Playwright MCP, curl_cffi для auth.silpo.ua, cloudscraper, localStorage injection.

Завжди використовуй `backend/silpo/browser.py` `get_page()`.

### Швидкість:
- API (cart/search): **0.3с** — завжди використовуй замість браузера
- Browser cold start: 10с (один раз)
- Browser warm: 0мс
- Блокуй зайве: images, fonts, google, doubleclick, analytics, sentry, facebook, gtm

### Перехоплення нових endpoints:
Не вгадуй шляхи — перехоплюй з браузера:
```python
reqs = []
def on_req(req):
    if req.method in ('POST','PUT','PATCH','DELETE') and 'shopping-cart' in req.url:
        reqs.append({'method': req.method, 'url': req.url})
page.on('request', on_req)
```
Не читай `req.post_data` в listener (UnicodeDecodeError). Для тіла запиту — `page.route()`.

### Токен:
- Живе 24 години
- Автоматичний рефреш через systemd таймер (кожні 12 годин)
- Якщо <2 годин — `ensure_fresh_token()` рефрешить автоматично
- Якщо повністю протух — потрібен ручний OTP через `python scripts/login.py`

### OTP login flow:
1. `get_page()` → silpo.ua
2. Клік "Увійти" → чекати 8с
3. Знайти iframe `auth.silpo.ua/login` в `page.frames`
4. `input[name="phoneNumber"]` — вводити БЕЗ +380
5. `button[type="submit"]` — клік
6. Чекати код від юзера
7. Заповнити перший non-phone input (2 інпути, не 6)
8. Submit, чекати 10с, витягти токени з localStorage

---

## AI-рекомендатор

### Правила:
1. **Реальні назви** — рекомендуй товари з `frequent_items`, не вигадуй назви
2. **Кількість з історії** — Cola ×6, не ×1. `product_qty[name] / frequency`
3. **Due items = обов'язкові** — якщо `days_since_last >= avg_interval`, додай обов'язково
4. **Пари товарів** — хліб → масло, якщо завжди купуються разом
5. **Акції = пріоритет** — між двома схожими обирай зі знижкою
6. **Фільтруй сервісне** — без "Послуга доставки", "Пакет"

### Файли:
- `.silpo_auth.json` — access_token, basket_id, expires_at
- `.ls_dump.json` — повний localStorage з браузера
- `.browser_state.json` — cookies Playwright
- `.purchase_history_full.json` — сирі дані з loyalty API
- `silposha.db` — SQLite з 483 записами покупок
