#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
오늘 나갈 카드 1장을 만듭니다.

verses.json 에서 cursor.txt 가 가리키는 순번의 구절을 꺼내
out/ 폴더에 1080x1350 JPEG 로 저장하고, 발행 스크립트가 읽을
out/today.json 을 함께 남깁니다.
"""

import json, os, re
from datetime import datetime, timezone, timedelta
from playwright.sync_api import sync_playwright

# ── 디자인 설정 ────────────────────────────────
W, H        = 1080, 1350
BG          = "#16211D"      # 배경 (딥그린)
FG          = "#ECE5D8"      # 본문
DIM         = "#8FA096"      # 구절 표기
FOOT        = "#6E7F75"      # 하단
HAIR        = "#3E4F47"      # 얇은 선

HANDLE      = "@bibledaily_zip"
TRANSLATION = "새번역"

FONT_MAX, FONT_MIN = 76, 42
BOX_W, BOX_H       = 888, 700
QUALITY            = 92      # 인스타 API 는 JPEG 만 허용
# ──────────────────────────────────────────────

KST = timezone(timedelta(hours=9))

CARD = """<!doctype html><html><head><meta charset="utf-8"><style>
  *{{margin:0;padding:0;box-sizing:border-box}}
  html,body{{width:{W}px;height:{H}px}}
  body{{background:{BG};color:{FG};font-family:"Noto Serif CJK KR",serif;
       -webkit-font-smoothing:antialiased}}
  .wrap{{height:100%;display:flex;flex-direction:column;align-items:center;
        justify-content:center;padding:120px 96px;text-align:center;position:relative}}
  .ref{{font-family:"Noto Sans CJK KR",sans-serif;font-size:27px;
       letter-spacing:.16em;color:{DIM}}}
  .hair{{background:{HAIR};width:56px;height:1.5px;margin:44px 0 60px}}
  #verse{{font-size:{FS}px;font-weight:500;line-height:1.78;letter-spacing:-.01em;
         max-width:{BOX_W}px;word-break:keep-all}}
  .foot{{position:absolute;bottom:88px;left:0;right:0;text-align:center;
        font-family:"Noto Sans CJK KR",sans-serif;font-size:23px;
        color:{FOOT};letter-spacing:.04em}}
</style></head><body>
  <div class="wrap">
    <div class="ref">{REF}</div><div class="hair"></div>
    <div id="verse">{TEXT}</div>
    <div class="foot">{HANDLE} &nbsp;·&nbsp; {TRANSLATION}</div>
  </div>
</body></html>"""


def load_cursor(total):
    try:
        with open("cursor.txt", encoding="utf-8") as f:
            return int(f.read().strip()) % total
    except Exception:
        return 0


def main():
    with open("verses.json", encoding="utf-8") as f:
        verses = json.load(f)
    if not verses:
        raise SystemExit("verses.json 이 비어 있습니다.")

    idx  = load_cursor(len(verses))
    item = verses[idx]
    text, ref = item["text"].strip(), item["ref"].strip()
    ref_disp  = re.sub(r"\s*:\s*", " : ", ref)

    today    = datetime.now(KST).strftime("%Y-%m-%d")
    filename = f"{today}.jpg"
    os.makedirs("out", exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": W, "height": H}, device_scale_factor=1)

        # 구절 길이에 맞춰 글자 크기를 자동으로 줄입니다.
        fs = FONT_MAX
        while fs >= FONT_MIN:
            page.set_content(CARD.format(
                W=W, H=H, BG=BG, FG=FG, DIM=DIM, FOOT=FOOT, HAIR=HAIR,
                FS=fs, BOX_W=BOX_W, REF=ref_disp, TEXT=text,
                HANDLE=HANDLE, TRANSLATION=TRANSLATION))
            if page.evaluate("document.getElementById('verse').scrollHeight") <= BOX_H:
                break
            fs -= 2

        page.screenshot(path=f"out/{filename}", type="jpeg", quality=QUALITY)
        browser.close()

    with open("out/today.json", "w", encoding="utf-8") as f:
        json.dump({"file": filename, "text": text, "ref": ref,
                   "translation": TRANSLATION, "index": idx},
                  f, ensure_ascii=False, indent=2)

    # 다음 순번으로 넘겨둡니다.
    with open("cursor.txt", "w", encoding="utf-8") as f:
        f.write(str((idx + 1) % len(verses)))

    print(f"카드 생성: out/{filename}  ({ref}, 글자크기 {fs}px, 순번 {idx})")


if __name__ == "__main__":
    main()
