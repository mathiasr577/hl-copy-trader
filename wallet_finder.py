import requests
import json
import time

HL_API_URL = "https://api.hyperliquid.xyz/info"
DEXLY_API = "https://api.dexly.trade/hyperliquid/leaderboard"

def get_leaderboard_dexly():
    """Obtiene el leaderboard via Dexly API"""
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        params = {
            "window": "allTime",
            "sort": "roi",
            "order": "desc",
            "limit": 200,
            "offset": 0
        }
        r = requests.get(DEXLY_API, params=params, headers=headers, timeout=15)
        data = r.json()
        if isinstance(data, list):
            return data
        return data.get("data", data.get("traders", data.get("rows", [])))
    except Exception as e:
        print(f"Error Dexly: {e}")
        return []

def get_leaderboard_hl():
    """Obtiene leaderboard directo de Hyperliquid"""
    try:
        url = "https://stats-data.hyperliquid.xyz/Mainnet/leaderboard"
        headers = {"User-Agent": "Mozilla/5.0"}
        r = requests.get(url, headers=headers, timeout=15)
        data = r.json()
        return data
    except Exception as e:
        print(f"Error HL stats: {e}")
        return []

def get_wallet_performance(address):
    try:
        payload = {"type": "userFills", "user": address}
        r = requests.post(HL_API_URL, json=payload, timeout=10)
        fills = r.json()
        if not isinstance(fills, list):
            return None
        wins = 0
        total = 0
        for fill in fills:
            closed_pnl = float(fill.get("closedPnl", 0))
            if closed_pnl != 0:
                total += 1
                if closed_pnl > 0:
                    wins += 1
        if total < 100:
            return None
        win_rate = (wins / total * 100) if total > 0 else 0
        return {"win_rate": round(win_rate, 2), "total_trades": total}
    except:
        return None

def get_wallet_value(address):
    try:
        payload = {"type": "clearinghouseState", "user": address}
        r = requests.post(HL_API_URL, json=payload, timeout=10)
        data = r.json()
        margin = data.get("marginSummary", {})
        account_value = float(margin.get("accountValue", 0))
        positions = data.get("assetPositions", [])
        active_positions = sum(1 for p in positions if float(p.get("position", {}).get("szi", 0)) != 0)
        return {"account_value": account_value, "active_positions": active_positions}
    except:
        return None

def extract_address(trader):
    """Extrae la dirección de cualquier formato de trader"""
    if isinstance(trader, dict):
        for key in ["ethAddress", "address", "user", "trader", "wallet"]:
            val = trader.get(key)
            if val and isinstance(val, str) and val.startswith("0x") and len(val) > 10:
                return val
    elif isinstance(trader, str) and trader.startswith("0x"):
        return trader
    return None

def find_best_wallets():
    print("🔍 Buscando las mejores wallets en Hyperliquid...")
    print("=" * 60)

    # Intentar múltiples fuentes
    traders = []
    
    print("📡 Intentando Hyperliquid stats API...")
    data = get_leaderboard_hl()
    if data:
        if isinstance(data, list):
            traders = data
        elif isinstance(data, dict):
            for key in ["leaderboardRows", "rows", "data", "traders"]:
                if key in data:
                    traders = data[key]
                    break
        print(f"✅ Obtenidos {len(traders)} traders de HL stats")

    if not traders:
        print("📡 Intentando Dexly API...")
        traders = get_leaderboard_dexly()
        print(f"✅ Obtenidos {len(traders)} traders de Dexly")

    if not traders:
        print("❌ No se pudo obtener el leaderboard de ninguna fuente")
        return []

    print(f"📊 Analizando top 200 traders...")
    print()

    good_wallets = []
    analyzed = 0
    checked = 0

    for trader in traders[:200]:
        checked += 1
        address = extract_address(trader)
        if not address:
            continue

        try:
            wallet_info = get_wallet_value(address)
            if not wallet_info:
                continue

            account_value = wallet_info["account_value"]
            active_positions = wallet_info["active_positions"]

            if account_value < 500000:
                continue
            if active_positions == 0:
                continue

            perf = get_wallet_performance(address)
            if not perf:
                continue

            win_rate = perf["win_rate"]
            total_trades = perf["total_trades"]

            if win_rate < 60:
                continue
            if total_trades < 100:
                continue

            good_wallets.append({
                "address": address,
                "account_value": account_value,
                "active_positions": active_positions,
                "win_rate": win_rate,
                "total_trades": total_trades
            })

            analyzed += 1
            print(f"✅ #{analyzed} {address[:10]}...{address[-6:]}")
            print(f"   💰 ${account_value:,.0f} | WR: {win_rate}% | Trades: {total_trades} | Pos: {active_positions}")
            print()

            time.sleep(0.3)

        except Exception as e:
            continue

    print("=" * 60)
    print(f"🎯 {len(good_wallets)} wallets buenas de {checked} analizadas")
    print()

    good_wallets.sort(key=lambda x: x["win_rate"], reverse=True)

    print("🏆 TOP WALLETS:")
    print()
    for i, w in enumerate(good_wallets[:10], 1):
        print(f"{i}. {w['address']}")
        print(f"   WR: {w['win_rate']}% | Trades: {w['total_trades']} | Cuenta: ${w['account_value']:,.0f}")
        print()

    with open("best_wallets.json", "w") as f:
        json.dump(good_wallets, f, indent=2)
    print("💾 Guardado en best_wallets.json")

    return good_wallets

if __name__ == "__main__":
    find_best_wallets()