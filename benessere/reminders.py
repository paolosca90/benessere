"""Reminder pasti: avvisa se un pasto non è stato registrato oltre la finestra."""

from __future__ import annotations

import sqlite3
from datetime import datetime

from . import nutrition


def pending_meal_reminders(conn: sqlite3.Connection, now: datetime | None = None) -> list[dict]:
    """Pasti di oggi non ancora loggati il cui orario limite è passato.

    Ritorna lista di {meal, cutoff, message}. Vuota = tutto ok.
    """
    now = now or datetime.now()
    today = now.strftime("%Y-%m-%d")
    hours = nutrition.meal_windows()

    logged = {r["meal"] for r in nutrition.meals_for_day(conn, today)}
    targets = nutrition.compute_targets(conn, now.date())

    out: list[dict] = []
    for meal, cutoff_h in hours.items():
        cutoff = now.replace(hour=int(cutoff_h), minute=int((cutoff_h % 1) * 60), second=0, microsecond=0)
        if now >= cutoff and meal not in logged:
            out.append(
                {
                    "meal": meal,
                    "cutoff": cutoff.strftime("%H:%M"),
                    "message": f"{meal.capitalize()} non registrato (limite {cutoff.strftime('%H:%M')}). "
                    f"Target oggi: {targets.target_kcal} kcal / {targets.protein_g} g proteine.",
                }
            )
    return out


def reminder_report(conn: sqlite3.Connection, now: datetime | None = None) -> str:
    reminders = pending_meal_reminders(conn, now)
    if not reminders:
        return "Pasti di oggi tutti registrati ✔"
    return "\n".join(f"⏰ {r['message']}" for r in reminders)
