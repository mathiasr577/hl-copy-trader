def check_and_copy_trades():
    wallets = load_wallets()
    state = load_paper_state()
    current_assets = {p["asset"] for p in state["positions"]}

    for w in wallets:
        address = w.get("address")
        stats = get_wallet_stats(address)
        perf = get_wallet_performance(address)
        
        # Filtro: win rate mínimo 60%
        win_rate = perf.get("win_rate", 0)
        if win_rate < 60:
            continue
        
        # Máximo 5 posiciones copiadas por wallet
        positions_from_wallet = [p for p in state["positions"] if p.get("copied_from", "").startswith(address[:10])]
        if len(positions_from_wallet) >= 5:
            continue
        
        # Ordenar posiciones por PNL descendente y tomar las mejores
        open_positions = sorted(
            stats.get("open_positions", []),
            key=lambda x: x.get("pnl", 0),
            reverse=True
        )
        
        slots_available = 5 - len(positions_from_wallet)
        
        for pos in open_positions[:slots_available]:
            asset = pos["asset"]
            if asset in current_assets:
                continue
            invest = state["balance"] * 0.05
            if invest < 1:
                continue
            price = get_current_price(asset)
            if price == 0:
                price = pos["entry_price"]
            new_position = {
                "asset": asset,
                "side": pos["side"],
                "entry_price": price,
                "size": invest / price if price > 0 else 0,
                "invested": invest,
                "opened_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "copied_from": address[:10] + "..." + address[-6:],
                "wallet_label": w.get("label", "Sin nombre")
            }
            state["balance"] -= invest
            state["positions"].append(new_position)
            current_assets.add(asset)

    # Actualizar precios en tiempo real
    for pos in state["positions"]:
        current_price = get_current_price(pos["asset"])
        if current_price > 0 and pos["entry_price"] > 0:
            if pos["side"] == "LONG":
                pnl = (current_price - pos["entry_price"]) / pos["entry_price"] * pos["invested"]
            else:
                pnl = (pos["entry_price"] - current_price) / pos["entry_price"] * pos["invested"]
            pos["current_price"] = current_price
            pos["unrealized_pnl"] = round(pnl, 2)
            pos["pnl_pct"] = round((pnl / pos["invested"]) * 100, 2)

    save_paper_state(state)
    return state