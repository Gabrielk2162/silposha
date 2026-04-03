"""AI-powered recommendation engine using Claude API."""

from __future__ import annotations

import json

import anthropic

from backend.config import settings


async def generate_cart_recommendation(
    purchase_stats: dict,
    user_preferences: list[dict],
    due_items: list[dict],
) -> dict:
    """Use Claude to generate a smart cart recommendation.

    Args:
        purchase_stats: Output from analyzer.get_purchase_stats
        user_preferences: User's saved preferences (diet, allergies, budget, etc.)
        due_items: Items that are due for reorder based on frequency

    Returns:
        Dict with recommended_items list and reasoning.
    """
    if not settings.claude_api_key:
        return _fallback_recommendation(due_items, purchase_stats)

    prefs_text = "\n".join(
        f"- {p['category']}: {p['key']} = {p['value']}" for p in user_preferences
    )

    due_text = "\n".join(
        f"- {item['product']}: купували {item['times_bought']} раз, "
        f"кожні ~{item['avg_interval_days']} днів, "
        f"не купували вже {item['days_since_last']} днів"
        for item in due_items[:15]
    )

    frequent_text = "\n".join(
        f"- {name}: {count} шт" for name, count in purchase_stats.get("frequent_items", [])[:15]
    )

    brands_text = "\n".join(
        f"- {brand}: {count} покупок" for brand, count in purchase_stats.get("brand_preferences", {}).items()
    )

    prompt = f"""Ти — розумний помічник для закупок продуктів в українському магазині Сільпо.

На основі історії покупок та уподобань користувача, сформуй рекомендований список покупок.

## Уподобання користувача:
{prefs_text or "Немає збережених уподобань"}

## Товари, які пора замовити (на основі частоти покупок):
{due_text or "Немає даних про частоту"}

## Найчастіші покупки:
{frequent_text or "Немає історії"}

## Улюблені бренди:
{brands_text or "Немає даних"}

## Завдання:
Сформуй JSON-список рекомендованих товарів для наступного замовлення.
Враховуй:
1. Товари, які пора купити (due items) — додай їх обовʼязково
2. Товари, які часто купуються разом
3. Уподобання по брендах
4. Дієтичні обмеження та алергії
5. Бюджетні обмеження, якщо є

Відповідай ТІЛЬКИ валідним JSON у форматі:
{{
  "items": [
    {{"name": "Назва товару", "quantity": 1, "reason": "Чому рекомендовано"}}
  ],
  "reasoning": "Загальне пояснення рекомендації"
}}"""

    client = anthropic.AsyncAnthropic(api_key=settings.claude_api_key)
    response = await client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}],
    )

    try:
        text = response.content[0].text
        # Extract JSON from response (Claude might wrap it in markdown)
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0]
        elif "```" in text:
            text = text.split("```")[1].split("```")[0]
        return json.loads(text.strip())
    except (json.JSONDecodeError, IndexError):
        return _fallback_recommendation(due_items, purchase_stats)


def _fallback_recommendation(due_items: list[dict], purchase_stats: dict) -> dict:
    """Simple rule-based recommendation when Claude API is unavailable."""
    items = []
    for item in due_items[:10]:
        items.append({
            "name": item["product"],
            "quantity": 1,
            "reason": f"Купуєте кожні ~{item['avg_interval_days']} днів, вже {item['days_since_last']} днів без покупки",
        })

    # Add top frequent items not already in due list
    due_names = {item["product"] for item in due_items}
    for name, count in purchase_stats.get("frequent_items", [])[:5]:
        if name not in due_names:
            items.append({
                "name": name,
                "quantity": 1,
                "reason": f"Часто купуєте ({count} разів)",
            })

    return {
        "items": items,
        "reasoning": "Рекомендація на основі частоти покупок (без AI-аналізу).",
    }
