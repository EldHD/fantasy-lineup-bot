from sqlalchemy import select, delete
from bot.db.database import SessionLocal
from bot.db.models import Player, Prediction, Match, PlayerStatus
from typing import List

ROLE_MAP_DETAIL = {
    "GK": "GK",
    "CB": "DEF", "LCB": "DEF", "RCB": "DEF",
    "LB": "DEF", "RB": "DEF", "LWB": "DEF", "RWB": "DEF",
    "DM": "DM", "CDM": "DM",
    "CM": "CM",
    "AM": "AM", "CAM": "AM", "10": "AM",
    "LW": "WG", "RW": "WG",
    "CF": "CF", "ST": "CF", "SS": "CF"
}

def classify_line(player):
    d = (player.position_detail or "").upper()
    pm = player.position_main
    if pm == "goalkeeper" or d == "GK":
        return "GK"
    if d in ROLE_MAP_DETAIL:
        return ROLE_MAP_DETAIL[d]
    if pm == "defender":
        return "DEF"
    if pm == "forward":
        return "CF"
    if pm == "midfielder":
        return "CM"
    return "CM"


def sort_players(block):
    return sorted(block, key=lambda x: (
        x.shirt_number if x.shirt_number is not None else 999,
        x.full_name.lower()
    ))


def distribute_starters(players):
    """
    Схема 4-2-3-1
    1 GK, 4 DEF, 2 (DM/CM), 3 (AM/WG/CM), 1 CF
    """
    gk = [p for p in players if p._line == "GK"]
    df = [p for p in players if p._line == "DEF"]
    dm = [p for p in players if p._line == "DM"]
    cm = [p for p in players if p._line == "CM"]
    am = [p for p in players if p._line == "AM"]
    wg = [p for p in players if p._line == "WG"]
    cf = [p for p in players if p._line == "CF"]

    gk = sort_players(gk)
    df = sort_players(df)
    dm = sort_players(dm)
    cm = sort_players(cm)
    am = sort_players(am)
    wg = sort_players(wg)
    cf = sort_players(cf)

    starters = []

    # 1 GK
    if gk: starters.append(gk[0])

    # 4 DEF
    starters.extend(df[:4])

    # 2 deeper mids (DM first, then CM)
    deeper_pool = dm + cm
    starters.extend(deeper_pool[:2])

    # 3 attacking mids: AM + WG + оставшиеся CM
    att_pool = am + wg + cm[2:]
    starters.extend(att_pool[:3])

    # 1 CF
    if cf:
        if cf[0] not in starters:
            starters.append(cf[0])

    # Если не 11 — добираем из оставшихся
    if len(starters) < 11:
        remaining = [p for p in players if p not in starters]
        starters.extend(remaining[:(11 - len(starters))])

    # Ровно 11
    return starters[:11]


def assign_probabilities(starters, bench, statuses_map):
    """
    Возвращает dict player_id -> (will_start, probability, explanation)
    OUT не в старте, bench/out получают свои диапазоны.
    """
    result = {}

    # Порядок для градации
    line_priority = {"GK": 0, "DEF": 1, "DM": 2, "CM": 3, "AM": 4, "WG": 5, "CF": 6}
    starters_sorted = sorted(starters, key=lambda p: (line_priority.get(p._line, 9), p.full_name.lower()))

    total = len(starters_sorted)
    for idx, p in enumerate(starters_sorted):
        base_top = 95
        base_low = 80
        # линейная интерполяция
        if total > 1:
            frac = idx / (total - 1)
            prob = round(base_top - (base_top - base_low) * frac)
        else:
            prob = 93
        st = statuses_map.get(p.id)
        if st and st.availability == "OUT":
            # на случай если по ошибке попал — но мы исключаем выше
            result[p.id] = (False, 3, "OUT (injury)")
        else:
            result[p.id] = (True, prob, "Predicted starter 4-2-3-1")

    # BENCH
    for p in bench:
        st = statuses_map.get(p.id)
        if st and st.availability == "OUT":
            result[p.id] = (False, 3, "OUT (injury)")
        else:
            # простая базовая вероятность выхода в старт (не стартует) — 60
            result[p.id] = (False, 60, "Bench / rotation")

    return result


async def generate_baseline_predictions(match_id: int, team_id: int):
    async with SessionLocal() as session:
        m_res = await session.execute(select(Match).where(Match.id == match_id))
        match = m_res.scalar_one_or_none()
        if not match:
            return f"Match {match_id} not found."

        p_res = await session.execute(select(Player).where(Player.team_id == team_id))
        players = p_res.scalars().all()
        if not players:
            return f"No players for team {team_id}."

        st_res = await session.execute(
            select(PlayerStatus).where(PlayerStatus.player_id.in_([p.id for p in players]))
        )
        statuses = st_res.scalars().all()
        latest_status = {}
        for s in statuses:
            # первый OUT сохраняем, остальные игнор
            if s.player_id not in latest_status:
                latest_status[s.player_id] = s

        # Проставим линии
        healthy_players = []
        out_players = []
        for p in players:
            p._line = classify_line(p)
            st = latest_status.get(p.id)
            if st and st.availability == "OUT":
                out_players.append(p)
            else:
                healthy_players.append(p)

        # Формируем старт из здоровых
        starters = distribute_starters(healthy_players)
        starter_ids = {p.id for p in starters}
        bench = [p for p in healthy_players if p.id not in starter_ids] + out_players

        # Удаляем старые предикты
        await session.execute(delete(Prediction).where(Prediction.match_id == match_id))
        await session.flush()

        probs = assign_probabilities(starters, bench, latest_status)

        for p in players:
            will_start, probability, explanation = probs[p.id]
            session.add(Prediction(
                match_id=match_id,
                player_id=p.id,
                will_start=will_start,
                probability=probability,
                explanation=explanation
            ))
        await session.commit()
        return f"Predictions generated (improved 4-2-3-1) starters={len(starters)}, total_players={len(players)}"
