# TrendPulse GOLD Bot — Free 24/7 Cloud Version

Ye folder GitHub Actions par chalne ke liye ready hai. Matlab: **aapka PC/laptop band ho, internet kat jaye — bot phir bhi chalega** (GitHub ke server par).

**Instrument:** `XAUTUSD` — Tether Gold perpetual (Delta Exchange India). 1 contract = 0.001 XAUT, tick 0.01, fees 0.01% dono side.

| File | Kaam |
|---|---|
| `algo_bot.py` | Main bot (paper mode default) |
| `.github/workflows/bot.yml` | Ghante-ghante chalne ka schedule |
| `requirements.txt` | Python libraries (pandas, requests) |
| `bot_state.json` | Equity + position ka record |
| `.gitignore` | Secret files ko upload hone se rokta hai |

> ⚠️ **`bot_config.txt` kabhi upload mat karna** — usme Telegram token hota hai. Cloud mein token GitHub *Secrets* se aata hai.

---

## Setup (ek baar, ~10 minute)

### 1. GitHub account
[github.com/signup](https://github.com/signup) par free account banao (email + password).

### 2. Naya repository
GitHub par top-right **`+` → New repository**
- Repository name: `gold-bot`
- **Public** chuno (free unlimited Actions minutes)
- **Create repository** dabao

### 3. Files upload karo
Repo page par **"uploading an existing file"** link dabao, phir ye 3 files drag-and-drop karo:
- `algo_bot.py`
- `requirements.txt`
- `bot_state.json`

**Commit changes** dabao.

### 4. `.gitignore` file banao
**Add file → Create new file** → filename: `.gitignore`
Content (ye 2 line kaafi hain):
```
bot_config.txt
__pycache__/
```
**Commit changes** dabao.

### 5. Workflow file banao (sabse zaroori)
**Add file → Create new file** → filename **exactly** ye likho:
```
.github/workflows/bot.yml
```
(jaise hi `/` type karoge, folder ban jayega)

Ab is folder ke andar wali `.github/workflows/bot.yml` file ka **poora content copy** karke paste karo → **Commit changes**.

### 6. Telegram secrets daalo
Repo → **Settings → Secrets and variables → Actions → New repository secret**

| Name | Value |
|---|---|
| `TELEGRAM_BOT_TOKEN` | BotFather wala token |
| `TELEGRAM_CHAT_ID` | `bot_config.txt` mein jo chat id hai |

(Dono naam bilkul same hone chahiye — capital letters.)

### 7. Test run
Repo → **Actions** tab → agar "I understand my workflows, go ahead and enable them" aaye to click karo →
left side **TrendPulse GOLD Bot** → **Run workflow** → **Run workflow**.

10–30 second mein run shuru hoga. Green ✅ matlab sab theek. Run par click karke **Run bot (paper mode)** step ka log dekh sakte ho.

Sab sahi hua to **Telegram par message aayega** (bot start / signal / trade ke waqt).

---

## Roz kya hoga

- Har ghante (minute 5) GitHub khud bot chalayega
- **Din mein ek baar** "update" message (price, equity, position) — isse pata chalega bot zinda hai
- Naya 4H signal aaya to entry + Telegram alert
- Trade khula hai to trailing SL update + exit par alert
- `bot_state.json` aur `bot_trades.csv` repo mein automatically update ho jate hain

> **Note:** Sirf 1 trade na hone par koi message nahi aata — isliye daily heartbeat rakha hai.

**Status dekhna ho:** Actions tab (runs) ya repo mein `bot_trades.csv` kholo.

**Band karna ho:** Actions → TrendPulse GOLD Bot → right side **`...` → Disable workflow**.

### Manual "Run workflow" par kya hota hai
- **Telegram test message** turant ata hai ("Telegram alerts working!")
- **Status message** bhi ata hai (price, equity, FLAT/position)
- 2 message aayenge — dono aa gaye matlab sab sahi hai ✅

---

## 📱 Live Dashboard (phone par trading terminal)

Bot ki **live position, chart, P&L** dekhne ke liye ek free dashboard hai — `docs/index.html`.
Ye GitHub Pages par chalta hai (free), aur data seedha `bot_state.json` + Delta Exchange public API se leta hai.

### Enable karna (ek baar, 5 minute)

1. Repo page par **Add file → Upload files** dabao.
2. Apne computer se **`docs` folder** (jisme `index.html` hai) drag-and-drop karo.
   - Ya: **Add file → Create new file** → filename `docs/index.html` → file ka content paste → **Commit changes**.
3. **Commit changes** dabao.
4. Repo → **Settings → Pages**:
   - **Source**: `Deploy from a branch`
   - **Branch**: `main` · **Folder**: `/docs`
   - **Save** dabao
5. 1–2 minute baad khulega: **https://alpeshukani.github.io/gold-bot/**

### Phone par app jaisa

Chrome mein URL kholo → **3 dots → Add to Home screen**. Ab home screen se ek tap mein terminal khulega.

### Dashboard mein kya dikhta hai

| Hissa | Detail |
|---|---|
| **Chart** | 15m / 1H / 4H candles, ENTRY + SL lines, last price, bot ki entry par marker |
| **Position** | Side, size, entry, mark, SL, unrealised P&L, ROE, R-multiple |
| **Account** | Equity (open P&L ke saath), total return, closed trades, win rate |
| **Bot status** | Last run, next run (IST), heartbeat, last 4H bar |
| **Tabs** | Positions · Trade History · Bot Activity · Performance |

- Har **20 second** mein apne aap refresh hota hai.
- Pehli baar khulte waqt purana data cache se turant dikhta hai, phir fresh update aata hai.
- `PAPER` badge = paper trading. LIVE mode mein bhi badge `LIVE` dikhega — par real order tabhi jate hain jab aap khud keys daalo.

> Dashboard **read-only** hai. Yahan se koi order place/cancel nahi hota.

---

## ❌ Green tick par bhi Telegram par kuch nahi aaya?

Pehle **Actions tab → latest run → "Check secrets" step** kholo:
- `TELEGRAM_BOT_TOKEN: SET` aur `TELEGRAM_CHAT_ID: SET` dikhna chahiye
- `MISSING` dikhe to secret ka naam galat hai ya add nahi hua

Fir **"Telegram test (manual run only)"** step ka log dekho:
- `Test message bheja — Telegram check karo` = Telegram theek hai
- `⚠ telegram error: ... 'Unauthorized'` = token galat (BotFather se dobara copy karo)
- `⚠ telegram error: ... 'chat not found'` = chat id galat (ya aapne bot ko kabhi "hi" nahi bheja)
- `Telegram set nahi hai` = secrets daale hi nahi

Aur ek zaroori baat: **bot ko khud message karna padta hai** — Telegram mein apne bot ko `hi` bhejo, warna bot aapko message nahi bhej sakta.

---

## Zaroori baatein (satik)

1. **Paper mode** hai — koi real order nahi jata. ✅
2. GitHub ka schedule **exact time par nahi chalta** — 5 se 30 minute late ho sakta hai, kabhi ek run skip bhi ho sakta hai. 4H strategy ke liye ye theek hai.
3. **SL check har ghante** hota hai (har second nahi). Isliye backtest se thoda different fill mil sakta hai.
4. **Private repo** chuno to free 2000 minutes/month milte hain — har ghante chalane se limit khatam ho sakti hai. Us case mein `bot.yml` mein cron badal do: `"5 */2 * * *"` (har 2 ghante).
5. **60 din** repo inactive rahe to GitHub schedule band kar deta hai — par ye bot khud state commit karta hai, isliye ye problem nahi aayegi.
6. **Live trading** (real paisa) ke liye: Settings → Secrets mein `DELTA_API_KEY` + `DELTA_API_SECRET` daalo, aur `bot.yml` mein `python algo_bot.py --once` ko `python algo_bot.py --once --live` kar do. ⚠️ Pehle 3–4 hafte paper mein chalao.
7. Ye **guarantee nahi** hai — backtest future nahi hota.

---

## ✅ Bot reliable kaise hai (pichhli galtiyon ka fix)

1. **Trailing SL** ab entry ke baad ke **saare closed bars** ka extreme (min low / max high) use karta hai — pehle sirf last bar dekhta tha, isliye GitHub run late hone par beech ka bada move chhoot jata tha (15 Nov ki raat wahi hua). Ab state mein `best` save hota hai.
2. **Exit fill market price par** hota hai, SL price par nahi. Gap ke waqt "free fill" maan lena jhooth hota — ab nahi hota.
3. **Push retry** — state commit 5 baar tak retry karta hai, ek network hiccup se state nahi khota.
4. `last_run` / `last_price` / `mode` state mein save hote hain, isliye dashboard ko sach dikhta hai.

---

## ⚠️ Ek honest warning — GitHub ka cron reliable nahi hai

Gold bot ke pichhle 46 ghante mein GitHub ne **4 baar** chalaya (schedule hourly likha tha):

```
23:50 UTC → 06:14 UTC (6.4 ghante gap) → 14:40 UTC
```

Public repos par GitHub free scheduler throttle karta hai. 4H strategy ke liye replay nahi hota (gold bot last closed bar dekhta hai), isliye **run ka gap = kamzor SL monitoring**. Do rasta:

### Option A — cron-job.org (free, 10 minute) ✅ recommended

Har ghante bahar se workflow trigger karega:

1. GitHub token: Settings → Developer settings → **Fine-grained tokens** → Generate
   - Repository access: `gold-bot` only
   - Permissions: **Actions → Read and write**
2. [cron-job.org](https://cron-job.org) → free account → **Create cronjob**
   - URL: `https://api.github.com/repos/alpeshukani/gold-bot/actions/workflows/bot.yml/dispatches`
   - Schedule: **Every 1 hour** (minute 5)
   - Method: **POST**
   - Headers: `Authorization: Bearer <token>` · `Accept: application/vnd.github+json`
   - Body: `{"ref":"main"}`
3. Test run → **204** aana chahiye.

### Option B — Oracle Cloud Always Free VM (advanced)

Bot har minute chale, GitHub par depend na kare. Setup commands chahiye to bolo — main step-by-step de dunga. Short version: free VM → Python + git → `python algo_bot.py --loop 60` systemd service → state sync script har 5 min → **GitHub Actions schedule disable**.
