from sqlalchemy import select, delete
from bot.db.database import SessionLocal
from bot.db.models import Player, Prediction, Match, PlayerStatus
from typing import List, Dict

# Расширяем отображение деталей в унифицированные линии
ROLE_MAP_DETAIL = {
    "GK": "GK",
    "CB": "DEF", "LCB": "DEF", "RCB": "DEF",
    "LB": "DEF", "RB": "DEF", "LWB": "DEF", "RWB": "DEF",
    "DM": "DM", "CDM": "DM",
    "CM": "CM",
    "AM": "AM", "CAM": "AM", "10": "AM",
    "LW": "WG", "RW": "WG",
    "CF": "CF", "ST": "CF", "SS": "CF", "STRIKER": "CF", "FORWARD": "CF"
}


def classify_line(player):
    d = (player.position_detail or "").upper()
    pm = player.position_main
    if pm == "goalkeeper" or d == "GK":
        return "GK"
    if d in ROLE_MAP_DETAIL:
        return ROLE_MAP_DETAIL[d]
    # эвристики по тексту
    if "BACK" in d:
        return "DEF"
    if "WING" in d:
        return "WG"
    if "STRIK" in d or "FORWARD" in d or "ATT" in d:
        return "CF"
    if "MID" in d:
        # если есть DEF в тексте — опорник
        if "DEF" in d:
            return "DM"
        if "ATT" in d:
            return "AM"
        return "CM"
    # fallback по основной позиции
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


def distribute_starters(healthy_players):
    """
    Гибкая сборка 4-2-3-1:
    - 1 GK
    - 4 DEF
    - 2 (DM/CM)
    - 3 (AM/WG/CM)
    - 1 CF (fallback если нет)
    Всегда возвращает ровно 11 (если игроков >= 11).
    """
    # Группы
    gk = sort_players([p for p in healthy_players if p._line == "GK"])
    df = sort_players([p for p in healthy_players if p._line == "DEF"])
    dm = sort_players([p for p in healthy_players if p._line == "DM"])
    cm = sort_players([p for p in healthy_players if p._line == "CM"])
    am = sort_players([p for p in healthy_players if p._line == "AM"])
    wg = sort_players([p for p in healthy_players if p._line == "WG"])
    cf = sort_players([p for p in healthy_players if p._line == "CF"])

    starters = []

    # 1 GK
    if gk:
        starters.append(gk[0])

    # 4 DEF (или сколько есть)
    starters.extend(df[:4])

    # 2 deeper mids (DM приоритет, потом CM)
    deeper_pool = dm + cm
    starters.extend(deeper_pool[:2])

    # 3 атакующие (AM + WG + оставшиеся CM)
    att_pool = am + wg + cm[2:]
    for p in att_pool:
        if len([s for s in starters if s not in gk]) >= 1 + 4 + 2 + 3:  # уже взяли нужное
            break
        if p not in starters:
            starters.append(p)

    # CF
    if cf:
        # берём лучшего
        best_cf = cf[0]
        if best_cf not in starters:
            starters.append(best_cf)
    else:
        # Fallback: попытка взять ещё одного атакующего из AM/WG/CM/DM
        fallback_pool = am + wg + cm + dm
        for cand in fallback_pool:
            if cand not in starters:
                starters.append(cand)
                break

    # Теперь доводим до 11, если вдруг ещё меньше
    if len(starters) < 11:
        remaining = [p for p in healthy_players if p not in starters]
        starters.extend(remaining[:(11 - len(starters))])

    # Ровно 11 (если игроков достаточно)
    return starters[:11]


def assign_probabilities(starters, bench, statuses_map):
    """
    Возвращает {player_id: (will_start, probability, explanation)}
    OUT = 3%, will_start=False.
    Bench = 60%.
    Стартеры 95→80 плавной линейкой.
    """
    result = {}

    line_priority = {"GK": 0, "DEF": 1, "DM": 2, "CM": 3, "AM": 4, "WG": 5, "CF": 6}
    starters_sorted = sorted(starters, key=lambda p: (line_priority.get(p._line, 9), p.full_name.lower()))
    total = len(starters_sorted)

    for idx, p in enumerate(starters_sorted):
        st = statuses_map.get(p.id)
        if st and st.availability == "OUT":
            result[p.id] = (False, 3, "OUT (injury)")
            continue
        # линейная интерполяция стартовых
        if total > 1:
            frac = idx / (total - 1)
            prob = round(95 - (95 - 80) * frac)
        else:
            prob = 92
        result[p.id] = (True, prob, "Predicted starter 4-2-3-1")

    for p in bench:
        st = statuses_map.get(p.id)
        if st and st.availability == "OUT":
            result[p.id] = (False, 3, "OUT (injury)")
        else:
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
            # Просто первый встретившийся OUT фиксируем (для MVP)
            if s.player_id not in latest_status:
                latest_status[s.player_id] = s

        # Классификация + разделение health / out
        healthy = []
        out_list = []
        for p in players:
            p._line = classify_line(p)
            st = latest_status.get(p.id)
            if st and st.availability == "OUT":
                out_list.append(p)
            else:
                healthy.append(p)

        starters = distribute_starters(healthy)
        starter_ids = {p.id for p in starters}
        bench = [p for p in healthy if p.id not in starter_ids] + out_list

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
        return f"Predictions generated (4-2-3-1 improved) starters={len(starters)}, total_players={len(players)}"
