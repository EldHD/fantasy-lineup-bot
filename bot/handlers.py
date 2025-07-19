from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from bot.db.crud import (
    fetch_matches_by_league,
    fetch_match_with_teams,
    fetch_team_lineup_predictions,
)
from bot.services.roster import sync_multiple_teams
from bot.services.predictions import generate_baseline_predictions

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

from sqlalchemy import select
from bot.db.database import SessionLocal
from bot.db.models import Tournament, Match, Player

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
            f"Произошла ошибка при загрузке матчей для {league_code.upper()} :(",
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
    starters = [r for r in rows if r["will_start"] and r["status_availability"] != "OUT"]
    starters.sort(key=lambda r: -r["probability"])
    starters = starters[:11]
    out_players = [r for r in rows if r["status_availability"] == "OUT"]
    bench = [r for r in rows if not r["will_start"] and r["status_availability"] != "OUT"]

    def line_tag(r):
        d = (r["position_detail"] or "").upper()
        pm = r["position_main"]
        if pm == "goalkeeper" or d == "GK": return "GK"
        DEF = {"CB","LCB","RCB","LB","RB","LWB","RWB"}
        DM = {"DM","CDM"}
        CM = {"CM"}
        AM = {"AM","CAM","10"}
        W = {"LW","RW"}
        CF = {"CF","ST","SS"}
        if d in DEF: return "DEF"
        if d in DM: return "DM"
        if d in CM: return "CM"
        if d in AM: return "AM"
        if d in W: return "WG"
        if d in CF: return "CF"
        if pm == "defender": return "DEF"
        if pm == "forward": return "CF"
        return "CM"

    for r in starters:
        r["_lt"] = line_tag(r)

    order_line = ["GK","DEF","DM","CM","AM","WG","CF"]
    starters_sorted = []
    for tag in order_line:
        starters_sorted.extend([r for r in starters if r["_lt"] == tag])
    starters_sorted.extend([r for r in starters if r not in starters_sorted])

    def fmt_player(r):
        num = (str(r["number"]) if r["number"] else "-").rjust(2)
        pos = r["position_detail"] or r["position_main"]
        return f"{num} {r['full_name']} ({pos}) {r['probability']}%"

    def block(tag, title):
        items = [fmt_player(r) for r in starters_sorted if r.get("_lt") == tag]
        if items:
            return f"{title}:\n" + "\n".join(items)
        return ""

    start_blocks = [
        block("GK", "🧤 GK"),
        block("DEF", "🛡 DEF"),
        block("DM", "🧱 DM"),
        block("CM", "⚙️ CM"),
        block("AM", "🎨 AM"),
        block("WG", "⚡ Wings"),
        block("CF", "🎯 CF"),
    ]
    start_text = "\n\n".join([b for b in start_blocks if b]) or "(нет данных)"

    def fmt_out(r):
        pos = r["position_detail"] or r["position_main"]
        reason = r["status_reason"] or "Unavailable"
        return f"{r['full_name']} ({pos}) — ❌ {reason}"

    def fmt_bench(r):
        pos = r["position_detail"] or r["position_main"]
        return f"{r['full_name']} ({pos}) {r['probability']}%"

    out_text = "\n".join(fmt_out(r) for r in out_players) if out_players else "—"
    bench_text = "\n".join(fmt_bench(r) for r in bench[:15]) if bench else "—"

    lines = [
        f"Схема: {formation_code}",
        f"✅ **Старт (11)**:",
        start_text,
        "",
        "❌ **Не сыграют**:",
        out_text,
        "",
        "🔁 **Скамейка / ротация**:",
        bench_text
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
