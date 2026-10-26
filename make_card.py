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

# ── 디자인 설정 (D 아카이브: 종이 카드 + 금색 책갈피) ─────────────
# 평일은 paper, 주일은 navy. 색을 바꾸려면 여기만 고치면 됩니다.
THEMES = {
    "paper": dict(BG="#E9E1D3", CARD="#FBF8F2", INK="#1F2B45", MUTED="#9A8F7C",
                  REFCOL="#B07F2A", DASH="#D8CDB8", RIBBON="#E3A63F", SHADOW="rgba(31,43,69,.14)"),
    "navy":  dict(BG="#141C30", CARD="#1F2B45", INK="#F6EFE3", MUTED="#8D96AB",
                  REFCOL="#E3A63F", DASH="#3A4766", RIBBON="#E3A63F", SHADOW="rgba(0,0,0,.35)"),
}
SUNDAY_THEME = "navy"        # 주일에도 종이로 두려면 "paper"

HANDLE      = "@bibledaily_zip"
TRANSLATION = "새번역"
LABEL       = "TODAY'S VERSE"   # 왼쪽 위 작은 글씨

# 본문 글꼴은 구글 웹 글꼴(고운바탕), 숫자·영문은 Gelasio. 못 받으면 Noto Serif 로 그립니다.
FONTS_CSS = "https://fonts.googleapis.com/css2?family=Gowun+Batang:wght@400;700&family=Gelasio:wght@400&display=block"

# 피드 카드 (1080x1350). 좌표는 화면 왼쪽 위 기준 px.
FEED = dict(W=1080, H=1350, CARD_X=90, CARD_Y=90, CARD_W=900, CARD_H=1170,
            TEXT_X=170, TEXT_W=740, LABEL_Y=180, DATE_Y=222, DATE_FS=110,
            BOX_TOP=400, BOX_BOTTOM=965, REF_Y=1004, REF_FS=32,
            DASH_Y=1108, FOOT_Y=1138, FOOT_FS=26, FS_MAX=56, FS_MIN=40)

# 스토리 카드 (1080x1920) — 위 320px·아래 300px 는 인스타 UI 에 가리므로 글은 그 사이에만 둡니다
STORY = dict(W=1080, H=1920, CARD_X=90, CARD_Y=230, CARD_W=900, CARD_H=1460,
             TEXT_X=170, TEXT_W=740, LABEL_Y=360, DATE_Y=402, DATE_FS=110,
             BOX_TOP=600, BOX_BOTTOM=1370, REF_Y=1410, REF_FS=34,
             DASH_Y=1520, FOOT_Y=1550, FOOT_FS=27, FS_MAX=62, FS_MIN=44)

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

CARD = """<!doctype html><html><head><meta charset="utf-8">
<link rel="stylesheet" href="{FONTS_CSS}">
<style>
  *{{margin:0;padding:0;box-sizing:border-box}}
  html,body{{width:{W}px;height:{H}px;overflow:hidden}}
  body{{background:{BG};color:{INK};position:relative;-webkit-font-smoothing:antialiased;
       font-family:"Gowun Batang","Noto Serif CJK KR",serif}}
  .card{{position:absolute;left:{CARD_X}px;top:{CARD_Y}px;width:{CARD_W}px;height:{CARD_H}px;
        background:{CARD};border-radius:28px;box-shadow:0 18px 40px {SHADOW}}}
  .ribbon{{position:absolute;left:{RIB_X}px;top:{CARD_Y}px;width:56px;height:150px;background:{RIBBON};
          clip-path:polygon(0 0,100% 0,100% 100%,50% 82%,0 100%)}}
  .latin{{font-family:Gelasio,Georgia,"Noto Serif",serif}}
  .label{{position:absolute;left:{TEXT_X}px;top:{LABEL_Y}px;font-size:30px;letter-spacing:6px;color:{MUTED}}}
  .date{{position:absolute;left:{DATE_X}px;top:{DATE_Y}px;font-size:{DATE_FS}px;line-height:1;color:{INK}}}
  .date small{{font-family:"Gowun Batang","Noto Serif CJK KR",serif;font-size:34px;color:{MUTED};margin-left:22px;letter-spacing:2px}}
  .box{{position:absolute;left:{TEXT_X}px;top:{BOX_TOP}px;width:{TEXT_W}px;height:{BOX_H}px;
       display:flex;flex-direction:column;justify-content:flex-end}}
  #verse{{font-size:{FS}px;font-weight:700;line-height:1.7;max-width:{TEXT_W}px;word-break:keep-all}}
  .ref{{position:absolute;left:{TEXT_X}px;top:{REF_Y}px;font-size:{REF_FS}px;color:{REFCOL}}}
  .dash{{position:absolute;left:{TEXT_X}px;top:{DASH_Y}px;width:{TEXT_W}px;border-top:2px dashed {DASH}}}
  .foot{{position:absolute;left:{TEXT_X}px;top:{FOOT_Y}px;width:{TEXT_W}px;display:flex;justify-content:space-between;
        font-size:{FOOT_FS}px;color:{MUTED}}}
</style></head><body>
  <div class="card"></div><div class="ribbon"></div>
  <div class="label latin">{LABEL}</div>
  <div class="date latin">{D_MD}<small>{D_W}</small></div>
  <div class="box"><div id="verse" data-text="{TEXT}"></div></div>
  <div class="ref">{REF}</div>
  <div class="dash"></div>
  <div class="foot"><span class="latin">{HANDLE}</span><span>{TRANSLATION}</span></div>
</body></html>"""

# 한글 웹 글꼴은 글자 묶음(unicode-range)별로 내려옵니다. 실제로 쓸 글자를 넘겨 받아 둔 뒤
# 줄바꿈 폭을 재야 합니다. 글자 없이 받으면 일부 글자만 고운바탕으로 나와 굵기가 섞입니다.
FONT_JS = r"""
async () => {
  const v = document.getElementById('verse').getAttribute('data-text');
  const rest = document.body.innerText;
  const all = Promise.all([
    document.fonts.load('700 50px "Gowun Batang"', v),
    document.fonts.load('400 32px "Gowun Batang"', rest || '가'),
    document.fonts.load('400 30px Gelasio', rest || 'A'),
  ]);
  await Promise.race([all, new Promise(r => setTimeout(r, 15000))]);
  await document.fonts.ready;
  return document.fonts.check('700 50px "Gowun Batang"', v);
}
"""


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


def card_html(text, ref, dparts, theme, L, fs):
    t = THEMES[theme]
    return CARD.format(
        FONTS_CSS=FONTS_CSS, W=L["W"], H=L["H"], FS=fs,
        CARD_X=L["CARD_X"], CARD_Y=L["CARD_Y"], CARD_W=L["CARD_W"], CARD_H=L["CARD_H"],
        RIB_X=L["CARD_X"] + L["CARD_W"] - 90 - 56,
        TEXT_X=L["TEXT_X"], TEXT_W=L["TEXT_W"], DATE_X=L["TEXT_X"] - 4,
        LABEL_Y=L["LABEL_Y"], DATE_Y=L["DATE_Y"], DATE_FS=L["DATE_FS"],
        BOX_TOP=L["BOX_TOP"], BOX_H=L["BOX_BOTTOM"] - L["BOX_TOP"],
        REF_Y=L["REF_Y"], REF_FS=L["REF_FS"], DASH_Y=L["DASH_Y"],
        FOOT_Y=L["FOOT_Y"], FOOT_FS=L["FOOT_FS"],
        LABEL=LABEL, D_MD=dparts[1], D_W=dparts[2],
        REF=esc(ref), TEXT=esc(text), HANDLE=HANDLE, TRANSLATION=TRANSLATION, **t)


def render(page, path, text, ref, dparts, theme, L):
    """글자 수에 맞춰 크기를 자동으로 줄여가며 한 장을 그립니다."""
    # 1차: 높이도 맞고 끊김도 깨끗한 가장 큰 크기를 찾는다
    # 2차: 그런 크기가 없으면 높이만 맞는 가장 큰 크기로 돌아간다
    # 줄바꿈이 깨끗한 것을 글자 크기보다 우선합니다.
    box_h = L["BOX_BOTTOM"] - L["BOX_TOP"]
    font_ok = None
    for require_clean in (True, False):
        fs = L["FS_MAX"]
        while fs >= L["FS_MIN"]:
            page.set_viewport_size({"width": L["W"], "height": L["H"]})
            page.set_content(card_html(text, ref, dparts, theme, L, fs))
            ok = page.evaluate(FONT_JS)
            font_ok = ok if font_ok is None else (font_ok and ok)
            page.evaluate(WRAP_JS)
            fits = page.evaluate(
                "document.getElementById('verse').scrollHeight") <= box_h
            clean = page.evaluate(
                "+document.getElementById('verse').getAttribute('data-bad')") == 0
            if fits and (clean or not require_clean):
                break
            fs -= 2
        if fs >= L["FS_MIN"]:
            break
    page.screenshot(path=path, type="jpeg", quality=QUALITY)
    if not font_ok:
        print("  ※ 고운바탕 글꼴을 다 받지 못해 일부를 Noto Serif 로 그렸습니다")
    return fs


def main():
    with open("verses.json", encoding="utf-8") as f:
        verses = json.load(f)
    if not verses:
        raise SystemExit("verses.json 이 비어 있습니다.")

    idx  = load_cursor(len(verses))
    item = verses[idx]
    text, ref = item["text"].strip(), item["ref"].strip()

    now   = datetime.now(KST)
    today = now.strftime("%Y-%m-%d")
    # 요일 표기를 바꾸려면 이 줄만 고치면 됩니다.
    #   영문  → now.strftime("%a").upper()  /  없이 → ""
    weekday = "월화수목금토일"[now.weekday()] + "요일"
    dparts = (now.strftime("%Y"), f"{now.month}.{now.day:02d}", weekday)
    theme = SUNDAY_THEME if now.weekday() == 6 else "paper"
    feed_name  = f"{today}.jpg"
    story_name = f"{today}_story.jpg"
    os.makedirs("out", exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": FEED["W"], "height": FEED["H"]}, device_scale_factor=1)
        fs1 = render(page, f"out/{feed_name}", text, ref, dparts, theme, FEED)
        fs2 = render(page, f"out/{story_name}", text, ref, dparts, theme, STORY)
        browser.close()

    with open("out/today.json", "w", encoding="utf-8") as f:
        json.dump({"file": feed_name, "story": story_name, "text": text,
                   "ref": ref, "translation": TRANSLATION, "index": idx},
                  f, ensure_ascii=False, indent=2)

    with open("cursor.txt", "w", encoding="utf-8") as f:
        f.write(str((idx + 1) % len(verses)))

    print(f"피드   : out/{feed_name}   ({ref}, 글자크기 {fs1}px, {theme})")
    print(f"스토리 : out/{story_name}  ({ref}, 글자크기 {fs2}px, {theme})")
    print(f"순번 {idx} → 다음 {(idx + 1) % len(verses)}")


if __name__ == "__main__":
    main()
