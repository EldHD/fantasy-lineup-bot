from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from bot.db.crud import (
    fetch_matches_by_league,
    fetch_match_with_teams,
    fetch_team_lineup_predictions,
)

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
    return {
        "code": code,
        "def": parts[0],
        "mid": sum(parts[1:-1]),
        "fwd": parts[-1],
    }

def classify_role(row, formation_meta):
    pos_main = (row["position_main"] or "").lower()
    detail = (row["position_detail"] or "").upper()
    defenders = {"CB","RCB","LCB","RB","LB","RWB","LWB","CB-L","CB-R"}
    dm = {"DM","CDM","DMC"}
    mid_core = {"CM","RCM","LCM","CM-L","CM-R"}
    am = {"AM","CAM","LAM","RAM","10"}
    winger = {"RW","LW","W"}
    forward = {"CF","ST","FW","SS","9"}
    if pos_main == "goalkeeper" or detail == "GK":
        return "goalkeeper"
    if detail in defenders:
        return "defender"
    if detail in dm or detail in mid_core or detail in am:
        return "midfielder"
    if detail in forward:
        return "forward"
    if detail in winger:
        return "forward" if formation_meta["fwd"] >= 3 else "midfielder"
    if pos_main in ("defender","midfielder","forward"):
        return pos_main
    return "midfielder"


# -------- /start ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton(name, callback_data=f"league_{code}")] for name, code in LEAGUES]
    markup = InlineKeyboardMarkup(keyboard)
    if update.message:
        await update.message.reply_text("Выберите лигу:", reply_markup=markup)
    else:
        await context.bot.send_message(update.effective_chat.id, "Выберите лигу:", reply_markup=markup)


async def back_to_leagues(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await start(update, context)


# -------- Лига ----------
async def handle_league_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    raw = query.data
    league_code = raw.split("_", 1)[1]
    print(f"[CALLBACK] league_code={league_code}")

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
            kickoff = m["utc_kickoff"]
            # Подстрахуемся: если не datetime — просто строкой
            if hasattr(kickoff, "strftime"):
                ko_txt = kickoff.strftime("%Y-%m-%d %H:%M UTC")
            else:
                ko_txt = str(kickoff)
            txt = f"{m['home_team_name']} vs {m['away_team_name']} • {ko_txt}"
            buttons.append([InlineKeyboardButton(txt, callback_data=f"matchdb_{m['id']}")])

        buttons.append([InlineKeyboardButton("⬅ К лигам", callback_data="back_leagues")])
        await query.edit_message_text(
            f"Матчи ({league_code.upper()}):",
            reply_markup=InlineKeyboardMarkup(buttons)
        )
    except Exception as e:
        # Лог в консоль
        print(f"[ERROR] handle_league_selection {league_code}: {e}")
        import traceback; traceback.print_exc()
        # Сообщение пользователю
        await query.edit_message_text(
            f"Произошла ошибка при загрузке матчей для {league_code.upper()} :(",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅ К лигам", callback_data="back_leagues")]])
        )


# -------- Матч ----------
async def handle_db_match_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    match_id = int(query.data.split("_", 1)[1])
    print(f"[CALLBACK] match_id={match_id}")
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


# -------- Команда / предикт ----------
async def handle_team_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    parts = query.data.split("_", 2)
    if len(parts) < 3:
        await query.edit_message_text("Некорректный формат callback.")
        return
    match_id = int(parts[1])
    team_id = int(parts[2])
    print(f"[CALLBACK] team selection match={match_id} team={team_id}")

    rows = await fetch_team_lineup_predictions(match_id, team_id)
    if not rows:
        await query.edit_message_text(
            "Нет предиктов для этой команды.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅ Назад", callback_data=f"matchdb_{match_id}")]])
        )
        return

    formation_code = "4-2-3-1"
    fm = parse_formation(formation_code)
    for r in rows:
        r["_role"] = classify_role(r, fm)

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
    if gk_ok: starters.append(gk_ok[0])
    elif gk_doubt: starters.append(gk_doubt[0])
    else:
        any_left = ok_sorted + doubt_sorted
        if any_left: starters.append(any_left[0])
    starter_ids = {r["player_id"] for r in starters}

    def fill(role, need):
        nonlocal starters, starter_ids
        ok_pool = [r for r in ok_sorted if r["_role"] == role and r["player_id"] not in starter_ids]
        db_pool = [r for r in doubt_sorted if r["_role"] == role and r["player_id"] not in starter_ids]
        for pool in (ok_pool, db_pool):
            for r in pool:
                if len([s for s in starters if s["_role"] == role]) >= need:
                    break
                starters.append(r)
                starter_ids.add(r["player_id"])

    fill("defender", fm["def"])
    fill("midfielder", fm["mid"])
    fill("forward", fm["fwd"])

    if len(starters) < 11:
        remain = [r for r in ok_sorted + doubt_sorted if r["player_id"] not in starter_ids]
        for r in remain:
            if len(starters) >= 11:
                break
            starters.append(r)
            starter_ids.add(r["player_id"])

    potential = [r for r in ok_sorted + doubt_sorted if r["player_id"] not in starter_ids]

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
        expl = []
        if r["explanation"]:
            expl.append(r["explanation"])
        if r["status_reason"]:
            expl.append(r["status_reason"])
        if expl:
            line += "\n  " + "; ".join(expl)
        return line

    starters_txt = [fmt_line(r) for r in starters]
    out_txt = [fmt_line(r) for r in out_players]
    pot_txt = [fmt_line(r) for r in potential]

    parts_out = [
        f"Схема: {fm['code']}",
        "Предикт стартового состава:",
        "",
        "✅ Старт:",
        *starters_txt
    ]
    if len(starters_txt) < 11:
        parts_out.append(f"\n⚠️ Только {len(starters_txt)} игроков (недостаточно данных).")
    if out_txt:
        parts_out += ["", "❌ Не сыграют:", *out_txt]
    if pot_txt:
        parts_out += ["", "🔁 Возможны / скамейка:", *pot_txt]

    text = "\n".join(parts_out)
    if len(text) > 3900:
        text = text[:3900] + "\n… (обрезано)"

    buttons = [
        [InlineKeyboardButton("⬅ Другая команда", callback_data=f"matchdb_{match_id}")],
        [InlineKeyboardButton("🏁 Лиги", callback_data="back_leagues")]
    ]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons))


# --- Диагностическая команда ---
async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("pong")


# --- Catch-all логгер (временно) ---
async def debug_catch_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query:
        print("[CATCH-ALL] data =", update.callback_query.data)
        await update.callback_query.answer()
