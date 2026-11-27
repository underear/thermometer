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
    import time
    def _f(x):
        return float(str(x).replace(",", "").replace("+", "").strip())
    for url in ["https://polling.finance.naver.com/api/realtime/domestic/index/VKOSPI",
                "https://m.stock.naver.com/api/index/VKOSPI/basic"]:
        host = url.split("/")[2]
        for attempt in range(3):
            try:
                r = requests.get(url, headers=UA, timeout=20)
                if r.status_code != 200:
                    notes.append(f"{host} HTTP {r.status_code}")
                    time.sleep(3 * (attempt + 1))
                    continue
                j = r.json()
                if isinstance(j, dict) and j.get("datas"):
                    j = j["datas"][0]
                v = c = None
                for k in ("closePrice", "nowVal", "now", "currentPrice", "price"):
                    if j.get(k) not in (None, ""):
                        v = j[k]; break
                for k in ("fluctuationsRatio", "changeRate", "fluctuationRate"):
                    if j.get(k) not in (None, ""):
                        c = j[k]; break
                if v is not None:
                    DIAG["vkospi"] = f"{host} 성공"
                    return {"value": _f(v), "chg_pct": _f(c) if c is not None else 0.0}
                notes.append(f"{host} 값 못 찾음(키: {','.join(list(j)[:8]) if isinstance(j, dict) else type(j).__name__})")
                break
            except Exception as e:
                notes.append(f"{host} {type(e).__name__}")
                break
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
        def _n(x):
            return int(str(x).replace(",", "").replace("+", "").strip())
        # 1) 네이버 모바일 JSON (오늘부터 최대 6일 전까지 가장 최근 거래일을 찾음)
        for back in range(0, 7):
            d = dt.datetime.now(KST) - dt.timedelta(days=back)
            if d.weekday() >= 5:
                continue
            ymd = d.strftime("%Y%m%d")
            try:
                r = requests.get("https://m.stock.naver.com/api/index/KOSPI/trend",
                                 params={"bizdate": ymd}, headers=UA, timeout=20)
                if r.status_code != 200:
                    notes.append(f"m.naver trend HTTP {r.status_code}")
                    break
                j = r.json()
                if j.get("foreignValue") not in (None, "") and str(j.get("bizdate")) == ymd:
                    DIAG["foreign"] = f"m.naver trend 성공({ymd})"
                    return {"value": _n(j["foreignValue"]), "date": ymd[4:6] + "." + ymd[6:]}
                if back == 0:
                    notes.append("오늘 자료 아직 없음→이전 거래일 확인")
            except Exception as e:
                notes.append(f"m.naver trend {type(e).__name__}")
                break
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
    try:
        r = requests.post("https://ntfy.sh/", json={"topic": topic, "title": title, "message": msg}, timeout=15)
        print(f"[ntfy 전송] HTTP {r.status_code} / 주제 글자수 {len(topic)}")
    except Exception as e:
        print("[ntfy 전송 실패]", type(e).__name__, e)

def interpret(cur, stg, hist):
    """규칙 기반 해설. 직설적으로, 참고용."""
    vk = cur.get("vkospi") or {}
    stale = bool(vk.get("stale"))
    val = vk.get("value")
    lvl = {"평소": 0, "관찰": 1, "경계": 2, "극단": 3}.get(stg["name"], 0) if val else None
    g = lambda k: (cur.get(k) or {}).get("chg_pct")
    # 방향: VKOSPI(실시간일 때) + VIX
    d = 0
    if val and not stale:
        d += -1 if vk["chg_pct"] <= -3 else (1 if vk["chg_pct"] >= 3 else 0)
    if g("vix") is not None:
        d += -1 if g("vix") <= -5 else (1 if g("vix") >= 5 else 0)
    direction = "꺾임" if d < 0 else ("확대" if d > 0 else "보합")
    # 수급
    fr = (cur.get("foreign") or {}).get("value")
    flow = "중립"
    if fr is not None:
        flow = "매수" if fr >= 3000 else ("매도" if fr <= -3000 else "중립")
    streak = 0
    for h in reversed(hist):
        if h.get("foreign") is None: break
        if (h["foreign"] > 0) == (fr is not None and fr > 0): streak += 1
        else: break
    fx = g("usdkrw")
    fxs = "원화 강세" if (fx is not None and fx <= -0.5) else ("원화 약세" if (fx is not None and fx >= 0.7) else "환율 안정")
    rate = (cur.get("us10y") or {}).get("value")
    kos = g("kospi")

    lines = []
    if val is None:
        lines.append("VKOSPI를 못 가져와서 공포 크기는 판단하지 못했어요.")
    else:
        lines.append(f"공포: VKOSPI {val:.1f} → {stg['name']} 단계" + (" (※옛 기록값이라 방향은 판단 못 함)" if stale else ""))
    lines.append(f"방향: 공포가 {direction}" + (f" (VIX {g('vix'):+.1f}%)" if g("vix") is not None else ""))
    if fr is not None:
        lines.append(f"수급: 외국인 {fr:+,}억원 → {'사는 중' if flow=='매수' else '파는 중' if flow=='매도' else '뚜렷하지 않음'}" + (f" ({streak}일째)" if streak >= 2 else ""))
    lines.append(f"환율: {fxs}" + (f" ({fx:+.1f}%)" if fx is not None else "") + (f" · 미 10년 {rate:.2f}%" + (" (부담)" if rate and rate >= 4.8 else "") if rate else ""))

    hot = lvl is not None and lvl >= 2
    if lvl is None:
        tone, verdict, line = "watch", "판단 보류", "공포 지표가 없어서 결론은 못 내요. 수급·환율만 참고하세요."
    elif hot and direction != "확대" and flow == "매수":
        tone, verdict = "buy", "분할 매수 관심"
        line = "공포가 큰데 꺾이는 쪽이고 외국인이 사고 있어요. 관심 구간이에요. 한 번에 말고 나눠서 보세요." + (" 다만 하루 신호라 내일도 이어지는지 확인하세요." if streak < 2 else " 수급이 이어지는 중이라 신호가 더 믿을 만해요.")
        if stale: line = "공포는 큰 구간이고 외국인이 사고 있어요. 방향은 확인이 안 돼요. 관심 구간 후보예요."
    elif hot and (direction == "확대" or flow == "매도"):
        tone, verdict = "wait", "아직 아니에요"
        why = "공포가 더 커지는 중" if direction == "확대" else "외국인이 팔고 있어요"
        line = f"{why}. 떨어지는 칼날이에요. 공포가 꺾이고 외국인이 돌아설 때까지 기다리는 쪽이 유리해요."
    elif hot:
        tone, verdict = "watch", "관망"
        line = "공포는 크지만 방향도 수급도 아직 애매해요. 신호가 하나 더 나올 때까지 보세요."
    elif lvl == 1 and direction == "꺾임" and flow != "매도":
        tone, verdict = "buy", "회복 초기"
        line = "공포가 가라앉는 중이에요. 급하게 사기보다 흐름이 이어지는지 보세요."
    elif lvl == 1 and (direction == "확대" or flow == "매도"):
        tone, verdict = "wait", "대기"
        line = "공포 단계가 올라갈 수 있어요. 지금은 사지 말고 지켜보세요."
    elif lvl == 0 and kos is not None and kos >= 3:
        tone, verdict = "wait", "과열 주의"
        line = "시장이 평온한데 지수가 크게 올랐어요. 공포가 없을 때 추격 매수는 위험해요."
    elif lvl == 0:
        tone, verdict = "calm", "평온"
        line = "공포가 없는 구간이에요. 싸게 살 타이밍이라고 볼 근거는 없어요. 원래 계획대로 하세요."
    else:
        tone, verdict = "watch", "관망"
        line = "뚜렷한 신호가 없어요. 지켜보세요."
    if rate and rate >= 4.8 and tone == "buy":
        line += " 미 금리가 높아서 부담은 남아 있어요."
    return {"verdict": verdict, "tone": tone, "summary": line, "lines": lines}

def brief_text(cur, stg, rk, rd=None):
    vk = cur.get("vkospi")
    if vk:
        s = f"VKOSPI {vk['value']:.1f} ({vk['chg_pct']:+.1f}%) · {stg['name']} 단계" + (f" [※{vk['stale']} 기록값]" if vk.get("stale") else "") + f"\n하루 예상 폭 약 ±{vk['value'] / 16:.1f}%"
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
    if rd:
        s = f"【{rd['verdict']}】{rd['summary']}\n\n" + s
    return s

def demo():
    return {"vkospi": {"value": 53.18, "chg_pct": -1.39},
            "kospi": {"value": 2480.12, "chg_pct": -1.2}, "samsung": {"value": 61200, "chg_pct": -2.1},
            "hynix": {"value": 1100000, "chg_pct": -7.1}, "vix": {"value": 24.3, "chg_pct": 8.2},
            "sox": {"value": 8408.59, "chg_pct": -10.73}, "us10y": {"value": 4.936, "chg_pct": -2.3},
            "usdkrw": {"value": 1462.5, "chg_pct": 0.4}, "foreign": {"value": -12850, "date": "11.26"}}

def run(mode):
    if mode == "test":
        push("✅ 시험 알림", "시장 온도계 알림이 정상 연결됐어요.")
        print("시험 알림 전송 시도 완료 (데이터는 건드리지 않아요)")
        return
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
    if not vk and mode != "demo":
        last = [h for h in hist if h.get("vkospi")]
        if last:
            vk = {"value": last[-1]["vkospi"], "chg_pct": 0.0, "stale": last[-1]["date"]}
            cur["vkospi"] = vk
            DIAG["vkospi"] = (DIAG.get("vkospi", "") + f" → 마지막 기록({last[-1]['date']}) 값 표시").strip()
    stg = stage_of(vk["value"], cfg) if vk else cfg["stages"][0]
    today = now.strftime("%Y-%m-%d")
    fr_now = (cur.get("foreign") or {}).get("value")
    if fr_now is not None and mode != "demo":
        rec = next((h for h in hist if h["date"] == today), None)
        if rec is None:
            rec = {"date": today, "vkospi": None}; hist.append(rec)
        rec["foreign"] = fr_now
    if vk and vk.get("stale"):
        pass
    elif vk and not any(h["date"] == today for h in hist):
        hist.append({"date": today, "vkospi": vk["value"]})
    elif vk and not vk.get("stale"):
        for h in hist:
            if h["date"] == today: h["vkospi"] = vk["value"]
    hist = hist[-750:]
    base = baseline(hist, cfg)
    rk = rank_pct(vk["value"], hist) if vk and base["ready"] else None
    rd = interpret(cur, stg, hist if mode != "demo" else [])
    alerts = make_alerts(cur, state, cfg) if mode != "brief" else []
    if mode == "watch" and state.get("verdict") and state["verdict"] != rd["verdict"]:
        alerts.append(f"해설 변경: {state['verdict']} → {rd['verdict']}\n{rd['summary']}")
    data = {"updated": now.strftime("%Y-%m-%d %H:%M"), "items": cur,
            "stage": {"name": stg["name"], "note": stg["note"]},
            "read": rd, "baseline": base, "rank_pct": rk, "diag": DIAG, "stages": cfg["stages"],
            "log": (load("data.json", {}).get("log", []) +
                    [{"t": now.strftime("%m-%d %H:%M"), "m": x} for x in alerts])[-30:]}
    save("data.json", data); save("history.json", hist)
    save("state.json", {"vkospi": vk["value"] if vk else state.get("vkospi"), "verdict": rd["verdict"]})
    if mode == "brief":
        push("☀️ 아침 브리핑", brief_text(cur, stg, rk, rd))
    for x in alerts:
        push("🔔 시장 알림", x)
    print("완료:", data["updated"], "알림", len(alerts), "건")

if __name__ == "__main__":
    run(sys.argv[sys.argv.index("--mode") + 1] if "--mode" in sys.argv else "watch")
