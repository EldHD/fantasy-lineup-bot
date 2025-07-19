import logging
import math
import random
from datetime import datetime, timezone
from typing import List, Optional

from telegram import (
    Update,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from telegram.ext import (
    ContextTypes,
)

from bot.config import TOURNAMENT_TEAMS, EPL_TEAM_NAMES
from bot.db.database import async_session
from bot.db import models
from bot.services.roster import (
    sync_multiple_teams,
    ensure_teams_exist,
)
from bot.db.crud import (
    fetch_matches_by_league,
    fetch_match_with_teams,
    fetch_predictions_for_team_match,
    upsert_prediction_stub,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ UI
# ---------------------------------------------------------------------------

def leagues_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton("Premier League", callback_data="league:epl")],
        # Расширяем по мере добавления: laliga, rpl и т.д.
    ]
    return InlineKeyboardMarkup(buttons)

def back_buttons(level: str, match_id: Optional[int] = None) -> InlineKeyboardMarkup:
    rows = []
    if level == "matches":
        rows.append([InlineKeyboardButton("⬅ Матчи", callback_data=f"back:matches:{match_id}")])
    if level == "leagues":
        rows.append([InlineKeyboardButton("🏁 Лиги", callback_data="back:leagues")])
    return InlineKeyboardMarkup(rows)


# ---------------------------------------------------------------------------
# /start
# ---------------------------------------------------------------------------

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Стартовое меню – сразу показываем выбор лиг без промежуточного текста."""
    kb = leagues_keyboard()
    text = "Выберите лигу:"
    if update.message:
        await update.message.reply_text(text, reply_markup=kb)
    else:
        # если /start пришёл через callback – редактируем
        q = update.callback_query
        if q:
            await q.answer()
            await q.edit_message_text(text, reply_markup=kb)


# ---------------------------------------------------------------------------
# ВЫБОР ЛИГИ -> СПИСОК МАТЧЕЙ
# ---------------------------------------------------------------------------

async def handle_league_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data  # league:<code>
    league_code = data.split(":")[1]

    await query.edit_message_text("Загружаю матчи ...")

    try:
        matches = await fetch_matches_by_league(league_code)
    except Exception as e:
        logger.exception("Error fetching matches")
        await query.edit_message_text(f"Произошла ошибка при загрузке матчей для {league_code.upper()} :(",
                                      reply_markup=InlineKeyboardMarkup(
                                          [[InlineKeyboardButton("🏁 Лиги", callback_data="back:leagues")]]
                                      ))
        return

    if not matches:
        await query.edit_message_text(f"Нет доступных матчей для {league_code.upper()}",
                                      reply_markup=InlineKeyboardMarkup(
                                          [[InlineKeyboardButton("🏁 Лиги", callback_data="back:leagues")]]
                                      ))
        return

    # Клавиатура: каждый матч — кнопка; плюс навигация
    buttons = []
    for m in matches:
        # ожидаем что m имеет поля: id, home_team_name, away_team_name, kickoff_utc, matchweek
        dt_str = ""
        if m.kickoff_utc:
            if isinstance(m.kickoff_utc, datetime):
                dt_str = m.kickoff_utc.strftime("%Y-%m-%d %H:%M")
            else:
                dt_str = str(m.kickoff_utc)
        label = f"{m.home_team_name} vs {m.away_team_name} ({dt_str} UTC)"
        buttons.append([InlineKeyboardButton(label, callback_data=f"match:{m.id}")])

    buttons.append([InlineKeyboardButton("🏁 Лиги", callback_data="back:leagues")])

    await query.edit_message_text(
        "Выберите матч:",
        reply_markup=InlineKeyboardMarkup(buttons)
    )


# ---------------------------------------------------------------------------
# ВЫБОР МАТЧА -> ВЫБОР КОМАНДЫ
# ---------------------------------------------------------------------------

async def handle_match_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    match_id = int(q.data.split(":")[1])

    match = await fetch_match_with_teams(match_id)
    if not match:
        await q.edit_message_text("Матч не найден.", reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("🏁 Лиги", callback_data="back:leagues")]]
        ))
        return

    # Предполагаем поля: home_team_name, away_team_name, matchweek, kickoff_utc
    lines = [
        f"{match.home_team_name} vs {match.away_team_name}",
        f"Matchweek {match.matchweek}" if match.matchweek else "",
    ]
    if match.kickoff_utc:
        if isinstance(match.kickoff_utc, datetime):
            lines.append(f"Kickoff: {match.kickoff_utc.strftime('%Y-%m-%d %H:%M')} UTC")
        else:
            lines.append(f"Kickoff: {match.kickoff_utc} UTC")
    text = "\n".join([l for l in lines if l])

    buttons = [
        [InlineKeyboardButton(match.home_team_name, callback_data=f"team:{match_id}:{match.home_team_id}")],
        [InlineKeyboardButton(match.away_team_name, callback_data=f"team:{match_id}:{match.away_team_id}")],
        [InlineKeyboardButton("⬅ Матчи", callback_data="back:leagues"),  # упрощённо
         InlineKeyboardButton("🏁 Лиги", callback_data="back:leagues")]
    ]
    await q.edit_message_text(text + "\n\nВыберите команду:", reply_markup=InlineKeyboardMarkup(buttons))


# ---------------------------------------------------------------------------
# НАЗАД К ЛИГАМ / МАТЧАМ
# ---------------------------------------------------------------------------

async def back_to_leagues(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    await start_cmd(update, context)

async def back_to_matches(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    # Здесь можно повторно загрузить матчи из сохранённого league_code в context.user_data
    await q.edit_message_text("Выберите лигу:", reply_markup=leagues_keyboard())


# ---------------------------------------------------------------------------
# ПРЕДИКТ СОСТАВА ДЛЯ КОМАНДЫ
# ---------------------------------------------------------------------------

def format_player_line(p):
    """
    p – объект предикта/игрока.
    Ожидаемые атрибуты:
      p.shirt_number / p.number
      p.name
      p.position (общее: GK/DF/MF/FW)
      p.position_detail (например, CB, LB)
      p.predicted_prob (float 0..1)
      p.status (OUT / INJ / SUSP / None)
      p.reason_text (текст причины)
      p.is_starting (bool)
    """
    num = getattr(p, "shirt_number", None) or getattr(p, "number", "")
    pos_detail = getattr(p, "position_detail", "") or ""
    base_pos = getattr(p, "position", "") or ""
    prob = getattr(p, "predicted_prob", None)
    if prob is None:
        prob_percent = "?"
    else:
        prob_percent = f"{int(round(prob * 100))}%"
    status = getattr(p, "status", None)
    reason = getattr(p, "reason_text", "")
    name = getattr(p, "name", "???")

    pos_out = f"{base_pos}" + (f"/{pos_detail}" if pos_detail and pos_detail not in base_pos else "")
    left = f"{num} {name}" if num else name
    if status and status.upper() in ("OUT", "INJ", "SUSP"):
        return f"{left} ({pos_out}) {prob_percent} | ❌ {reason or status}"
    return f"{left} ({pos_out}) {prob_percent}"

def pick_lineup(predictions: List, scheme: str = "4-2-3-1"):
    """
    Заглушечная логика выбора 11: сортируем по вероятности и берём 11.
    Схема пока не применяет точный набор ролей – это place-holder.
    """
    ordered = sorted(predictions, key=lambda x: (getattr(x, "predicted_prob", 0.0) or 0.0), reverse=True)
    starting = ordered[:11]
    rest = ordered[11:]
    return starting, rest

async def handle_team_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    parts = q.data.split(":")
    match_id = int(parts[1])
    team_id = int(parts[2])

    preds = await fetch_predictions_for_team_match(match_id, team_id)

    if not preds:
        await q.edit_message_text("Нет предиктов для этой команды.",
                                  reply_markup=InlineKeyboardMarkup(
                                      [[InlineKeyboardButton("⬅ Назад", callback_data=f"match:{match_id}")]]
                                  ))
        return

    # Искусственный выбор схемы (позже можно динамически)
    scheme = "4-2-3-1"

    starting, bench = pick_lineup(preds, scheme)

    # Разделим OUT отдельно
    out_players = [p for p in bench if getattr(p, "status", "") in ("OUT", "INJ", "SUSP")]

    bench_clean = [p for p in bench if p not in out_players]

    # Группировка стартовых по крупным линиям
    def cat(p):
        pos = (getattr(p, "position", "") or "").upper()
        if pos == "GK":
            return 0
        if pos in ("DF", "D", "DEF"):
            return 1
        if pos in ("MF", "M", "MID"):
            return 2
        return 3  # FW

    starting_sorted = sorted(starting, key=lambda x: (cat(x), -(getattr(x, "predicted_prob", 0) or 0)))

    lines = [f"Схема: {scheme}", "✅ Старт (11):"]
    for p in starting_sorted:
        lines.append(format_player_line(p))

    if out_players:
        lines.append("")
        lines.append("❌ Не сыграют:")
        for p in out_players:
            lines.append(format_player_line(p))

    if bench_clean:
        lines.append("")
        lines.append("🔁 Скамейка / ротация:")
        # ограничим вывод чтобы не переполнять сообщение
        for p in bench_clean[:25]:
            lines.append(format_player_line(p))
        if len(bench_clean) > 25:
            lines.append(f"... ещё {len(bench_clean) - 25}")

    buttons = [
        [InlineKeyboardButton("⬅ Матчи", callback_data="back:leagues"),
         InlineKeyboardButton("🏁 Лиги", callback_data="back:leagues")]
    ]
    await q.edit_message_text("\n".join(lines), reply_markup=InlineKeyboardMarkup(buttons))


# ---------------------------------------------------------------------------
# /sync_roster – синхронизация для текущего матча (демо – синк первых 2 команд EPL)
# ---------------------------------------------------------------------------

async def sync_roster_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    teams = EPL_TEAM_NAMES[:2]
    rep = await sync_multiple_teams(teams, delay_between=3.0)
    await update.message.reply_text(rep or "Roster sync done.")


# ---------------------------------------------------------------------------
# /resync_all – пакетная синхронизация EPL по 5 команд
# ---------------------------------------------------------------------------

async def resync_all_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message:
        return
    all_teams = EPL_TEAM_NAMES
    chunk = 5
    offset = context.user_data.get("resync_offset", 0)
    if offset >= len(all_teams):
        context.user_data["resync_offset"] = 0
        offset = 0
    slice_ = all_teams[offset: offset + chunk]
    context.user_data["resync_offset"] = offset + chunk

    await message.reply_text(f"🔄 Batch {offset//chunk + 1} ({offset + 1}-{min(offset + chunk, len(all_teams))}): "
                             f"{', '.join(slice_)}")

    rep = await sync_multiple_teams(slice_, delay_between=3.5)
    await message.reply_text(rep or "Batch done.")
    if context.user_data["resync_offset"] < len(all_teams):
        await message.reply_text("Отправь /resync_all ещё раз для следующего батча.")
    else:
        await message.reply_text("Полный цикл EPL завершён.")


# ---------------------------------------------------------------------------
# /modules – диагностика (покажет загруженные апланировщики, если остались)
# ---------------------------------------------------------------------------

async def modules_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    import sys
    mods = [m for m in sys.modules if m.startswith("apscheduler")]
    await update.message.reply_text("Apscheduler modules: " + ("; ".join(mods) if mods else "NONE"))


# ---------------------------------------------------------------------------
# СТАБ: если нужно создать stub-предикты вручную (опционально)
# ---------------------------------------------------------------------------

async def create_stub_predictions_for_match(match_id: int, team_id: int):
    """
    Пример: создаёт заглушечные предикты в БД если нет.
    """
    async with async_session() as session:
        # Получаем список игроков команды
        players = await session.execute(
            models.select_players_by_team(team_id)  # Нужно иметь helper или заменить реальным запросом
        )
        players = [row[0] for row in players]
        for p in players:
            await upsert_prediction_stub(
                session=session,
                match_id=match_id,
                team_id=team_id,
                player_id=p.id,
                prob=random.uniform(0.4, 0.95)
            )
        await session.commit()
