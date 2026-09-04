# bibledaily — 매일 말씀 카드 자동 발행

매일 한국시간 **오전 8시**에 카드 한 장을 만들어 인스타그램 `@bibledaily_zip` 에 자동으로 올립니다.
컴퓨터를 켜둘 필요가 없고, GitHub Actions 무료 사용량 안에서 돌아갑니다.

---

## 어떻게 돌아가나

```
verses.json (구절 목록)
      ↓  cursor.txt 순번대로 하나 꺼냄
make_card.py     → out/2026-09-05.jpg 생성
      ↓  저장소에 커밋 (이때 이미지가 공개 주소를 갖게 됨)
publish.py       → 인스타그램 API 로 발행
```

인스타 API는 **공개된 이미지 주소**를 요구하는데, 저장소에 커밋된 파일의
`raw.githubusercontent.com` 주소가 그 역할을 합니다. 별도 이미지 호스팅이 필요 없습니다.

---

## 설치 (한 번만)

### 1. 저장소 만들기

GitHub에서 새 저장소를 만들고 이 폴더의 파일을 전부 올립니다.
**저장소는 반드시 Public 이어야 합니다** — 이미지 주소가 공개여야 인스타가 읽어갑니다.

### 2. Actions 쓰기 권한 켜기

저장소 → `Settings` → `Actions` → `General` → 맨 아래 **Workflow permissions**
→ `Read and write permissions` 선택 → Save

이걸 안 하면 카드를 커밋하는 단계에서 실패합니다.

### 3. Secrets 등록

저장소 → `Settings` → `Secrets and variables` → `Actions` → `New repository secret`

| 이름 | 값 |
|---|---|
| `IG_USER_ID` | Instagram user_id |
| `IG_TOKEN` | 60일짜리 장기 액세스 토큰 |

두 값은 Meta 개발자 앱 세팅에서 나옵니다. (별도 세팅 가이드 참고)

### 4. 수동으로 한 번 돌려보기

저장소 → `Actions` 탭 → `매일 말씀 카드 발행` → `Run workflow`

인스타에 글이 올라가면 성공입니다. 이후로는 매일 아침 8시에 알아서 돌아갑니다.

---

## 매달 할 일

### 구절 채워넣기

`verses.json` 에 구절을 순서대로 넣어두면 매일 하나씩 소진됩니다.
목록이 끝나면 처음으로 돌아가므로 **비면 멈추는 게 아니라 반복됩니다.** 미리 채워두세요.

```json
[
  {"text": "주님은 나의 목자시니, 내게 부족함 없어라.", "ref": "시편 23:1"},
  {"text": "...", "ref": "요한복음 3:16"}
]
```

구절 본문은 대한성서공회 사이트(`bskorea.or.kr`)에서 복사해 넣는 것을 권합니다.
오타나 번역 혼선이 카드로 나가면 되돌리기 어렵습니다.

### 토큰 갱신 (중요)

`IG_TOKEN` 은 **60일이면 만료**됩니다. 만료되면 발행이 조용히 멈추므로
한 달에 한 번 갱신하고 Secret 값을 새로 넣어주세요.

```bash
curl -G https://graph.instagram.com/refresh_access_token \
  -d grant_type=ig_refresh_token \
  -d access_token={현재 토큰}
```

---

## 파일 설명

| 파일 | 역할 |
|---|---|
| `.github/workflows/publish.yml` | 매일 오전 8시 실행 스케줄 |
| `make_card.py` | 카드 이미지 생성 (디자인 설정도 이 파일 위쪽에) |
| `publish.py` | 인스타그램 API 발행 |
| `verses.json` | 구절 목록 |
| `cursor.txt` | 다음에 나갈 구절 순번 (자동 관리, 손댈 필요 없음) |
| `out/` | 생성된 카드가 쌓이는 곳 |

색상·글자 크기·해시태그를 바꾸려면 `make_card.py` 와 `publish.py` 위쪽의
설정 구역만 고치면 됩니다.

---

## 문제가 생기면

| 증상 | 원인 |
|---|---|
| 커밋 단계에서 실패 | 2번(Actions 쓰기 권한)을 안 했을 가능성 |
| `이미지가 공개 주소에서 안 보입니다` | 저장소가 Private 이거나 푸시가 안 됨 |
| 발행 단계에서 인증 오류 | 토큰 만료 — 위의 갱신 절차 |
| 아무 일도 안 일어남 | Actions 탭에서 실행 기록 확인. 저장소가 60일간 조용하면 GitHub이 스케줄을 자동 중지합니다 |
