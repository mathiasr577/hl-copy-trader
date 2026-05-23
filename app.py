from flask import Flask, jsonify, render_template, request
import json
import os
from tracker import (track_all_wallets, load_wallets, save_wallets,
                     get_wallet_stats, get_wallet_performance,
                     check_and_copy_trades, load_paper_state,
                     save_paper_state, init_websocket)
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/wallets")
def api_wallets():
    data = track_all_wallets()
    return jsonify(data)

@app.route("/api/paper")
def api_paper():
    state = check_and_copy_trades()
    return jsonify(state)

@app.route("/api/paper/close", methods=["POST"])
def close_position():
    body = request.json
    asset = body.get("asset")
    state = load_paper_state()
    new_positions = []
    for pos in state["positions"]:
        if pos["asset"] == asset:
            pnl = pos.get("unrealized_pnl", 0)
            state["balance"] += pos["invested"] + pnl
            state["history"].append({
                **pos,
                "closed_at": __import__("datetime").datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "final_pnl": pnl
            })
        else:
            new_positions.append(pos)
    state["positions"] = new_positions
    save_paper_state(state)
    return jsonify({"success": True, "new_balance": state["balance"]})

@app.route("/api/paper/reset", methods=["POST"])
def reset_paper():
    state = {
        "balance": 1000.0,
        "initial_balance": 1000.0,
        "positions": [],
        "history": []
    }
    save_paper_state(state)
    return jsonify({"success": True})

@app.route("/api/add_wallet", methods=["POST"])
def add_wallet():
    body = request.json
    address = body.get("address")
    label = body.get("label", "")
    if not address:
        return jsonify({"error": "Address requerida"}), 400
    wallets = load_wallets()
    for w in wallets:
        if w["address"] == address:
            return jsonify({"error": "Wallet ya existe"}), 400
    wallets.append({"address": address, "label": label})
    save_wallets(wallets)
    # Suscribir nueva wallet al WebSocket
    from tracker import ws_app
    if ws_app:
        import json as _json
        sub = {"method": "subscribe", "subscription": {"type": "webData2", "user": address}}
        ws_app.send(_json.dumps(sub))
    return jsonify({"success": True})

@app.route("/api/remove_wallet/<address>", methods=["DELETE"])
def remove_wallet(address):
    wallets = load_wallets()
    wallets = [w for w in wallets if w["address"] != address]
    save_wallets(wallets)
    return jsonify({"success": True})

if __name__ == "__main__":
    init_websocket()
    app.run(debug=False, port=5001)