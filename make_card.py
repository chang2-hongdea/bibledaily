#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
오늘 나갈 카드를 만듭니다.

verses.json 에서 cursor.txt 가 가리키는 순번의 구절을 꺼내
  out/YYYY-MM-DD.jpg        피드용 (1080x1350)
  out/YYYY-MM-DD_story.jpg  스토리용 (1080x1920)
두 장을 만들고, 발행 스크립트가 읽을 out/today.json 을 남깁니다.
"""

import json, os, re
from datetime import datetime, timezone, timedelta
from playwright.sync_api import sync_playwright

# ── 디자인 설정 ────────────────────────────────
BG          = "#16211D"      # 배경 (딥그린)
FG          = "#ECE5D8"      # 본문
DIM         = "#8FA096"      # 구절 표기
FOOT        = "#6E7F75"      # 하단
HAIR        = "#3E4F47"      # 얇은 선
DATE        = "#7E9387"      # 좌상단 날짜

HANDLE      = "@bibledaily_zip"
TRANSLATION = "새번역"

# 피드 카드
W,  H       = 1080, 1350
FONT_MAX,   FONT_MIN   = 84, 46
BOX_W,      BOX_H      = 888, 840
REF_FS                 = 52   # 출처 표기 (요한복음 15 : 5)
PAD_Y,      FOOT_Y     = 120, 88
DATE_TOP,   DATE_LEFT  = 66, 84
SHIFT_Y                = 44   # 본문 묶음을 아래로 내려 날짜와 거리를 둡니다

# 스토리 카드 — 위아래 320px 는 인스타 UI(프로필·답장창)에 가리므로 비워 둡니다
SW, SH      = 1080, 1920
S_FONT_MAX, S_FONT_MIN = 92, 50
S_BOX_W,    S_BOX_H    = 880, 910
S_REF_FS               = 58
S_PAD_Y,    S_FOOT_Y   = 320, 300
# 스토리는 위 320px 가 인스타 UI 에 가리므로 날짜를 그 아래에 둡니다
S_DATE_TOP, S_DATE_LEFT = 348, 90
S_SHIFT_Y              = 80

QUALITY     = 92             # 인스타 API 는 JPEG 만 허용
# ──────────────────────────────────────────────

KST = timezone(timedelta(hours=9))

# ── 줄바꿈 ────────────────────────────────────
# 어절을 의미 단위로 묶어 줄을 나눕니다. 브라우저에서 실제 글자 폭을 재고,
# 문장 끝 > 쉼표 > 그 밖의 순으로 끊을 자리를 고르며, 관형사("그", "네" 등)
# 뒤나 의존명사("것을", "수가" 등) 앞에서 갈라지지 않도록 벌점을 줍니다.
WRAP_JS = r"""
(function(){
  const el = document.getElementById('verse');
  const raw = el.getAttribute('data-text');
  const cs = getComputedStyle(el);
  // 빈 요소는 폭이 0으로 잡히므로 max-width(없으면 부모 폭)를 기준으로 삼는다
  const maxW = parseFloat(cs.maxWidth) || el.parentElement.clientWidth;
  const words = raw.split(/\s+/).filter(Boolean);
  const n = words.length;
  if (n < 2) { el.textContent = raw; return; }

  // 폭 측정용 숨은 span (본문과 완전히 같은 서체·크기)
  const probe = document.createElement('span');
  probe.style.cssText = 'position:absolute;visibility:hidden;white-space:pre;left:-9999px';
  probe.style.fontFamily    = cs.fontFamily;
  probe.style.fontSize      = cs.fontSize;
  probe.style.fontWeight    = cs.fontWeight;
  probe.style.letterSpacing = cs.letterSpacing;
  document.body.appendChild(probe);
  const wcache = new Map();
  function width(i, j){                      // words[i..j] 를 한 줄로 붙였을 때 폭
    const k = i + ':' + j;
    if (wcache.has(k)) return wcache.get(k);
    probe.textContent = words.slice(i, j+1).join(' ');
    const w = probe.getBoundingClientRect().width;
    wcache.set(k, w); return w;
  }

  // ── 끊어도 되는 자리 / 끊으면 안 되는 자리 ──────────────
  const SENT = /[.!?]["'”’)]?$/;             // 문장이 끝나는 어절
  const COMMA = /[,;:·]["'”’)]?$/;           // 쉼표로 끊기는 어절
  // 뒤 낱말과 반드시 붙어야 하는 관형사·부사 (여기서 끊으면 "너는 네 / 마음을" 사고가 남)
  const DET = /^(그|이|저|네|내|한|두|세|온|참|더|못|안|또|저런|이런|그런|어떤|모든|무슨|어느|한낱|오직|다만|바로|가장|아주|매우|더욱|정말|결코|능히|이미|아직|함께|서로)$/;
  // 홀로 남으면 어색한 의존명사로 시작하는 어절
  const BOUND = /^(것|수|줄|바|때|뿐|채|데|지|만큼|대로|듯|양|터|따름|나위)(이|가|을|를|은|는|에|의|도|으로|로|과|와|야|라|다)?[.,!?]?$/;

  function breakPenalty(j){                  // words[j] 다음에서 줄을 끊을 때의 벌점
    const w = words[j], nx = words[j+1] || '';
    let p = 0;
    if (SENT.test(w))       p -= 9000;       // 문장 끝 — 가장 좋은 자리
    else if (COMMA.test(w)) p -= 4500;       // 쉼표 — 그 다음으로 좋은 자리
    if (DET.test(w))        p += 90000;      // "네" 다음에서 끊기 금지
    if (BOUND.test(nx))     p += 60000;      // 다음 줄이 의존명사로 시작
    if (w.length <= 1 && !SENT.test(w) && !COMMA.test(w)) p += 6000;  // 한 글자 어절 뒤
    return p;
  }

  // ── 동적계획법: 줄 고르기 비용 최소화 ──────────────────
  const INF = Infinity;
  const best = new Array(n+1).fill(INF), from = new Array(n+1).fill(-1);
  best[0] = 0;
  for (let i = 0; i < n; i++){
    if (best[i] === INF) continue;
    for (let j = i; j < n; j++){
      const w = width(i, j);
      if (w > maxW && j > i) break;          // 한 줄에 안 들어감
      const slack = maxW - w;
      const last  = (j === n-1);
      let cost = slack * slack;              // 줄 길이를 고르게
      if (last) cost *= 0.35;                // 마지막 줄은 짧아도 덜 혼냄
      if (last && (j - i) === 0) cost += 60000;   // 끝줄에 한 어절만 남는 것 방지
      if (!last) cost += breakPenalty(j);
      if ((j - i) === 0 && !last) cost += 12000;  // 중간에 한 어절짜리 줄 방지
      const tot = best[i] + cost;
      if (tot < best[j+1]) { best[j+1] = tot; from[j+1] = i; }
    }
  }

  // 되짚어 줄 나누기
  const lines = []; let k = n;
  while (k > 0){ const i = from[k]; lines.unshift(words.slice(i, k).join(' ')); k = i; }
  const probe2 = probe;   // 폭 측정용으로 계속 쓴다 (아래에서 제거)
  el.innerHTML = lines.map(s => s.replace(/&/g,'&amp;').replace(/</g,'&lt;')).join('<br>');
  el.setAttribute('data-lines', lines.length);

  // 보기 나쁜 자리의 개수 — 0 이 아니면 호출부가 한 단계 작은 크기를 시도한다
  let bad = 0;
  for (let i = 0; i < lines.length - 1; i++){
    const tail = lines[i].split(' ').pop();
    const head = lines[i+1].split(' ')[0];
    if (DET.test(tail) || BOUND.test(head)) bad++;      // 붙어야 할 말이 갈라짐
    // 짧은 낱말 하나만 덩그러니 남은 중간 줄 (문장이 끝나는 자리는 괜찮다)
    if (lines[i].split(' ').length === 1 && !/[.,!?]$/.test(lines[i])){
      probe2.textContent = lines[i];
      if (probe2.getBoundingClientRect().width < maxW * 0.45) bad++;
    }
  }
  probe2.remove();
  el.setAttribute('data-bad', bad);
})();
"""

CARD = """<!doctype html><html><head><meta charset="utf-8"><style>
  *{{margin:0;padding:0;box-sizing:border-box}}
  html,body{{width:{W}px;height:{H}px}}
  body{{background:{BG};color:{FG};font-family:"Noto Serif CJK KR",serif;
       -webkit-font-smoothing:antialiased}}
  .wrap{{transform:translateY({SHIFT}px);height:100%;display:flex;flex-direction:column;align-items:center;
        justify-content:center;padding:{PAD_Y}px 96px;text-align:center;position:relative}}
  .ref{{font-family:"Noto Sans CJK KR",sans-serif;font-size:{REF_FS}px;
       letter-spacing:.16em;color:{DIM}}}
  .hair{{background:{HAIR};width:56px;height:1.5px;margin:38px 0 50px}}
  #verse{{font-size:{FS}px;font-weight:500;line-height:1.78;letter-spacing:-.01em;
         max-width:{BOX_W}px;word-break:keep-all}}
  .date{{position:absolute;top:{DATE_TOP}px;left:{DATE_LEFT}px;text-align:left;
        font-family:"Noto Sans CJK KR",sans-serif;color:{DATE};line-height:1.34}}
  .date .y{{font-size:19px;letter-spacing:.42em}}
  .date .d{{font-size:34px;letter-spacing:.02em;font-weight:500;margin-top:2px}}
  .date .w{{font-size:18px;letter-spacing:.14em;opacity:.85}}
  .foot{{position:absolute;bottom:{FOOT_Y}px;left:0;right:0;text-align:center;
        font-family:"Noto Sans CJK KR",sans-serif;font-size:{FOOT_FS}px;
        color:{FOOT};letter-spacing:.04em}}
</style></head><body>
  <div class="date"><div class="y">{D_Y}</div><div class="d">{D_MD}</div><div class="w">{D_W}</div></div>
  <div class="wrap">
    <div class="ref">{REF}</div>
    <div class="hair"></div>
    <div id="verse" data-text="{TEXT}"></div>
    <div class="foot">{HANDLE} &nbsp;·&nbsp; {TRANSLATION}</div>
  </div>
</body></html>"""


def esc(s):
    """본문을 HTML 속성에 안전하게 넣습니다."""
    return (s.replace("&", "&amp;").replace("<", "&lt;")
             .replace(">", "&gt;").replace('"', "&quot;"))


def load_cursor(total):
    try:
        with open("cursor.txt", encoding="utf-8") as f:
            return int(f.read().strip()) % total
    except Exception:
        return 0


def render(page, path, text, ref, dparts, *, w, h, fs_max, fs_min,
           box_w, box_h, pad_y, foot_y, ref_fs, foot_fs, date_top, date_left, shift):
    """글자 수에 맞춰 크기를 자동으로 줄여가며 한 장을 그립니다."""
    # 1차: 높이도 맞고 끊김도 깨끗한 가장 큰 크기를 찾는다
    # 2차: 그런 크기가 없으면 높이만 맞는 가장 큰 크기로 돌아간다
    # 줄바꿈이 깨끗한 것을 글자 크기보다 우선합니다.
    # 1차 탐색은 fs_min 까지 끝까지 내려가며 깨끗한 배치를 찾습니다.
    CLEAN_DROP = 10**6
    for require_clean in (True, False):
        floor = max(fs_min, fs_max - CLEAN_DROP) if require_clean else fs_min
        fs = fs_max
        while fs >= floor:
            page.set_viewport_size({"width": w, "height": h})
            page.set_content(CARD.format(
                W=w, H=h, BG=BG, FG=FG, DIM=DIM, FOOT=FOOT, HAIR=HAIR,
                FS=fs, BOX_W=box_w, PAD_Y=pad_y, FOOT_Y=foot_y,
                REF_FS=ref_fs, FOOT_FS=foot_fs, DATE=DATE,
                DATE_TOP=date_top, DATE_LEFT=date_left, SHIFT=shift,
                D_Y=dparts[0], D_MD=dparts[1], D_W=dparts[2],
                REF=ref, TEXT=esc(text), HANDLE=HANDLE, TRANSLATION=TRANSLATION))
            page.evaluate(WRAP_JS)
            fits = page.evaluate(
                "document.getElementById('verse').scrollHeight") <= box_h
            clean = page.evaluate(
                "+document.getElementById('verse').getAttribute('data-bad')") == 0
            if fits and (clean or not require_clean):
                break
            fs -= 2
        if fs >= floor:
            break
    page.screenshot(path=path, type="jpeg", quality=QUALITY)
    return fs


def main():
    with open("verses.json", encoding="utf-8") as f:
        verses = json.load(f)
    if not verses:
        raise SystemExit("verses.json 이 비어 있습니다.")

    idx  = load_cursor(len(verses))
    item = verses[idx]
    text, ref = item["text"].strip(), item["ref"].strip()
    ref_disp  = re.sub(r"\s*:\s*", " : ", ref)

    now   = datetime.now(KST)
    today = now.strftime("%Y-%m-%d")
    # 요일 표기를 바꾸려면 이 줄만 고치면 됩니다.
    #   영문  → now.strftime("%A")        /  없이 → ""
    weekday = "월화수목금토일"[now.weekday()] + "요일"
    dparts = (now.strftime("%Y"), f"{now.month}.{now.day:02d}", weekday)
    feed_name  = f"{today}.jpg"
    story_name = f"{today}_story.jpg"
    os.makedirs("out", exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": W, "height": H}, device_scale_factor=1)

        fs1 = render(page, f"out/{feed_name}", text, ref_disp, dparts,
                     w=W, h=H, fs_max=FONT_MAX, fs_min=FONT_MIN,
                     box_w=BOX_W, box_h=BOX_H, pad_y=PAD_Y, foot_y=FOOT_Y,
                     ref_fs=REF_FS, foot_fs=23, date_top=DATE_TOP, date_left=DATE_LEFT,
                     shift=SHIFT_Y)

        fs2 = render(page, f"out/{story_name}", text, ref_disp, dparts,
                     w=SW, h=SH, fs_max=S_FONT_MAX, fs_min=S_FONT_MIN,
                     box_w=S_BOX_W, box_h=S_BOX_H, pad_y=S_PAD_Y, foot_y=S_FOOT_Y,
                     ref_fs=S_REF_FS, foot_fs=25, date_top=S_DATE_TOP, date_left=S_DATE_LEFT,
                     shift=S_SHIFT_Y)

        browser.close()

    with open("out/today.json", "w", encoding="utf-8") as f:
        json.dump({"file": feed_name, "story": story_name, "text": text,
                   "ref": ref, "translation": TRANSLATION, "index": idx},
                  f, ensure_ascii=False, indent=2)

    with open("cursor.txt", "w", encoding="utf-8") as f:
        f.write(str((idx + 1) % len(verses)))

    print(f"피드   : out/{feed_name}   ({ref}, 글자크기 {fs1}px)")
    print(f"스토리 : out/{story_name}  ({ref}, 글자크기 {fs2}px)")
    print(f"순번 {idx} → 다음 {(idx + 1) % len(verses)}")


if __name__ == "__main__":
    main()
