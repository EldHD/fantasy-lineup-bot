async def handle_team_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    parts = query.data.split("_", 2)
    if len(parts) < 3:
        await query.edit_message_text("Некорректный формат callback.")
        return

    match_id = int(parts[1])
    team_id = int(parts[2])

    preds, status_map = await fetch_team_lineup_predictions(match_id, team_id)
    if not preds:
        await query.edit_message_text("Нет предиктов для этой команды.",
                                      reply_markup=InlineKeyboardMarkup(
                                          [[InlineKeyboardButton("⬅ Назад", callback_data=f"matchdb_{match_id}")]]
                                      ))
        return

    starters = []
    out_or_doubt = []

    for pr in preds:
        p = pr.player
        st = status_map.get(p.id)
        pos = p.position_detail or p.position_main
        availability_tag = ""
        if st:
            if st.availability == "OUT":
                availability_tag = "❌ OUT"
            elif st.availability == "DOUBT":
                availability_tag = "❓ Doubt"
        base_line = f"{p.shirt_number or '-'} {p.full_name} — {pos} | {pr.probability}%"
        if availability_tag:
            base_line += f" | {availability_tag}"

        explain = pr.explanation or ""
        if st and st.reason:
            explain += ("; " if explain else "") + st.reason

        formatted = base_line + ("\n  " + explain if explain else "")

        if st and st.availability in ("OUT", "DOUBT"):
            out_or_doubt.append(formatted)
        else:
            if pr.will_start:
                starters.append(formatted)
            else:
                # Если позже будут bench-предикты
                starters.append(formatted)

    text_parts = ["Предикт стартового состава:\n"]
    if starters:
        text_parts.append("✅ Ожидаемые в старте:\n" + "\n".join(starters))
    if out_or_doubt:
        text_parts.append("\n🚑 OUT / DOUBT:\n" + "\n".join(out_or_doubt))

    text = "\n".join(text_parts)
    buttons = [
        [InlineKeyboardButton("⬅ Другая команда", callback_data=f"matchdb_{match_id}")],
        [InlineKeyboardButton("🏁 Лиги", callback_data="back_leagues")]
    ]
    await query.edit_message_text(text[:3900], reply_markup=InlineKeyboardMarkup(buttons))
