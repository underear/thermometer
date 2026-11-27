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

DIAG = {}
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36",
      "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8"}

def fetch_vkospi():
    """1) manual.json 2) Investing.com 여러 주소 시도. 실패 이유는 DIAG에 기록."""
    m = load("manual.json", {})
    if isinstance(m.get("vkospi"), (int, float)):
        DIAG["vkospi"] = "수동 입력값 사용"
        return {"value": float(m["vkospi"]), "chg_pct": float(m.get("vkospi_chg_pct", 0))}
    try:
        import requests
    except Exception as e:
        DIAG["vkospi"] = f"requests 없음: {e}"
        return None
    notes = []
    for url in ["https://m.stock.naver.com/api/index/VKOSPI/basic",
                "https://polling.finance.naver.com/api/realtime/domestic/index/VKOSPI"]:
        host = url.split("/")[2] + url.split("/")[-2][:0]
        try:
            r = requests.get(url, headers=UA, timeout=20)
            if r.status_code != 200:
                notes.append(f"{host} HTTP {r.status_code}")
                continue
            j = r.json()
            if isinstance(j, dict) and "datas" in j and j["datas"]:
                j = j["datas"][0]
            v = j.get("closePrice") or j.get("nowVal") or j.get("now")
            c = j.get("fluctuationsRatio") or j.get("changeRate") or 0
            if v:
                DIAG["vkospi"] = f"{host} 성공"
                return {"value": float(str(v).replace(",", "")), "chg_pct": float(str(c).replace(",", ""))}
            notes.append(f"{host} 값 못 찾음")
        except Exception as e:
            notes.append(f"{host} {type(e).__name__}")
    for url in ["https://kr.investing.com/indices/kospi-volatility",
                "https://www.investing.com/indices/kospi-volatility",
                "https://m.investing.com/indices/kospi-volatility"]:
        host = url.split("/")[2]
        try:
            r = requests.get(url, headers=UA, timeout=20)
            if r.status_code != 200:
                notes.append(f"{host} HTTP {r.status_code}")
                continue
            t = r.text
            v = (re.search(r'data-test="instrument-price-last"[^>]*>\s*([\d.,]+)\s*<', t)
                 or re.search(r'"last"\s*:\s*"?([\d.,]+)"?', t))
            c = re.search(r'data-test="instrument-price-change-percent"[^>]*>\s*\(?([+-]?[\d.,]+)', t)
            if v:
                DIAG["vkospi"] = f"{host} 성공"
                return {"value": float(v.group(1).replace(",", "")),
                        "chg_pct": float(c.group(1).replace(",", "")) if c else 0.0}
            notes.append(f"{host} 값 못 찾음")
        except Exception as e:
            notes.append(f"{host} {type(e).__name__}")
    DIAG["vkospi"] = " / ".join(notes)
    return None

def fetch_foreign():
    """네이버 금융 투자자별 매매동향(코스피, 억원). 3번째 칸이 외국인. 수동값(manual.json)도 허용."""
    m = load("manual.json", {})
    if isinstance(m.get("foreign"), (int, float)):
        DIAG["foreign"] = "수동 입력값 사용"
        return {"value": int(m["foreign"]), "date": "수동"}
    notes = []
    try:
        import requests, lxml.html
        today = dt.datetime.now(KST).strftime("%Y%m%d")
        for path in ["investorDealTrendDay.nhn", "investorDealTrendDay.naver"]:
            for host in ["finance.naver.com"]:
                try:
                    r = requests.get(f"https://{host}/sise/{path}",
                                     params={"bizdate": today, "sosok": "01"}, headers=UA, timeout=20)
                    if r.status_code != 200:
                        notes.append(f"{path} HTTP {r.status_code}")
                        continue
                    doc = lxml.html.fromstring(r.content.decode("euc-kr", "ignore"))
                    for tr in doc.xpath('//table[contains(@class,"type_1")]//tr'):
                        td = [x.text_content().strip() for x in tr.xpath("./td")]
                        if len(td) >= 3 and re.match(r"\d{2}\.\d{2}\.\d{2}", td[0]):
                            DIAG["foreign"] = f"{path} 성공"
                            return {"value": int(td[2].replace(",", "").replace("+", "")), "date": td[0]}
                    notes.append(f"{path} 표를 못 찾음")
                except Exception as e:
                    notes.append(f"{path} {type(e).__name__}")
    except Exception as e:
        notes.append(f"{type(e).__name__}")
    DIAG["foreign"] = " / ".join(notes)
    return None

def fetch_rv20():
    """참고용: 코스피 20일 실현변동성(연율, %). VKOSPI와 다른 값이에요."""
    try:
        import yfinance as yf
        h = yf.Ticker("^KS11").history(period="3mo")["Close"].dropna()
        r = h.pct_change().dropna().tail(20)
        if len(r) >= 15:
            return {"value": round(float(r.std() * (252 ** 0.5) * 100), 1), "chg_pct": None}
    except Exception:
        pass
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
    if vk:
        s = f"VKOSPI {vk['value']:.1f} ({vk['chg_pct']:+.1f}%) · {stg['name']} 단계\n하루 예상 폭 약 ±{vk['value'] / 16:.1f}%"
        if rk is not None:
            s += f" · 최근 기록 중 하위 {rk}% 수준"
    else:
        s = "VKOSPI 수치를 가져오지 못했어요."
    for k, n in [("kospi", "코스피"), ("hynix", "SK하이닉스"), ("samsung", "삼성전자"),
                 ("sox", "필라델피아 반도체"), ("vix", "VIX")]:
        if cur.get(k):
            s += f"\n{n} {cur[k]['value']:,} ({cur[k]['chg_pct']:+.1f}%)"
    if cur.get("foreign"):
        s += f"\n외국인 코스피 {cur['foreign']['value']:,}억원"
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
        vk, fr, rv = fetch_vkospi(), fetch_foreign(), fetch_rv20()
        if vk: cur["vkospi"] = vk
        if fr: cur["foreign"] = fr
        if rv: cur["rv20"] = rv
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
            "baseline": base, "rank_pct": rk, "diag": DIAG, "stages": cfg["stages"],
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
