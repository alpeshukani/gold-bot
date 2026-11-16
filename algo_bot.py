"""
=====================================================================
TrendPulse GOLD BOT — XAUTUSD 4H Donchian Breakout + ATR Trail
=====================================================================
STRATEGY (XAUT same-period test 17-Apr-2026 -> 16-Nov-2026, 50 trades:
+20.4%, PF 1.54, MaxDD -12.7%, real Delta fees + 1 tick slippage.
PAXG same window: +17.9%, PF 1.46, MaxDD -12.5% -> XAUT thoda better.
NOTE: XAUT 4H history Delta par sirf ~17-Apr-2026 se hai, isliye test window
chhota hai. Sample 50 trades = indicative, guarantee nahi.)
  - TF 4H | N=20 Donchian | EMA200 filter | ATR(14) x 2 trailing
  - Entry: last CLOSED 4H bar close > 20-bar high (+ close > EMA200) -> LONG
           close < 20-bar low (+ close < EMA200) -> SHORT
  - Exit : trailing stop (lowest low/highest high since entry − 2xATR) / reverse breakout
  - Sizing: notional = 2.5x equity (25% margin x 10x), min 1 contract
  - Symbol: XAUTUSD (Tether Gold perpetual, Delta Exchange India)

MODES:
  python algo_bot.py --once            # ek baar check karo (paper)
  python algo_bot.py --loop 60         # har 60 sec check (paper)
  python algo_bot.py --once --live     # REAL orders (API keys chahiye!)

LIVE MODE KE LIYE env vars set karo:
  DELTA_API_KEY=...  DELTA_API_SECRET=...

⚠ LIVE MODE: pehle kam se kam 4 hafte PAPER mein chalao. Ye code educational
hai; real paisa apne risk par. Bot sirf CLOSED 4H bar par signal leta hai.
=====================================================================
"""

import os
import sys
import json
import time
import hmac
import hashlib
import argparse
from datetime import datetime, timezone, timedelta

import requests
import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = "https://api.india.delta.exchange"
HDRS = {"Accept": "application/json", "User-Agent": "trendpulse-bot/1.0"}

SYMBOL = "XAUTUSD"
TF_MIN = 240                 # 4H
DONCH_N = 20
ATR_K = 2.0
ATR_LEN = 14
EMA_LEN = 200
MARGIN_PCT = 25.0
LEVERAGE = 10
TICK = 0.01
MAKER_FEE = 0.0001
TAKER_FEE = 0.0001
UNIT_VALUE = 0.001           # XAUT per contract (Delta: contract_value 0.001)
FETCH_DAYS = 60

STATE_FILE = "bot_state.json"
TRADES_FILE = "bot_trades.csv"
CONFIG_FILE = "bot_config.txt"


def _load_config(path=CONFIG_FILE):
    cfg = {}
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    k, v = line.split("=", 1)
                    cfg[k.strip()] = v.strip()
        except Exception as e:
            print("config read error:", e)
    return cfg


_CFG = _load_config()
TG_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN") or _CFG.get("TELEGRAM_BOT_TOKEN", "")
TG_CHAT = os.environ.get("TELEGRAM_CHAT_ID") or _CFG.get("TELEGRAM_CHAT_ID", "")


def send_telegram(text):
    """Telegram alert bhejo (agar token set hai). True/False return karta hai."""
    if not TG_TOKEN or not TG_CHAT:
        return False
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
            json={"chat_id": TG_CHAT, "text": text, "parse_mode": "HTML"},
            timeout=15)
        d = r.json()
        if not d.get("ok"):
            print("  ⚠ telegram error:", str(d)[:200])
            return False
        return True
    except Exception as e:
        print("  ⚠ telegram error:", e)
        return False



# ----------------------------- data -----------------------------
def fetch_1m(days=FETCH_DAYS):
    now = int(time.time())
    start = now - days * 86400
    rows = []
    end = now
    while end > start:
        r = requests.get(f"{BASE}/v2/history/candles",
                         params={"resolution": "1m", "symbol": SYMBOL,
                                 "start": start, "end": end},
                         headers=HDRS, timeout=30)
        d = r.json()
        if not d.get("success"):
            raise RuntimeError(f"candles error: {str(d)[:200]}")
        batch = d.get("result", [])
        if not batch:
            break
        rows.extend(batch)
        oldest = min(x["time"] for x in batch)
        if oldest >= end:
            break
        end = oldest - 1
        time.sleep(0.15)
    df = pd.DataFrame(rows).drop_duplicates("time").sort_values("time")
    df["time"] = df["time"].astype("int64")
    return df.reset_index(drop=True)


def resample(df, minutes):
    step = minutes * 60
    g = df.groupby(df["time"] // step)
    agg = g.agg(open=("open", "first"), high=("high", "max"),
                low=("low", "min"), close=("close", "last"),
                volume=("volume", "sum"), open_time=("time", "first"))
    agg = agg.reset_index(drop=True).sort_values("open_time").reset_index(drop=True)
    agg["close_time"] = agg["open_time"] + step - 1
    return agg


def atr_wilder(h, l, c, length=14):
    import numpy as np
    n = len(c)
    tr = np.full(n, float("nan"))
    for i in range(1, n):
        pc = c[i - 1]
        tr[i] = max(h[i] - l[i], abs(h[i] - pc), abs(l[i] - pc))
    return pd.Series(tr).ewm(alpha=1.0 / length, min_periods=length,
                             adjust=False).mean().to_numpy()


def mark_price():
    r = requests.get(f"{BASE}/v2/tickers/{SYMBOL}", headers=HDRS, timeout=15)
    d = r.json()
    if not d.get("success"):
        raise RuntimeError(f"ticker error: {str(d)[:200]}")
    res = d["result"]
    for k in ("mark_price", "spot_price", "close", "last_price"):
        if res.get(k):
            return float(res[k])
    q = res.get("quotes") or {}
    if q.get("best_ask"):
        return (float(q["best_ask"]) + float(q["best_bid"])) / 2
    raise RuntimeError("no price in ticker")


# --------------------------- live trading ---------------------------
def _sign(method, path, query, body):
    key = os.environ.get("DELTA_API_KEY", "")
    secret = os.environ.get("DELTA_API_SECRET", "")
    if not key or not secret:
        raise RuntimeError("LIVE mode: DELTA_API_KEY / DELTA_API_SECRET set karo")
    ts = str(int(time.time()))
    payload = method + ts + path + query + (body or "")
    sig = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return {"api-key": key, "timestamp": ts, "signature": sig,
            "Content-Type": "application/json", "Accept": "application/json"}


def live_market_order(side, size, reduce_only=False):
    """side: 'buy' ya 'sell'. size: contracts."""
    path = "/v2/orders"
    body = json.dumps({"product_symbol": SYMBOL, "size": int(size),
                       "side": side, "order_type": "market_order",
                       "reduce_only": reduce_only})
    hdrs = _sign("POST", path, "", body)
    r = requests.post(BASE + path, data=body, headers=hdrs, timeout=20)
    d = r.json()
    if not d.get("success"):
        raise RuntimeError(f"order failed: {str(d)[:300]}")
    return d["result"]


# ----------------------------- state -----------------------------
def parse_entry_time(s):
    """state mein '2026-11-14 19:52 UTC' -> epoch seconds (na mile to None)."""
    if not s:
        return None
    try:
        txt = str(s).replace("UTC", "").strip()
        dt = datetime.strptime(txt, "%Y-%m-%d %H:%M")
        return int(dt.replace(tzinfo=timezone.utc).timestamp())
    except Exception:
        return None


def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return dict(equity=100.0, pos=None, pending=0, last_bar=None, trades=0)


def save_state(st):
    with open(STATE_FILE, "w") as f:
        json.dump(st, f, indent=2)


def log_trade(rec):
    df = pd.DataFrame([rec])
    hdr = not os.path.exists(TRADES_FILE)
    df.to_csv(TRADES_FILE, mode="a", header=hdr, index=False)


# ----------------------------- core -----------------------------
def compute(df4):
    h = df4["high"].to_numpy(); l = df4["low"].to_numpy()
    c = df4["close"].to_numpy()
    df4["hh"] = df4["high"].rolling(DONCH_N).max().shift(1)
    df4["ll"] = df4["low"].rolling(DONCH_N).min().shift(1)
    df4["ema"] = pd.Series(c).ewm(span=EMA_LEN, adjust=False).mean()
    df4["atr"] = atr_wilder(h, l, c, ATR_LEN)
    return df4


def size_for(equity, price):
    notional = equity * (MARGIN_PCT / 100.0) * LEVERAGE
    qty = int(notional / (price * UNIT_VALUE))
    cap = int((equity * LEVERAGE) / (price * UNIT_VALUE))
    return max(0, min(qty, cap))


def run_once(live=False, notify=False, heartbeat=False):
    st = load_state()
    df1 = fetch_1m()
    df4 = compute(resample(df1, TF_MIN))
    px = mark_price()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    closed = df4.iloc[:-1]            # chalu (incomplete) 4H bar hata do
    last = closed.iloc[-1]
    prev = closed.iloc[-2]
    last_bar_ts = int(last["open_time"])

    print(f"[{now}] {SYMBOL} 4H | price={px} | equity=${st['equity']:.2f} | "
          f"pos={st['pos']['side'] if st['pos'] else 'FLAT'}")
    print(f"  last closed 4H: close={last['close']} hh={last['hh']} ll={last['ll']} "
          f"ema200={last['ema']:.2f} atr={last['atr']:.3f}")

    # ---------------- position management (bar-by-bar replay) ----------------
    if st["pos"]:
        P = st["pos"]
        side = P["side"]
        d = 1 if side == "LONG" else -1
        atr_e = float(P["atr_entry"])
        entry_ts = parse_entry_time(P.get("time"))

        # Pichhle run ke baad close hue SAARE 4H bars replay karo. Isse GitHub
        # run late/miss hone par bhi koi bar, koi SL hit, koi trailing extreme
        # nahi chhootta (15 Nov ki raat yahi galti hui thi).
        if st.get("last_bar"):
            replay = closed[closed["open_time"].astype("int64") > int(st["last_bar"])]
        else:
            replay = closed[closed["open_time"].astype("int64") >= entry_ts] \
                if entry_ts else closed.iloc[0:0]

        exit_info = None
        for _, b in replay.iterrows():
            bts = int(b["open_time"])
            if entry_ts is not None and bts < entry_ts:
                continue                     # entry se pehle ka bar skip
            bh, bl, bc, bo = float(b["high"]), float(b["low"]), float(b["close"]), float(b["open"])

            # 1) SL hit is bar ke andar? (SL woh jo is bar se PEHLE effective tha —
            #    same bar ka extreme trail mein pehle nahi milta, warna look-ahead bias)
            gapped = (d == 1 and bo <= P["sl"]) or (d == -1 and bo >= P["sl"])
            touched = (d == 1 and bl <= P["sl"]) or (d == -1 and bh >= P["sl"])
            if touched:
                exit_info = (bts, (bo if gapped else P["sl"]) - d * TICK, "TRAIL")
                break

            # 2) trail update — is bar ke close par naya SL (agla bar isse check karega)
            if d == 1:
                P["best"] = round(max(float(P.get("best", P["entry_px"])), bh), 3)
                P["sl"] = round(max(P["sl"], P["best"] - ATR_K * atr_e), 3)
            else:
                P["best"] = round(min(float(P.get("best", P["entry_px"])), bl), 3)
                P["sl"] = round(min(P["sl"], P["best"] + ATR_K * atr_e), 3)

            # 3) reverse breakout (bar close Donchian ke ulta)
            if (d == 1 and bc < float(b["ll"])) or (d == -1 and bc > float(b["hh"])):
                exit_info = (bts, bc - d * TICK, "REV")
                break

        # 4) replay ke baad bhi position khuli hai to current price check
        if exit_info is None:
            hit = (d == 1 and px <= P["sl"]) or (d == -1 and px >= P["sl"])
            if hit:
                exit_info = (int(time.time()), px, "TRAIL")

        if exit_info:
            bts, fill, reason = exit_info
            if live:
                fill = px          # real order abhi lagega — purani bar ka fill jhooth hoga
            gross = (fill - P["entry_px"]) * d * P["qty"] * UNIT_VALUE
            fee_out = abs(fill * P["qty"] * UNIT_VALUE) * TAKER_FEE
            pnl = gross - P["entry_fee"] - fee_out
            st["equity"] += pnl
            st["trades"] += 1
            if live:
                live_market_order("sell" if side == "LONG" else "buy",
                                  P["qty"], reduce_only=True)
            ets = datetime.fromtimestamp(bts, timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
            log_trade(dict(time=ets, event="EXIT", side=side,
                           entry_px=P["entry_px"], exit_px=round(fill, 3),
                           qty=P["qty"], reason=reason, pnl=round(pnl, 4),
                           equity_after=round(st["equity"], 2)))
            print(f"  ✅ EXIT {side} @ {fill:.3f} ({reason}) pnl=${pnl:+.2f} "
                  f"| equity ${st['equity']:.2f}")
            send_telegram(
                f"🔔 <b>TrendPulse GOLD — EXIT</b>\n"
                f"Side: {side}\nEntry: {P['entry_px']:.2f}\n"
                f"Exit: {fill:.2f} ({reason})\n"
                f"P&L: <b>${pnl:+.2f}</b>\n"
                f"Equity: ${st['equity']:.2f}")
            st["pos"] = None
        else:
            print(f"  trail SL {P['sl']:.3f} (best {P.get('best'):.3f}, "
                  f"{len(replay)} bar checked)")

    # ---------------- new signal (last closed bar) ----------------
    elif st["last_bar"] != last_bar_ts:
        long_sig = float(last["close"]) > float(last["hh"]) and \
            float(last["close"]) > float(last["ema"])
        short_sig = float(last["close"]) < float(last["ll"]) and \
            float(last["close"]) < float(last["ema"])
        if long_sig or short_sig:
            side = "LONG" if long_sig else "SHORT"
            qty = size_for(st["equity"], px)
            atr_e = float(last["atr"])
            sl = px - ATR_K * atr_e if long_sig else px + ATR_K * atr_e
            if qty >= 1:
                if live:
                    live_market_order("buy" if long_sig else "sell", qty)
                entry_fee = abs(px * qty * UNIT_VALUE) * TAKER_FEE
                st["pos"] = dict(side=side, entry_px=px, qty=qty,
                                 sl=round(sl, 3), atr_entry=atr_e,
                                 best=round(px, 3),
                                 entry_fee=entry_fee, time=now)
                log_trade(dict(time=now, event="ENTRY", side=side,
                               entry_px=round(px, 3), exit_px="", qty=qty,
                               reason="BREAKOUT", pnl="",
                               equity_after=round(st["equity"], 2)))
                print(f"  🚀 ENTRY {side} {qty} contracts @ {px} SL={sl:.3f}")
                send_telegram(
                    f"🚀 <b>TrendPulse GOLD — ENTRY</b>\n"
                    f"Side: {side}\nPrice: {px:.2f}\nQty: {qty} contracts\n"
                    f"SL: {sl:.2f}\nEquity: ${st['equity']:.2f}")
            else:
                print("  signal tha par qty=0 (capital chhota) — skip")
        else:
            print("  koi naya signal nahi")

    st["last_bar"] = last_bar_ts

    save_state(st)
    print(f"  state saved -> {STATE_FILE}")

    # dashboard ke liye live info
    st["last_run"] = now
    st["last_price"] = round(float(px), 3)
    st["mode"] = "LIVE" if live else "PAPER"
    save_state(st)

    # ---------------- status message (heartbeat / manual notify) ----------------
    if notify or heartbeat:
        pos_txt = "FLAT"
        if st["pos"]:
            P = st["pos"]
            pos_txt = f"{P['side']} {P['qty']} @ {P['entry_px']:.2f} (SL {P['sl']:.2f})"
        status = (
            f"📊 <b>TrendPulse GOLD — update</b>\n"
            f"Mode: {'LIVE' if live else 'PAPER'}\n"
            f"Price: {px:.2f}\n"
            f"Equity: <b>${st['equity']:.2f}</b>\n"
            f"Position: {pos_txt}\n"
            f"4H: close {float(last['close']):.2f} | HH {float(last['hh']):.2f} | "
            f"LL {float(last['ll']):.2f}\n"
            f"Trades: {st['trades']}\n"
            f"🕒 {now}")
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if heartbeat and not notify and st.get("last_heartbeat") != today:
            if send_telegram(status):
                st["last_heartbeat"] = today
                save_state(st)
                print("  📨 daily heartbeat bheja")
        if notify:
            print("  📨 status message bheja" if send_telegram(status)
                  else "  ⚠ status message nahi gaya (Telegram settings check karo)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true", help="ek baar chalao")
    ap.add_argument("--loop", type=int, default=0, help="har N sec repeat")
    ap.add_argument("--live", action="store_true", help="REAL orders (risky!)")
    ap.add_argument("--test-telegram", action="store_true",
                    help="Telegram alert test bhejo")
    ap.add_argument("--notify", action="store_true",
                    help="run ke baad status message bhejo")
    ap.add_argument("--heartbeat", action="store_true",
                    help="din mein ek baar status message bhejo (bot zinda hai)")
    a = ap.parse_args()

    if a.test_telegram:
        if not TG_TOKEN or not TG_CHAT:
            print("Telegram set nahi hai. 'bot_config.txt' kholo aur")
            print("TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID bharo.")
            print("(Madad: python telegram_setup.py <TOKEN>)")
            sys.exit(1)
        ok = send_telegram("✅ <b>TrendPulse GOLD bot</b>\nTelegram alerts working!")
        if ok:
            print("✅ Test message bheja — Telegram check karo")
        else:
            print("❌ Message nahi gaya — token ya chat id galat hai.")
            sys.exit(1)
        return

    if a.live and not (os.environ.get("DELTA_API_KEY")
                       and os.environ.get("DELTA_API_SECRET")):
        print("ERROR: --live ke liye DELTA_API_KEY / DELTA_API_SECRET chahiye")
        sys.exit(1)

    mode = "LIVE 🔴" if a.live else "PAPER 📝"
    print(f"=== TrendPulse GOLD BOT | {SYMBOL} 4H | mode={mode} ===")
    if TG_TOKEN and TG_CHAT:
        src = "GitHub secrets / env" if os.environ.get("TELEGRAM_BOT_TOKEN") else CONFIG_FILE
        print(f"Telegram alerts: ON ✅ (source: {src})")
    else:
        print("Telegram alerts: OFF ❌ — token/chat id set nahi hai")
        print("  Local bot: bot_config.txt bharo | Cloud bot: GitHub Secrets daalo")

    if a.loop > 0:
        send_telegram(f"🤖 <b>TrendPulse GOLD bot started</b>\n"
                      f"Mode: {mode}\nEquity: ${load_state()['equity']:.2f}")
        while True:
            try:
                run_once(a.live, heartbeat=True)
            except Exception as e:
                print("ERROR:", e)
            time.sleep(a.loop)
    else:
        run_once(a.live, notify=a.notify, heartbeat=a.heartbeat)


if __name__ == "__main__":
    main()
