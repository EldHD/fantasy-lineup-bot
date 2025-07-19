from sqlalchemy import select, delete
from bot.db.database import SessionLocal
from bot.db.models import Player, Prediction, Match, PlayerStatus
from typing import List, Dict
import math


def _bucket(players, cond):
    return [p for p in players if cond(p)]


def _prob_for_slot(base: int, idx: int, total: int):
    # небольшая градация
    if total <= 1:
        return base
    step = 4
    return max(55, base - idx * step)


ROLE_ORDER = {"goalkeeper": 0, "defender": 1, "midfielder": 2, "forward": 3}

DEF_DETAILS = {"CB", "LCB", "RCB", "LB", "RB", "LWB", "RWB"}
DM_DETAILS = {"DM", "CDM"}
CM_DETAILS = {"CM"}
AM_DETAILS = {"AM", "CAM", "10"}
WING_DETAILS = {"LW", "RW"}
CF_DETAILS = {"CF", "ST", "SS"}

def classify_line(player):
    d = (player.position_detail or "").upper()
    pm = player.position_main
    if pm == "goalkeeper" or d == "GK":
        return "GK"
    if d in DEF_DETAILS:
        return "DEF"
    if d in DM_DETAILS:
        return "DM"
    if d in CM_DETAILS:
        return "CM"
    if d in AM_DETAILS:
        return "AM"
    if d in WING_DETAILS:
        return "WG"
    if d in CF_DETAILS:
        return "CF"
    # fallback
    if pm == "defender":
        return "DEF"
    if pm == "forward":
        return "CF"
    return "CM"


async def generate_baseline_predictions(match_id: int, team_id: int):
    """
    Генерируем 4-2-3-1:
    1 GK, 4 DEF, 2 (DM/CM), 3 (AM/WG/CM), 1 CF
    Остальные: bench; OUT — если статус availability=OUT (prob 10–25)
    """
    async with SessionLocal() as session:
        m_res = await session.execute(select(Match).where(Match.id == match_id))
        match = m_res.scalar_one_or_none()
        if not match:
            return f"Match {match_id} not found."

        p_res = await session.execute(select(Player).where(Player.team_id == team_id))
        players = p_res.scalars().all()
        if not players:
            return f"No players for team {team_id}."

        # statuses
        st_res = await session.execute(
            select(PlayerStatus).where(PlayerStatus.player_id.in_([p.id for p in players]))
        )
        statuses = st_res.scalars().all()
        by_player_status = {}
        for s in statuses:
            # берем самый свежий OUT приоритетно
            if s.availability == "OUT":
                by_player_status[s.player_id] = s

        # Классифицируем
        for p in players:
            p._line = classify_line(p)  # тип линии

        # СЛОТЫ
        gk_list = [p for p in players if p._line == "GK"]
        def_list = [p for p in players if p._line == "DEF"]
        dm_list = [p for p in players if p._line == "DM"]
        cm_list = [p for p in players if p._line == "CM"]
        am_list = [p for p in players if p._line == "AM"]
        wg_list = [p for p in players if p._line == "WG"]
        cf_list = [p for p in players if p._line == "CF"]

        # Сортировка внутри — по номеру, потом по алфавиту
        def sort_block(lst):
            return sorted(lst, key=lambda x: (x.shirt_number if x.shirt_number is not None else 999, x.full_name.lower()))

        gk_list = sort_block(gk_list)
        def_list = sort_block(def_list)
        dm_list = sort_block(dm_list)
        cm_list = sort_block(cm_list)
        am_list = sort_block(am_list)
        wg_list = sort_block(wg_list)
        cf_list = sort_block(cf_list)

        starters = []

        # 1 GK
        if gk_list:
            starters.append(gk_list[0])
        # 4 DEF
        starters.extend(def_list[:4])
        # 2 deeper mids (DM first then CM)
        deeper = dm_list + cm_list
        starters.extend(deeper[:2])
        # 3 attacking mids: prefer AM + Wingers + CM fallback
        att_pool = am_list + wg_list + cm_list[2:]  # если CM много
        starters.extend(att_pool[:3])
        # 1 CF
        if cf_list:
            # не добавляем дубликат если уже попал (редко)
            if cf_list[0] not in starters:
                starters.append(cf_list[0])

        # Если не добрали 11 — добьём любыми, кто не в OUT
        if len(starters) < 11:
            pool_extra = [p for p in players if p not in starters]
            starters.extend(pool_extra[:(11 - len(starters))])

        starter_ids = {p.id for p in starters}

        # Удаляем старые предикты
        await session.execute(delete(Prediction).where(Prediction.match_id == match_id))
        await session.flush()

        # Проставляем вероятности
        # Базу берём 92, чуть спускаем
        sorted_starters = []
        # Сгруппируем по желаемому порядку вывода
        line_order = ["GK", "DEF", "DM", "CM", "AM", "WG", "CF"]
        for lo in line_order:
            group = [p for p in starters if p._line == lo]
            sorted_starters.extend(group)
        # + остальные стартеры не в этом порядке
        rest = [p for p in starters if p not in sorted_starters]
        sorted_starters.extend(rest)

        total_start = len(sorted_starters)
        for idx, p in enumerate(sorted_starters):
            base_prob = 92
            prob = _prob_for_slot(base_prob, idx, total_start)
            # Если есть статус OUT — не должен быть в старте (но вдруг попал)
            if p.id in by_player_status:
                prob = 15
            session.add(Prediction(
                match_id=match_id,
                player_id=p.id,
                will_start=True,
                probability=prob,
                explanation="Auto 4-2-3-1 baseline"
            ))

        # Bench / OUT
        bench_candidates = [p for p in players if p.id not in starter_ids]
        for p in bench_candidates:
            if p.id in by_player_status:
                prob = 15
                will_start = False
                expl = "OUT status"
            else:
                prob = 60
                will_start = False
                expl = "Bench candidate"
            session.add(Prediction(
                match_id=match_id,
                player_id=p.id,
                will_start=will_start,
                probability=prob,
                explanation=expl
            ))

        await session.commit()
        return f"Predictions generated (4-2-3-1) starters={len(sorted_starters)}, bench={len(bench_candidates)}"
