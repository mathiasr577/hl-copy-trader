import requests
import json
import os
import threading
import websocket
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

HL_API_URL = os.getenv("HL_API_URL", "https://api.hyperliquid.xyz/info")
HL_WS_URL = "wss://api.hyperliquid.xyz/ws"

wallet_positions = {}
ws_app = None
ws_thread = None

def get_current_price(asset):
    try:
        payload = {"type": "allMids"}
        r = requests.post(HL_API_URL, json=payload)
        mids = r.json()
        return float(mids.get(asset, 0))
    except:
        return 0

def get_wallet_stats(address):
    try:
        payload = {"type": "clearinghouseState", "user": address}
        r = requests.post(HL_API_URL, json=payload)
        data = r.json()
        positions = data.get("assetPositions", [])
        open_positions = []
        for p in positions:
            pos = p.get("position", {})
            size = float(pos.get("szi", 0))
            if size != 0:
                entry_px = float(pos.get("entryPx", 0))
                unrealized_pnl = float(pos.get("unrealizedPnl", 0))
                open_positions.append({
                    "asset": pos.get("coin"),
                    "size": size,
                    "entry_price": entry_px,
                    "pnl": unrealized_pnl,
                    "side": "LONG" if size > 0 else "SHORT"
                })
        wallet_positions[address] = open_positions
        return {
            "address": address,
            "open_positions": open_positions,
            "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
    except Exception as e:
        return {"address": address, "error": str(e), "open_positions": []}

def get_wallet_performance(address):
    try:
        payload = {"type": "userFills", "user": address}
        r = requests.post(HL_API_URL, json=payload)
        fills = r.json()
        if not isinstance(fills, list):
            return {"win_rate": 0, "total_trades": 0, "wins": 0}
        wins = 0
        total = 0
        for fill in fills:
            closed_pnl = float(fill.get("closedPnl", 0))
            if closed_pnl != 0:
                total += 1
                if closed_pnl > 0:
                    wins += 1
        win_rate = (wins / total * 100) if total > 0 else 0
        return {"win_rate": round(win_rate, 2), "total_trades": total, "wins": wins}
    except Exception as e:
        return {"win_rate": 0, "total_trades": 0, "error": str(e)}

def load_wallets():
    try:
        with open("wallets.json", "r") as f:
            return json.load(f)
    except:
        return []

def save_wallets(wallets):
    with open("wallets.json", "w") as f:
        json.dump(wallets, f, indent=2)

def load_paper_state():
    try:
        with open("paper_state.json", "r") as f:
            return json.load(f)
    except:
        return {
            "balance": 1000.0,
            "initial_balance": 1000.0,
            "positions": [],
            "history": []
        }

def save_paper_state(state):
    with open("paper_state.json", "w") as f:
        json.dump(state, f, indent=2)

def process_new_position(asset, side, entry_price, wallet_address, wallet_label):
    state = load_paper_state()
    current_assets = {p["asset"] for p in state["positions"]}
    if asset in current_assets:
        return
    positions_from_wallet = [p for p in state["positions"] if p.get("copied_from", "").startswith(wallet_address[:10])]
    if len(positions_from_wallet) >= 5:
        return
    invest = state["balance"] * 0.05
    if invest < 1:
        return
    price = entry_price if entry_price > 0 else get_current_price(asset)
    new_position = {
        "asset": asset,
        "side": side,
        "entry_price": price,
        "size": invest / price if price > 0 else 0,
        "invested": invest,
        "opened_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "copied_from": wallet_address[:10] + "..." + wallet_address[-6:],
        "wallet_label": wallet_label
    }
    state["balance"] -= invest
    state["positions"].append(new_position)
    save_paper_state(state)
    print(f"[PAPER] Nueva posición copiada: {side} {asset} @ ${price} — Invertido: ${invest:.2f}")

def on_ws_message(ws, message):
    try:
        data = json.loads(message)
        channel = data.get("channel")
        if channel != "webData2":
            return
        msg_data = data.get("data", {})
        user = msg_data.get("user", "").lower()
        wallets = load_wallets()
        wallet_map = {w["address"].lower(): w for w in wallets}
        if user not in wallet_map:
            return
        w = wallet_map[user]
        perf = get_wallet_performance(w["address"])
        if perf.get("win_rate", 0) < 60:
            return
        asset_positions = msg_data.get("clearinghouseState", {}).get("assetPositions", [])
        new_positions = []
        for p in asset_positions:
            pos = p.get("position", {})
            size = float(pos.get("szi", 0))
            if size != 0:
                new_positions.append({
                    "asset": pos.get("coin"),
                    "size": size,
                    "entry_price": float(pos.get("entryPx", 0)),
                    "pnl": float(pos.get("unrealizedPnl", 0)),
                    "side": "LONG" if size > 0 else "SHORT"
                })
        old_positions = wallet_positions.get(w["address"], [])
        old_assets = {p["asset"] for p in old_positions}
        for pos in new_positions:
            if pos["asset"] not in old_assets:
                print(f"[WS] Nueva posición en {w['label']}: {pos['side']} {pos['asset']}")
                process_new_position(pos["asset"], pos["side"], pos["entry_price"], w["address"], w.get("label", ""))
        wallet_positions[w["address"]] = new_positions
    except Exception as e:
        print(f"[WS] Error: {e}")

def on_ws_open(ws):
    print("[WS] Conectado a Hyperliquid WebSocket")
    wallets = load_wallets()
    for w in wallets:
        sub = {"method": "subscribe", "subscription": {"type": "webData2", "user": w["address"]}}
        ws.send(json.dumps(sub))
        print(f"[WS] Suscrito a {w['label']}")

def on_ws_error(ws, error):
    print(f"[WS] Error: {error}")

def on_ws_close(ws, close_status_code, close_msg):
    print("[WS] Conexión cerrada — reconectando en 5s...")
    threading.Timer(5.0, start_websocket).start()

def start_websocket():
    global ws_app
    wallets = load_wallets()
    if not wallets:
        threading.Timer(10.0, start_websocket).start()
        return
    ws_app = websocket.WebSocketApp(
        HL_WS_URL,
        on_open=on_ws_open,
        on_message=on_ws_message,
        on_error=on_ws_error,
        on_close=on_ws_close
    )
    ws_app.run_forever()

def init_websocket():
    global ws_thread
    wallets = load_wallets()
    for w in wallets:
        get_wallet_stats(w["address"])
    ws_thread = threading.Thread(target=start_websocket, daemon=True)
    ws_thread.start()
    print("[WS] WebSocket iniciado en background")

def check_and_copy_trades():
    wallets = load_wallets()
    state = load_paper_state()
    current_assets = {p["asset"] for p in state["positions"]}

    for w in wallets:
        address = w.get("address")
        stats = get_wallet_stats(address)
        perf = get_wallet_performance(address)

        if perf.get("win_rate", 0) < 60:
            continue

        positions_from_wallet = [p for p in state["positions"] if p.get("copied_from", "").startswith(address[:10])]
        if len(positions_from_wallet) >= 5:
            continue

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

def track_all_wallets():
    wallets = load_wallets()
    results = []
    for w in wallets:
        address = w.get("address")
        cached = wallet_positions.get(address)
        if cached is not None:
            stats = {
                "address": address,
                "open_positions": cached,
                "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
        else:
            stats = get_wallet_stats(address)
        perf = get_wallet_performance(address)
        results.append({**w, **stats, **perf})
    return results