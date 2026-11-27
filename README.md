# 시장 온도계 (VKOSPI 브리핑 · 알림)

## 설치 순서 (처음 한 번, 약 15분)
1. **GitHub 계정** 만들기 → 설정에서 2단계 인증 켜기
2. 새 저장소(Repository) 만들기 : 이름 예 `thermometer`, **Public**
3. 이 폴더의 파일을 전부 올리기 (`.github` 폴더 포함 — 폴더째 드래그)
4. 저장소 **Settings → Pages** : Source = `Deploy from a branch`, Branch = `main` / `(root)` → Save
   → 몇 분 뒤 `https://내아이디.github.io/thermometer/` 주소가 생겨요
5. 폰에 **ntfy 앱** 설치 → `+` 눌러 **길고 무작위인 이름**(예 `mt-x7k29qpa41zr`)으로 구독
6. 저장소 **Settings → Secrets and variables → Actions → New secret**
   이름 `NTFY_TOPIC`, 값 5번의 이름
7. 저장소 **Actions** 탭 → `update` → **Run workflow** (mode=brief) 로 첫 실행
   → 폰에 알림이 오고, 4번 주소 화면이 실제 값으로 바뀌면 성공
8. 폰 브라우저로 4번 주소를 열고 **홈 화면에 추가** (크롬: 메뉴 → 홈 화면에 추가 / 사파리: 공유 → 홈 화면에 추가)

## 조정
- `config.json` : 단계 경계(30/50/80), 알림 조건(돌파선, 하루 변동폭, 외국인 순매도 한도)
- `manual.json` : VKOSPI 자동 수집이 안 될 때 `{"vkospi": 53.18, "vkospi_chg_pct": -1.39}` 처럼 직접 입력
- 기준선(최근 분포 기반 순위)은 데이터가 60일 쌓이면 화면에 나타나요

## 알아둘 점
- VKOSPI 자동 수집(Investing.com)과 외국인 수급(네이버 금융)은 사이트 구조가 바뀌면 비어 있을 수 있어요. 7번 첫 실행 결과를 보내 주시면 맞춰 드릴게요.
- GitHub 자동 실행은 정각보다 몇 분~수십 분 늦을 수 있어요. 실시간 시세가 아니에요.
- 주소를 아는 사람은 화면을 볼 수 있어요. 개인 정보(보유 종목·금액)는 넣지 마세요.
- 투자 권유가 아닌 참고용 지표예요.
