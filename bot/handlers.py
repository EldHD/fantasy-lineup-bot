from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.ext import ContextTypes
from bot.db.crud import (
    fetch_matches_by_league,
    fetch_match_with_teams,
    fetch_team_lineup_predictions,
)
from bot.services.roster import sync_multiple_teams, ensure_teams_exist
from bot.services.predictions import generate_baseline_predictions
from bot.config import EPL_TEAM_NAMES
from sqlalchemy import select
from bot.db.database import SessionLocal
from bot.db.models import Tournament, Match, Player, Team, Prediction, PlayerStatus
import io
import csv
from datetime import datetime


LEAGUES = [
    ("Premier League", "epl"),
    ("La Liga", "laliga"),
    ("Serie A", "seriea"),
    ("Bundesliga", "bundesliga"),
    ("Ligue 1", "ligue1"),
    ("Russian Premier League", "rpl"),
]


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton(name, callback_data=f"league_{code}")] for name, code in LEAGUES]
    markup = InlineKeyboardMarkup(keyboard)
    if update.message:
        await update.message.reply_text("Выберите лигу:", reply_markup=markup)
    else:
        await context.bot.send_message(update.effective_chat.id, "Выберите лигу:", reply_markup=markup)


async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("pong")


async def sync_roster_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if context.args:
            team_names = " ".join(context.args).split(",")
            team_names = [t.strip() for t in team_names if t.strip()]
        else:
            team_names = ["Arsenal", "Chelsea"]
        rep = await sync_multiple_teams(team_names)
        await update.message.reply_text(f"Roster sync:\n{rep}")
    except Exception as e:
        await update.message.reply_text(f"Roster sync failed: {e}")


async def resync_all_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Полный синк всех EPL команд."""
    await ensure_teams_exist(EPL_TEAM_NAMES, tournament_code="epl")
    rep = await sync_multiple_teams(EPL_TEAM_NAMES)
    await update.message.reply_text(f"EPL full sync:\n{rep[:3500]}")

async def gen_demo_preds_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await update.message.reply_text("Usage: /gen_demo_preds <match_id> <team_id>")
        return
    try:
        match_id = int(context.args[0])
        team_id = int(context.args[1])
    except ValueError:
        await update.message.reply_text("IDs must be integers.")
        return
    rep = await generate_baseline_predictions(match_id, team_id)
    await update.message.reply_text(rep)


async def export_lineup_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /export_lineup <match_id> <team_id> [csv|md]
    Экспорт старт/OUT/bench в таблицу.
    """
    if len(context.args) < 2:
        await update.message.reply_text("Usage: /export_lineup <match_id> <team_id> [csv|md]")
        return
    try:
        match_id = int(context.args[0])
        team_id = int(context.args[1])
    except ValueError:
        await update.message.reply_text("IDs must be integers.")
        return
    fmt = "csv"
    if len(context.args) >= 3:
        fmt = context.args[2].lower()
        if fmt not in ("csv", "md"):
            fmt = "csv"

    rows = await fetch_team_lineup_predictions(match_id, team_id)
    if not rows:
        await update.message.reply_text("Нет данных предикта.")
        return

    # Найдём матч и команду
    async with SessionLocal() as session:
        m_res = await session.execute(select(Match).where(Match.id == match_id))
        match = m_res.scalar_one_or_none()
        t_res = await session.execute(select(Team).where(Team.id == team_id))
        team = t_res.scalar_one_or_none()
    match_label = f"{match.home_team_id} vs {match.away_team_id}" if match else f"match {match_id}"
    team_name = team.name if team else f"team {team_id}"

    # Преобразуем в упрощённый вид
    starters = [r for r in rows if r["will_start"] and r["status_availability"] != "OUT"]
    out_players = [r for r in rows if r["status_availability"] == "OUT"]
    bench = [r for r in rows if not r["will_start"] and r["status_availability"] != "OUT"]

    def simple_row(block_type, r):
        return {
            "match_id": match_id,
            "team_id": team_id,
            "team": team_name,
            "player": r["full_name"],
            "number": r["number"] or "",
            "position": r["position_detail"] or r["position_main"],
            "category": block_type,  # START / OUT / BENCH
            "probability": r["probability"],
            "reason": r["status_reason"] or r["explanation"] or ""
        }

    export_rows = (
        [simple_row("START", r) for r in starters[:11]] +
        [simple_row("OUT", r) for r in out_players] +
        [simple_row("BENCH", r) for r in bench]
    )

    if fmt == "csv":
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=list(export_rows[0].keys()))
        writer.writeheader()
        for er in export_rows:
            writer.writerow(er)
        data = buf.getvalue().encode("utf-8")
        bio = io.BytesIO(data)
        bio.name = f"lineup_{match_id}_{team_id}.csv"
        await update.message.reply_document(document=bio, caption=f"Export CSV: {team_name}")
    else:
        # Markdown таблица
        headers = list(export_rows[0].keys())
        md_lines = []
        md_lines.append("| " + " | ".join(headers) + " |")
        md_lines.append("| " + " | ".join(["---"] * len(headers)) + " |")
        for er in export_rows:
            md_lines.append("| " + " | ".join(str(er[h]) for h in headers) + " |")
        text = f"**Lineup Export** `{team_name}` / match {match_id}\n" + "\n".join(md_lines)
        if len(text) > 3900:
            text = text[:3900] + "\n… truncated"
        await update.message.reply_text(text, parse_mode="Markdown")


async def debug_db(update: Update, context: ContextTypes.DEFAULT_TYPE):
    async with SessionLocal() as session:
        t_res = await session.execute(select(Tournament))
        tournaments = t_res.scalars().all()
        m_res = await session.execute(select(Match))
        matches = m_res.scalars().all()
        p_res = await session.execute(select(Player))
        players = p_res.scalars().all()
    lines = ["Tournaments:"]
    for t in tournaments:
        lines.append(f"- {t.id} {t.code} {t.name}")
    lines.append("Matches:")
    for m in matches:
        lines.append(f"- {m.id} t={m.tournament_id} {m.round} ko={m.utc_kickoff} home={m.home_team_id} away={m.away_team_id}")
    lines.append(f"Players total: {len(players)}")
    text = "\n".join(lines)
    if len(text) > 3800:
        text = text[:3800] + "\n…truncated"
    await update.message.reply_text(f"```\n{text}\n```", parse_mode="Markdown")


# Навигационные (оставляем прежние ниже) ----------------

async def back_to_leagues(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await start(update, context)


async def handle_league_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    league_code = query.data.split("_", 1)[1]
    try:
        matches = await fetch_matches_by_league(league_code)
        if not matches:
            buttons = [[InlineKeyboardButton("⬅ К лигам", callback_data="back_leagues")]]
            await query.edit_message_text(
                f"Нет доступных матчей для {league_code.upper()}",
                reply_markup=InlineKeyboardMarkup(buttons)
            )
            return
        buttons = []
        for m in matches:
            ko = m["utc_kickoff"]
            ko_txt = ko.strftime("%Y-%m-%d %H:%M UTC") if hasattr(ko, "strftime") else str(ko)
            txt = f"{m['home_team_name']} vs {m['away_team_name']} • {ko_txt}"
            buttons.append([InlineKeyboardButton(txt, callback_data=f"matchdb_{m['id']}")])
        buttons.append([InlineKeyboardButton("⬅ К лигам", callback_data="back_leagues")])
        await query.edit_message_text(
            f"Матчи ({league_code.upper()}):",
            reply_markup=InlineKeyboardMarkup(buttons)
        )
    except Exception:
        await query.edit_message_text(
            f"Ошибка при загрузке матчей {league_code.upper()}",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅ К лигам", callback_data="back_leagues")]])
        )


async def handle_db_match_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    match_id = int(query.data.split("_", 1)[1])
    match = await fetch_match_with_teams(match_id)
    if not match:
        await query.edit_message_text(
            "Матч не найден.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅ Лиги", callback_data="back_leagues")]])
        )
        return
    header = (
        f"{match['home']['name']} vs {match['away']['name']}\n"
        f"{match['round']}\n"
        f"Kickoff: {match['utc_kickoff']:%Y-%m-%d %H:%M UTC}\n\nВыберите команду:"
    )
    buttons = [
        [InlineKeyboardButton(match["home"]["name"], callback_data=f"teamdb_{match['id']}_{match['home']['id']}")],
        [InlineKeyboardButton(match["away"]["name"], callback_data=f"teamdb_{match['id']}_{match['away']['id']}")],
        [InlineKeyboardButton("⬅ Матчи", callback_data=f"league_{match['tournament_code']}")],
        [InlineKeyboardButton("🏁 Лиги", callback_data="back_leagues")]
    ]
    await query.edit_message_text(header, reply_markup=InlineKeyboardMarkup(buttons))


# Из предыдущей версии – упрощённый вывод состава (можно оставить 4 линии, но экспорт есть отдельно)
def _line_group_tag(r):
    d = (r["position_detail"] or "").upper()
    pm = r["position_main"]
    if pm == "goalkeeper" or d == "GK":
        return "GK"
    DEF = {"CB", "LCB", "RCB", "LB", "RB", "LWB", "RWB"}
    MID_DEEP = {"DM", "CDM"}
    MID = {"CM", "AM", "CAM", "10"}
    WING = {"LW", "RW"}
    FWD = {"CF", "ST", "SS"}
    if d in DEF:
        return "DEF"
    if d in FWD:
        return "FWD"
    if d in WING:
        return "MID"
    if d in MID or d in MID_DEEP:
        return "MID"
    if pm == "defender":
        return "DEF"
    if pm == "forward":
        return "FWD"
    return "MID"


def _fmt_player_line(r):
    num = str(r["number"]) if r["number"] else "—"
    pos = r["position_detail"] or r["position_main"]
    return f"{num} {r['full_name']} ({pos}) {r['probability']}%"


def _fmt_player_out(r):
    num = str(r["number"]) if r["number"] else "—"
    pos = r["position_detail"] or r["position_main"]
    reason = r["status_reason"] or "Unavailable"
    return f"{num} {r['full_name']} ({pos}) — ❌ {reason}"


async def handle_team_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    parts = query.data.split("_", 2)
    if len(parts) < 3:
        await query.edit_message_text("Некорректный формат callback.")
        return
    match_id = int(parts[1])
    team_id = int(parts[2])

    rows = await fetch_team_lineup_predictions(match_id, team_id)
    if not rows:
        await query.edit_message_text(
            "Нет предиктов для этой команды.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅ Назад", callback_data=f"matchdb_{match_id}")]])
        )
        return

    formation_code = "4-2-3-1"
    raw_starters = [r for r in rows if r["will_start"] and r["status_availability"] != "OUT"]
    raw_starters.sort(key=lambda r: -r["probability"])
    starters = raw_starters[:11]
    out_players = [r for r in rows if r["status_availability"] == "OUT"]
    bench = [r for r in rows if not r["will_start"] and r["status_availability"] != "OUT"]

    for group in (starters, out_players, bench):
        for r in group:
            r["_grp"] = _line_group_tag(r)

    group_order = ["GK", "DEF", "MID", "FWD"]
    group_titles = {
        "GK": "🧤 GK",
        "DEF": "🛡 DEF",
        "MID": "⚙️ MID",
        "FWD": "🎯 FWD"
    }

    def render_group(players_list, fmt_func):
        blocks = []
        for g in group_order:
            items = [fmt_func(r) for r in players_list if r.get("_grp") == g]
            if items:
                blocks.append(group_titles[g] + ":\n" + "\n".join(items))
        return "\n\n".join(blocks) if blocks else "—"

    start_text = render_group(starters, _fmt_player_line)
    out_text = render_group(out_players, _fmt_player_out)
    bench_text = render_group(bench[:40], _fmt_player_line)

    lines = [
        f"Схема: {formation_code}",
        "✅ **Старт (11)**:",
        start_text,
        "",
        "❌ **Не сыграют**:",
        out_text,
        "",
        "🔁 **Скамейка / ротация**:",
        bench_text,
        "",
        "_/export_lineup {} {} md или csv для экспорта_".format(match_id, team_id)
    ]
    text = "\n".join(lines)
    if len(text) > 3900:
        text = text[:3900] + "\n… (обрезано)"

    buttons = [
        [InlineKeyboardButton("⬅ Другая команда", callback_data=f"matchdb_{match_id}")],
        [InlineKeyboardButton("🏁 Лиги", callback_data="back_leagues")]
    ]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode="Markdown")


async def debug_catch_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query:
        await update.callback_query.answer()
