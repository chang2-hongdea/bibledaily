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

HANDLE      = "@bibledaily_zip"
TRANSLATION = "새번역"

# 피드 카드
W,  H       = 1080, 1350
FONT_MAX,   FONT_MIN   = 76, 42
BOX_W,      BOX_H      = 888, 700
PAD_Y,      FOOT_Y     = 120, 88

# 스토리 카드 — 위아래 320px 는 인스타 UI(프로필·답장창)에 가리므로 비워 둡니다
SW, SH      = 1080, 1920
S_FONT_MAX, S_FONT_MIN = 84, 46
S_BOX_W,    S_BOX_H    = 880, 900
S_PAD_Y,    S_FOOT_Y   = 320, 300

QUALITY     = 92             # 인스타 API 는 JPEG 만 허용
# ──────────────────────────────────────────────

KST = timezone(timedelta(hours=9))

CARD = """<!doctype html><html><head><meta charset="utf-8"><style>
  *{{margin:0;padding:0;box-sizing:border-box}}
  html,body{{width:{W}px;height:{H}px}}
  body{{background:{BG};color:{FG};font-family:"Noto Serif CJK KR",serif;
       -webkit-font-smoothing:antialiased}}
  .wrap{{height:100%;display:flex;flex-direction:column;align-items:center;
        justify-content:center;padding:{PAD_Y}px 96px;text-align:center;position:relative}}
  .ref{{font-family:"Noto Sans CJK KR",sans-serif;font-size:{REF_FS}px;
       letter-spacing:.16em;color:{DIM}}}
  .hair{{background:{HAIR};width:56px;height:1.5px;margin:44px 0 60px}}
  #verse{{font-size:{FS}px;font-weight:500;line-height:1.78;letter-spacing:-.01em;
         max-width:{BOX_W}px;word-break:keep-all}}
  .foot{{position:absolute;bottom:{FOOT_Y}px;left:0;right:0;text-align:center;
        font-family:"Noto Sans CJK KR",sans-serif;font-size:{FOOT_FS}px;
        color:{FOOT};letter-spacing:.04em}}
</style></head><body>
  <div class="wrap">
    <div class="ref">{REF}</div>
    <div class="hair"></div>
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


def render(page, path, text, ref, *, w, h, fs_max, fs_min,
           box_w, box_h, pad_y, foot_y, ref_fs, foot_fs):
    """글자 수에 맞춰 크기를 자동으로 줄여가며 한 장을 그립니다."""
    fs = fs_max
    while fs >= fs_min:
        page.set_viewport_size({"width": w, "height": h})
        page.set_content(CARD.format(
            W=w, H=h, BG=BG, FG=FG, DIM=DIM, FOOT=FOOT, HAIR=HAIR,
            FS=fs, BOX_W=box_w, PAD_Y=pad_y, FOOT_Y=foot_y,
            REF_FS=ref_fs, FOOT_FS=foot_fs,
            REF=ref, TEXT=text, HANDLE=HANDLE, TRANSLATION=TRANSLATION))
        if page.evaluate("document.getElementById('verse').scrollHeight") <= box_h:
            break
        fs -= 2
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

    today = datetime.now(KST).strftime("%Y-%m-%d")
    feed_name  = f"{today}.jpg"
    story_name = f"{today}_story.jpg"
    os.makedirs("out", exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": W, "height": H}, device_scale_factor=1)

        fs1 = render(page, f"out/{feed_name}", text, ref_disp,
                     w=W, h=H, fs_max=FONT_MAX, fs_min=FONT_MIN,
                     box_w=BOX_W, box_h=BOX_H, pad_y=PAD_Y, foot_y=FOOT_Y,
                     ref_fs=27, foot_fs=23)

        fs2 = render(page, f"out/{story_name}", text, ref_disp,
                     w=SW, h=SH, fs_max=S_FONT_MAX, fs_min=S_FONT_MIN,
                     box_w=S_BOX_W, box_h=S_BOX_H, pad_y=S_PAD_Y, foot_y=S_FOOT_Y,
                     ref_fs=30, foot_fs=25)

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
