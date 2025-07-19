from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from bot.db.crud import (
    fetch_matches_by_league,
    fetch_match_with_teams,
    fetch_team_lineup_predictions,
)
from bot.db.seed import auto_seed  # если понадобится ручной перезапуск сидера (можно убрать позже)
from bot.db.seed import auto_seed as _dummy  # для линтера
from bot.db.seed import auto_seed as _unused   # заглушки при необходимости

LEAGUES = [
    ("Premier League", "epl"),
    ("La Liga", "laliga"),
    ("Serie A", "seriea"),
    ("Bundesliga", "bundesliga"),
    ("Ligue 1", "ligue1"),
    ("Russian Premier League", "rpl"),
]

TEAM_FORMATIONS = {
    "Arsenal": ["4-2-3-1"],
    "Chelsea": ["4-2-3-1"],
    "Zenit": ["4-2-3-1"],
    "CSKA Moscow": ["4-3-3"],
}


def parse_formation(code: str):
    parts = [int(p) for p in code.split("-")]
    defenders = parts[0]
    forwards = parts[-1]
    mids = sum(parts[1:-1])
    return {"code": code, "def": defenders, "mid": mids, "fwd": forwards}


def classify_role(row, formation_meta):
    pos_main = row["position_main"].lower()
    detail = (row["position_detail"] or "").upper()
    defenders = {"CB", "RCB", "LCB", "RB", "LB", "RWB", "LWB", "CB-L", "CB-R"}
    dm_set = {"DM", "CDM", "DMC"}
    mid_core = {"CM", "RCM", "LCM", "CM-L", "CM-R"}
    am_set = {"AM", "CAM", "LAM", "RAM", "10"}
    winger_set = {"RW", "LW", "W"}
    forward_set = {"CF", "ST", "FW", "SS", "9"}

    if pos_main == "goalkeeper" or detail == "GK":
        return "goalkeeper"
    if detail in defenders:
        return "defender"
    if detail in dm_set or detail in mid_core or detail in am_set:
        return "midfielder"
    if detail in forward_set:
        return "forward"
    if detail in winger_set:
        if formation_meta["fwd"] >= 3:
            return "forward"
        else:
            return "midfielder"
    if pos_main in ("defender", "midfielder", "forward"):
        return pos_main
    return "midfielder"


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton(name, callback_data=f"league_{code}")]
        for name, code in LEAGUES
    ]
    markup = InlineKeyboardMarkup(keyboard)
    if update.message:
        await update.message.reply_text("Выберите лигу:", reply_markup=markup)
    else:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="Выберите лигу:", reply_markup=markup)


async def back_to_leagues(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await start(update, context)


async def handle_league_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    league_code = query.data.split("_", 1)[1]
    print("DEBUG: league callback received:", league_code)
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
        txt = f"{m['home_team_name']} vs {m['away_team_name']} • {m['utc_kickoff']:%Y-%m-%d %H:%M UTC}"
        buttons.append([InlineKeyboardButton(txt, callback_data=f"matchdb_{m['id']}")])
    buttons.append([InlineKeyboardButton("⬅ К лигам", callback_data="back_leagues")])
    await query.edit_message_text(
        f"Матчи ({league_code.upper()}):",
        reply_markup=InlineKeyboardMarkup(buttons)
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
    buttons = [
        [InlineKeyboardButton(match["home"]["name"], callback_data=f"teamdb_{match['id']}_{match['home']['id']}")],
        [InlineKeyboardButton(match["away"]["name"], callback_data=f"teamdb_{match['id']}_{match['away']['id']}")],
        [InlineKeyboardButton("⬅ Матчи", callback_data=f"league_{match['tournament_code']}")],
        [InlineKeyboardButton("🏁 Лиги", callback_data="back_leagues")]
    ]
    header = (
        f"{match['home']['name']} vs {match['away']['name']}\n"
        f"{match['round']}\n"
        f"Kickoff: {match['utc_kickoff']:%Y-%m-%d %H:%M UTC}\n\nВыберите команду:"
    )
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
    formation_meta = parse_formation(formation_code)

    for r in rows:
        r["_role"] = classify_role(r, formation_meta)

    out_players = [r for r in rows if r["status_availability"] == "OUT"]
    doubt_players = [r for r in rows if r["status_availability"] == "DOUBT"]
    ok_players = [r for r in rows if r["status_availability"] in (None, "OK")]

    def base_sort(rs):
        return sorted(
            rs,
            key=lambda r: (
                {"goalkeeper": 0, "defender": 1, "midfielder": 2, "forward": 3}.get(r["_role"], 99),
                -r["probability"],
                r["full_name"].lower()
            )
        )

    ok_sorted = base_sort(ok_players)
    doubt_sorted = base_sort(doubt_players)

    starters = []
    # GK
    gk_ok = [r for r in ok_sorted if r["_role"] == "goalkeeper"]
    gk_doubt = [r for r in doubt_sorted if r["_role"] == "goalkeeper"]
    if gk_ok:
        starters.append(gk_ok[0])
    elif gk_doubt:
        starters.append(gk_doubt[0])
    else:
        candidates_any = ok_sorted + doubt_sorted
        if candidates_any:
            starters.append(candidates_any[0])

    starter_ids = {r["player_id"] for r in starters}

    def fill_role(role, need):
        nonlocal starters, starter_ids
        ok_pool = [r for r in ok_sorted if r["_role"] == role and r["player_id"] not in starter_ids]
        doubt_pool = [r for r in doubt_sorted if r["_role"] == role and r["player_id"] not in starter_ids]
        for pool in (ok_pool, doubt_pool):
            for r in pool:
                if len([s for s in starters if s["_role"] == role]) >= need:
                    break
                starters.append(r)
                starter_ids.add(r["player_id"])

    fill_role("defender", formation_meta["def"])
    fill_role("midfielder", formation_meta["mid"])
    fill_role("forward", formation_meta["fwd"])

    if len(starters) < 11:
        remaining = [r for r in ok_sorted + doubt_sorted if r["player_id"] not in starter_ids]
        for r in remaining:
            if len(starters) >= 11:
                break
            starters.append(r)
            starter_ids.add(r["player_id"])

    potential = []
    for r in ok_sorted + doubt_sorted:
        if r["player_id"] not in starter_ids:
            potential.append(r)

    def fmt_line(r):
        pos = r["position_detail"] or r["position_main"]
        tags = []
        if r["status_availability"] == "DOUBT":
            tags.append("❓ Doubt")
            if r in starters:
                tags.append("(* риск)")
        if r["status_availability"] == "OUT":
            tags.append("❌ OUT")
        line = f"{r['number'] or '-'} {r['full_name']} — {pos} | {r['probability']}%"
        if tags:
            line += " | " + " ".join(tags)
        reason_parts = []
        if r["explanation"]:
            reason_parts.append(r["explanation"])
        if r["status_reason"]:
            reason_parts.append(r["status_reason"])
        if reason_parts:
            line += "\n  " + "; ".join(reason_parts)
        return line

    starters_txt = [fmt_line(r) for r in starters]
    out_txt = [fmt_line(r) for r in out_players]
    potential_txt = [fmt_line(r) for r in potential]

    text_parts = [
        f"Схема: {formation_meta['code']}",
        "Предикт стартового состава (позиционно):",
        "",
        "✅ Старт:",
        *starters_txt
    ]
    if len(starters_txt) < 11:
        text_parts.append(f"\n⚠️ Только {len(starters_txt)} игроков (недостаточно данных).")
    if out_txt:
        text_parts += ["", "❌ Не сыграют:", *out_txt]
    if potential_txt:
        text_parts += ["", "🔁 Возможны / скамейка:", *potential_txt]

    text = "\n".join(text_parts)
    if len(text) > 3900:
        text = text[:3900] + "\n… (обрезано)"

    buttons = [
        [InlineKeyboardButton("⬅ Другая команда", callback_data=f"matchdb_{match_id}")],
        [InlineKeyboardButton("🏁 Лиги", callback_data="back_leagues")]
    ]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons))
