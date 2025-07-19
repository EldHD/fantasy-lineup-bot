from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from bot.db.crud import (
    fetch_matches_by_league,
    fetch_match_with_teams,
    fetch_team_lineup_predictions,
)
from bot.db.seed import force_players_reset  # /force_seed (можно убрать)

LEAGUES = [
    ("Premier League", "epl"),
    ("La Liga", "laliga"),
    ("Serie A", "seriea"),
    ("Bundesliga", "bundesliga"),
    ("Ligue 1", "ligue1"),
    ("Russian Premier League", "rpl"),
]

# Предпочтительные схемы (primary first)
TEAM_FORMATIONS = {
    "Arsenal": ["4-3-3", "4-2-3-1"],
    "Chelsea": ["4-2-3-1", "3-4-2-1"],
    "Zenit": ["4-2-3-1"],
    "CSKA Moscow": ["4-3-3"],
    # добавишь остальные позже
}


# ---------- Утилиты схем ----------

def parse_formation(code: str):
    """
    Возвращает dict: {'def': x, 'mid': y, 'fwd': z} + оригинал.
    Поддерживаем форматы: "4-3-3", "4-2-3-1", "3-4-2-1" (где нужно объединить средние).
    Правило: последний элемент = нападающие.
    Остальные элементы между первым и последним суммируются как midfielders.
    """
    parts = [int(p) for p in code.split("-")]
    if len(parts) < 3:
        raise ValueError(f"Unsupported formation code: {code}")
    defenders = parts[0]
    forwards = parts[-1]
    mids = sum(parts[1:-1])
    return {
        "code": code,
        "def": defenders,
        "mid": mids,
        "fwd": forwards,
    }


def classify_role(row, formation_meta):
    """
    Возвращает основную группу: goalkeeper | defender | midfielder | forward
    С учётом wingers (RW/LW/W): если forwards >=3 (например 4-3-3) -> winger -> forward,
    иначе -> midfielder.
    """
    pos_main = row["position_main"].lower()
    detail = (row["position_detail"] or "").upper()

    if pos_main == "goalkeeper" or detail == "GK":
        return "goalkeeper"

    # Унифицированные наборы
    defenders = {"CB", "RCB", "LCB", "RB", "LB", "RWB", "LWB", "CB-L", "CB-R"}
    dm_set = {"DM", "CDM", "DMC"}
    mid_core = {"CM", "RCM", "LCM", "CM-L", "CM-R"}
    am_set = {"AM", "CAM", "LAM", "RAM", "10"}
    winger_set = {"RW", "LW", "W"}
    forward_set = {"CF", "ST", "FW", "SS", "9"}

    # By detail first
    if detail in defenders:
        return "defender"
    if detail in dm_set or detail in mid_core or detail in am_set:
        return "midfielder"
    if detail in forward_set:
        return "forward"
    if detail in winger_set:
        # решаем по схеме
        if formation_meta["fwd"] >= 3:
            return "forward"
        else:
            return "midfielder"

    # fallback по main
    if pos_main == "defender":
        return "defender"
    if pos_main == "midfielder":
        return "midfielder"
    if pos_main == "forward":
        return "forward"

    # по умолчанию midfielder
    return "midfielder"


# ---------- Хендлеры ----------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton(name, callback_data=f"league_{code}")]
        for name, code in LEAGUES
    ]
    markup = InlineKeyboardMarkup(keyboard)
    if update.message:
        await update.message.reply_text("Выберите лигу:", reply_markup=markup)
    else:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Выберите лигу:",
            reply_markup=markup
        )


async def back_to_leagues(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await start(update, context)


async def handle_league_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    league_code = query.data.split("_", 1)[1]

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
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("⬅ Лиги", callback_data="back_leagues")]]
            )
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
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("⬅ Назад", callback_data=f"matchdb_{match_id}")]]
            )
        )
        return

    # Получим имя команды (есть в data? — пока нет → выведем без)
    # Можно позже дополнить fetch_team_lineup_predictions возвратом team_name.

    # Определяем схему
    # Попытаемся найти по названию команды через одного из игроков (берём первую строку)
    team_name_guess = None
    # (Опционально можно хранить map player_id -> team_name)
    # Сейчас пропустим и просто используем словарь по умолчанию — без имени fallback.

    formation_list = []
    if team_name_guess and team_name_guess in TEAM_FORMATIONS:
        formation_list = TEAM_FORMATIONS[team_name_guess]
    else:
        # fallback — возьмём 4-2-3-1 как универсальную
        # (Для примера: Zenit, Arsenal, Chelsea — есть в словаре; если не найдёт — дефолт)
        formation_list = TEAM_FORMATIONS.get(team_name_guess, ["4-2-3-1"])

    formation_code = formation_list[0]
    formation_meta = parse_formation(formation_code)

    # Группируем по статусу
    out_players = [r for r in rows if r["status_availability"] == "OUT"]
    doubt_players = [r for r in rows if r["status_availability"] == "DOUBT"]
    ok_players = [r for r in rows if r["status_availability"] in (None, "OK")]

    # Классификация ролей под схему
    for r in rows:
        r["_role"] = classify_role(r, formation_meta)

    # Сортировка кандидатов внутри своих групп
    def prob_sort(rs):
        return sorted(
            rs,
            key=lambda r: (
                {"goalkeeper": 0, "defender": 1, "midfielder": 2, "forward": 3}.get(r["_role"], 99),
                -r["probability"],
                r["full_name"].lower()
            )
        )

    ok_sorted = prob_sort(ok_players)
    doubt_sorted = prob_sort(doubt_players)

    # Отбор
    starters = []

    # 1. GK
    gk_ok = [r for r in ok_sorted if r["_role"] == "goalkeeper"]
    gk_doubt = [r for r in doubt_sorted if r["_role"] == "goalkeeper"]
    if gk_ok:
        starters.append(gk_ok[0])
    elif gk_doubt:
        starters.append(gk_doubt[0])
    else:
        # Крайний случай — нет GK
        candidates_any = (ok_sorted + doubt_sorted)
        if candidates_any:
            starters.append(candidates_any[0])

    starter_ids = {r["player_id"] for r in starters}

    # 2. DEF
    need_def = formation_meta["def"]
    def_pool_ok = [r for r in ok_sorted if r["_role"] == "defender" and r["player_id"] not in starter_ids]
    def_pool_doubt = [r for r in doubt_sorted if r["_role"] == "defender" and r["player_id"] not in starter_ids]

    for pool in (def_pool_ok, def_pool_doubt):
        for r in pool:
            if len([s for s in starters if s["_role"] == "defender"]) >= need_def:
                break
            starters.append(r)
            starter_ids.add(r["player_id"])

    # 3. MID
    need_mid = formation_meta["mid"]
    mid_pool_ok = [r for r in ok_sorted if r["_role"] == "midfielder" and r["player_id"] not in starter_ids]
    mid_pool_doubt = [r for r in doubt_sorted if r["_role"] == "midfielder" and r["player_id"] not in starter_ids]

    for pool in (mid_pool_ok, mid_pool_doubt):
        for r in pool:
            if len([s for s in starters if s["_role"] == "midfielder"]) >= need_mid:
                break
            starters.append(r)
            starter_ids.add(r["player_id"])

    # 4. FWD
    need_fwd = formation_meta["fwd"]
    fwd_pool_ok = [r for r in ok_sorted if r["_role"] == "forward" and r["player_id"] not in starter_ids]
    fwd_pool_doubt = [r for r in doubt_sorted if r["_role"] == "forward" and r["player_id"] not in starter_ids]

    for pool in (fwd_pool_ok, fwd_pool_doubt):
        for r in pool:
            if len([s for s in starters if s["_role"] == "forward"]) >= need_fwd:
                break
            starters.append(r)
            starter_ids.add(r["player_id"])

    # 5. Если < 11 добираем лучших из оставшихся (OK → DOUBT)
    if len(starters) < 11:
        remaining_ok = [r for r in ok_sorted if r["player_id"] not in starter_ids]
        remaining_doubt = [r for r in doubt_sorted if r["player_id"] not in starter_ids]
        for r in remaining_ok + remaining_doubt:
            if len(starters) >= 11:
                break
            starters.append(r)
            starter_ids.add(r["player_id"])

    # Потенциал
    potential = []
    used_ids = starter_ids
    for r in ok_sorted + doubt_sorted:
        if r["player_id"] not in used_ids:
            potential.append(r)

    # Форматирование
    def fmt_line(r):
        pos = r["position_detail"] or r["position_main"]
        tags = []
        if r["status_availability"] == "DOUBT":
            tags.append("❓ Doubt")
        if r["status_availability"] == "OUT":
            tags.append("❌ OUT")  # (theoretical, не должны попасть в старт)
        if r["status_availability"] == "DOUBT" and r in starters:
            tags.append("(* риск)")
        line = f"{r['number'] or '-'} {r['full_name']} — {pos} | {r['probability']}%"
        if tags:
            line += " | " + " ".join(tags)
        explain_parts = []
        if r["explanation"]:
            explain_parts.append(r["explanation"])
        if r["status_reason"]:
            explain_parts.append(r["status_reason"])
        if explain_parts:
            line += "\n  " + "; ".join(explain_parts)
        return line

    starters_formatted = [fmt_line(r) for r in starters]
    out_formatted = []
    for r in out_players:
        out_formatted.append(fmt_line(r))
    potential_formatted = [fmt_line(r) for r in potential]

    text_parts = [
        f"Схема: {formation_meta['code']}",
        "Предикт стартового состава (позиционно):\n",
        "✅ Старт:\n" + "\n".join(starters_formatted)
    ]

    if len(starters_formatted) < 11:
        text_parts.append(f"\n⚠️ Только {len(starters_formatted)} игроков в старте (недостаточно данных).")

    if out_formatted:
        text_parts.append("\n❌ Не сыграют:\n" + "\n".join(out_formatted))

    if potential_formatted:
        text_parts.append("\n🔁 Возможны / скамейка:\n" + "\n".join(potential_formatted))

    text = "\n".join(text_parts)
    if len(text) > 3900:
        text = text[:3900] + "\n… (обрезано)"

    buttons = [
        [InlineKeyboardButton("⬅ Другая команда", callback_data=f"matchdb_{match_id}")],
        [InlineKeyboardButton("🏁 Лиги", callback_data="back_leagues")]
    ]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons))


# /force_seed
async def force_seed_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⏳ Пересоздаю игроков/предикты/статусы...")
    await force_players_reset()
    await update.message.reply_text("✅ Готово. /start")
