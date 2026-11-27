"""VKOSPI 브리핑·알림. 사용법: python main.py --mode brief|watch|demo"""
import json, os, sys, re, datetime as dt
from io import StringIO

ROOT = os.path.dirname(os.path.abspath(__file__))
KST = dt.timezone(dt.timedelta(hours=9))

def load(name, default):
    p = os.path.join(ROOT, name)
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default

def save(name, obj):
    with open(os.path.join(ROOT, name), "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)

# ---------- 데이터 수집 (실패해도 멈추지 않고 None 반환) ----------
YF = {"kospi": "^KS11", "samsung": "005930.KS", "hynix": "000660.KS",
      "vix": "^VIX", "sox": "^SOX", "us10y": "^TNX", "usdkrw": "KRW=X"}

def fetch_yf():
    out = {}
    try:
        import yfinance as yf
    except Exception:
        return out
    for key, sym in YF.items():
        try:
            h = yf.Ticker(sym).history(period="10d")["Close"].dropna()
            if len(h) >= 2:
                last, prev = float(h.iloc[-1]), float(h.iloc[-2])
                out[key] = {"value": round(last, 2), "chg_pct": round((last / prev - 1) * 100, 2)}
        except Exception:
            pass
    return out

def fetch_vkospi():
    """1) manual.json (직접 입력) 2) Investing.com 페이지 시도. 실패 시 None."""
    m = load("manual.json", {})
    if isinstance(m.get("vkospi"), (int, float)):
        return {"value": float(m["vkospi"]), "chg_pct": float(m.get("vkospi_chg_pct", 0))}
    try:
        import requests
        r = requests.get("https://kr.investing.com/indices/kospi-volatility",
                         headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
        t = r.text
        v = re.search(r'data-test="instrument-price-last"[^>]*>([\d.,]+)<', t)
        c = re.search(r'data-test="instrument-price-change-percent"[^>]*>\(?([+-]?[\d.,]+)', t)
        if v:
            return {"value": float(v.group(1).replace(",", "")),
                    "chg_pct": float(c.group(1).replace(",", "")) if c else 0.0}
    except Exception:
        pass
    return None

def fetch_foreign():
    """네이버 금융 투자자별 매매동향(코스피, 억원). 구조가 바뀌면 None."""
    try:
        import requests, pandas as pd
        r = requests.get("https://finance.naver.com/sise/investorDealTrendDay.naver",
                         headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
        r.encoding = "euc-kr"
        df = pd.read_html(StringIO(r.text))[0].dropna(how="all")
        df.columns = [str(c[-1]) if isinstance(c, tuple) else str(c) for c in df.columns]
        row = df[df.iloc[:, 0].astype(str).str.contains(r"\d")].iloc[0]
        col = [c for c in df.columns if "외국인" in c][0]
        return {"value": int(str(row[col]).replace(",", "")), "date": str(row.iloc[0])}
    except Exception:
        return None

# ---------- 판정 ----------
def stage_of(v, cfg):
    for s in cfg["stages"]:
        if v < s["max"]:
            return s
    return cfg["stages"][-1]

def baseline(hist, cfg):
    vals = sorted(h["vkospi"] for h in hist if h.get("vkospi"))
    n = len(vals)
    if n < cfg["baseline_min_days"]:
        return {"ready": False, "days": n}
    q = lambda p: vals[min(n - 1, int(n * p))]
    return {"ready": True, "days": n, "p50": q(.5), "p75": q(.75), "p90": q(.9)}

def rank_pct(v, hist):
    vals = [h["vkospi"] for h in hist if h.get("vkospi")]
    if not vals:
        return None
    return round(100 * sum(1 for x in vals if x <= v) / len(vals))

def make_alerts(cur, prev_state, cfg):
    a, al = [], cfg["alert"]
    vk = cur.get("vkospi")
    if vk and prev_state.get("vkospi"):
        p, n = prev_state["vkospi"], vk["value"]
        for th in al["vkospi_cross"]:
            if p < th <= n:
                a.append(f"VKOSPI {th} 돌파 ({p:.1f} → {n:.1f})")
            elif n < th <= p:
                a.append(f"VKOSPI {th} 아래로 하락 ({p:.1f} → {n:.1f})")
    if vk and abs(vk["chg_pct"]) >= al["vkospi_daily_pct"]:
        a.append(f"VKOSPI 하루 {vk['chg_pct']:+.1f}% 변동")
    names = {"kospi": "코스피", "samsung": "삼성전자", "hynix": "SK하이닉스",
             "vix": "미국 VIX", "sox": "필라델피아 반도체", "usdkrw": "원/달러"}
    for k, th in al["move_pct"].items():
        d = cur.get(k)
        if d and abs(d["chg_pct"]) >= th:
            a.append(f"{names[k]} {d['chg_pct']:+.1f}%")
    f = cur.get("foreign")
    if f and f["value"] <= al["foreign_net_eok"]:
        a.append(f"외국인 코스피 순매도 {f['value']:,}억원")
    return a

def push(title, msg):
    topic = os.environ.get("NTFY_TOPIC")
    if not topic:
        print("[알림 미전송: NTFY_TOPIC 없음]", title, msg)
        return
    import requests
    requests.post("https://ntfy.sh/", json={"topic": topic, "title": title, "message": msg}, timeout=15)

def brief_text(cur, stg, rk):
    vk = cur.get("vkospi")
    if not vk:
        return "VKOSPI 수치를 가져오지 못했어요."
    day = vk["value"] / 16
    s = f"VKOSPI {vk['value']:.1f} ({vk['chg_pct']:+.1f}%) · {stg['name']} 단계\n하루 예상 폭 약 ±{day:.1f}%"
    if rk is not None:
        s += f" · 최근 기록 중 하위 {rk}% 수준"
    for k, n in [("kospi", "코스피"), ("hynix", "SK하이닉스"), ("samsung", "삼성전자"),
                 ("sox", "필라델피아 반도체"), ("vix", "VIX")]:
        if cur.get(k):
            s += f"\n{n} {cur[k]['value']:,} ({cur[k]['chg_pct']:+.1f}%)"
    return s

def demo():
    return {"vkospi": {"value": 53.18, "chg_pct": -1.39},
            "kospi": {"value": 2480.12, "chg_pct": -1.2}, "samsung": {"value": 61200, "chg_pct": -2.1},
            "hynix": {"value": 1100000, "chg_pct": -7.1}, "vix": {"value": 24.3, "chg_pct": 8.2},
            "sox": {"value": 8408.59, "chg_pct": -10.73}, "us10y": {"value": 4.936, "chg_pct": -2.3},
            "usdkrw": {"value": 1462.5, "chg_pct": 0.4}, "foreign": {"value": -12850, "date": "11.26"}}

def run(mode):
    cfg = load("config.json", {})
    hist = load("history.json", [])
    state = load("state.json", {})
    cur = demo() if mode == "demo" else {**fetch_yf()}
    if mode != "demo":
        vk, fr = fetch_vkospi(), fetch_foreign()
        if vk: cur["vkospi"] = vk
        if fr: cur["foreign"] = fr
    now = dt.datetime.now(KST)
    vk = cur.get("vkospi")
    stg = stage_of(vk["value"], cfg) if vk else cfg["stages"][0]
    today = now.strftime("%Y-%m-%d")
    if vk and not any(h["date"] == today for h in hist):
        hist.append({"date": today, "vkospi": vk["value"]})
    elif vk:
        for h in hist:
            if h["date"] == today: h["vkospi"] = vk["value"]
    hist = hist[-750:]
    base = baseline(hist, cfg)
    rk = rank_pct(vk["value"], hist) if vk and base["ready"] else None
    alerts = make_alerts(cur, state, cfg) if mode != "brief" else []
    data = {"updated": now.strftime("%Y-%m-%d %H:%M"), "items": cur,
            "stage": {"name": stg["name"], "note": stg["note"]},
            "baseline": base, "rank_pct": rk, "stages": cfg["stages"],
            "log": (load("data.json", {}).get("log", []) +
                    [{"t": now.strftime("%m-%d %H:%M"), "m": x} for x in alerts])[-30:]}
    save("data.json", data); save("history.json", hist)
    save("state.json", {"vkospi": vk["value"] if vk else state.get("vkospi")})
    if mode == "brief":
        push("☀️ 아침 브리핑", brief_text(cur, stg, rk))
    for x in alerts:
        push("🔔 시장 알림", x)
    print("완료:", data["updated"], "알림", len(alerts), "건")

if __name__ == "__main__":
    run(sys.argv[sys.argv.index("--mode") + 1] if "--mode" in sys.argv else "watch")
