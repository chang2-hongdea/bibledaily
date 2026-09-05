#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
주간 요약 릴스를 만듭니다.

지난 한 주에 나간 구절 5개를 이어붙인 9:16 세로 영상을 만들어
  out/reel_YYYY-MM-DD.mp4
로 저장하고, 발행 스크립트가 읽을 out/reel.json 을 남깁니다.

구성: 표지 → 구절 5장 → 마무리   (약 22초)
"""

import json, os, re, subprocess, shutil
from datetime import datetime, timezone, timedelta
from playwright.sync_api import sync_playwright

# ── 설정 ──────────────────────────────────────
BG          = "#16211D"
FG          = "#ECE5D8"
DIM         = "#8FA096"
FOOT        = "#6E7F75"
HAIR        = "#3E4F47"

HANDLE      = "@bibledaily_zip"
TRANSLATION = "새번역"

COUNT       = 5          # 담을 구절 수
W, H        = 1080, 1920 # 릴스는 9:16
FPS         = 30

DUR_COVER   = 2.6        # 표지 길이(초)
DUR_VERSE   = 3.6        # 구절 한 장당
DUR_OUTRO   = 2.6        # 마무리
FADE        = 0.6        # 페이드 인/아웃

FONT_MAX, FONT_MIN = 84, 46
BOX_W,   BOX_H     = 880, 900
PAD_Y,   FOOT_Y    = 320, 300

WORK = "reel_tmp"
# ──────────────────────────────────────────────

KST = timezone(timedelta(hours=9))

PAGE = """<!doctype html><html><head><meta charset="utf-8"><style>
  *{{margin:0;padding:0;box-sizing:border-box}}
  html,body{{width:{W}px;height:{H}px}}
  body{{background:{BG};color:{FG};font-family:"Noto Serif CJK KR",serif;
       -webkit-font-smoothing:antialiased}}
  .wrap{{height:100%;display:flex;flex-direction:column;align-items:center;
        justify-content:center;padding:{PAD_Y}px 100px;text-align:center;position:relative}}
  .ref{{font-family:"Noto Sans CJK KR",sans-serif;font-size:30px;
       letter-spacing:.16em;color:{DIM}}}
  .hair{{background:{HAIR};width:56px;height:1.5px;margin:44px 0 60px}}
  #verse{{font-size:{FS}px;font-weight:500;line-height:1.78;letter-spacing:-.01em;
         max-width:{BOX_W}px;word-break:keep-all}}
  .foot{{position:absolute;bottom:{FOOT_Y}px;left:0;right:0;text-align:center;
        font-family:"Noto Sans CJK KR",sans-serif;font-size:25px;
        color:{FOOT};letter-spacing:.04em}}
</style></head><body>
  <div class="wrap">
    {TOP}
    <div id="verse">{TEXT}</div>
    <div class="foot">{FOOTTEXT}</div>
  </div>
</body></html>"""


def draw(page, path, *, text, top_html, foot_text, fs_max=FONT_MAX):
    fs = fs_max
    while fs >= FONT_MIN:
        page.set_content(PAGE.format(
            W=W, H=H, BG=BG, FG=FG, DIM=DIM, FOOT=FOOT, HAIR=HAIR,
            FS=fs, BOX_W=BOX_W, PAD_Y=PAD_Y, FOOT_Y=FOOT_Y,
            TOP=top_html, TEXT=text, FOOTTEXT=foot_text))
        if page.evaluate("document.getElementById('verse').scrollHeight") <= BOX_H:
            break
        fs -= 2
    page.screenshot(path=path, type="jpeg", quality=94)


def run(cmd):
    subprocess.run(cmd, check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def clip(src, dst, dur):
    """이미지 한 장을 페이드 인/아웃이 붙은 영상 조각으로 만듭니다."""
    vf = (f"scale={W}:{H},"
          f"fade=t=in:st=0:d={FADE},"
          f"fade=t=out:st={dur - FADE:.2f}:d={FADE},"
          f"format=yuv420p")
    run(["ffmpeg", "-y", "-loop", "1", "-framerate", str(FPS),
         "-t", f"{dur}", "-i", src, "-vf", vf,
         "-c:v", "libx264", "-preset", "medium", "-crf", "20",
         "-r", str(FPS), dst])


def main():
    with open("verses.json", encoding="utf-8") as f:
        verses = json.load(f)
    n = len(verses)
    if n < COUNT:
        raise SystemExit(f"구절이 {n}개뿐이라 릴스({COUNT}개)를 만들 수 없습니다.")

    try:
        cursor = int(open("cursor.txt", encoding="utf-8").read().strip()) % n
    except Exception:
        cursor = 0

    # 지난 COUNT개(오래된 것 → 최근 것 순)
    picked = [verses[(cursor - COUNT + i) % n] for i in range(COUNT)]

    today = datetime.now(KST)
    stamp = today.strftime("%Y-%m-%d")
    name  = f"reel_{stamp}.mp4"

    shutil.rmtree(WORK, ignore_errors=True)
    os.makedirs(WORK, exist_ok=True)
    os.makedirs("out", exist_ok=True)

    frames = []   # (이미지 경로, 길이)

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": W, "height": H},
                                device_scale_factor=1)

        # 표지
        cover = f"{WORK}/00_cover.jpg"
        draw(page, cover,
             text="이번 주 말씀",
             top_html=f'<div class="ref">{today.strftime("%Y년 %m월")}</div>'
                      f'<div class="hair"></div>',
             foot_text=HANDLE)
        frames.append((cover, DUR_COVER))

        # 구절
        for i, item in enumerate(picked, 1):
            path = f"{WORK}/{i:02d}_verse.jpg"
            ref  = re.sub(r"\s*:\s*", " : ", item["ref"].strip())
            draw(page, path,
                 text=item["text"].strip(),
                 top_html=f'<div class="ref">{ref}</div><div class="hair"></div>',
                 foot_text=f"{HANDLE} &nbsp;·&nbsp; {TRANSLATION}")
            frames.append((path, DUR_VERSE))

        # 마무리
        outro = f"{WORK}/99_outro.jpg"
        draw(page, outro,
             text="매일 아침 8시,<br>말씀 한 절",
             top_html="",
             foot_text=HANDLE)
        frames.append((outro, DUR_OUTRO))

        browser.close()

    # 조각 영상 만들고 이어붙이기
    parts = []
    for i, (img, dur) in enumerate(frames):
        out = f"{WORK}/clip_{i:02d}.mp4"
        clip(img, out, dur)
        parts.append(out)

    with open(f"{WORK}/list.txt", "w", encoding="utf-8") as f:
        for part in parts:
            f.write(f"file '{os.path.basename(part)}'\n")

    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0",
         "-i", f"{WORK}/list.txt", "-c", "copy", f"{WORK}/joined.mp4"])

    # 인스타는 오디오 트랙이 있는 편이 안전하므로 무음 트랙을 넣습니다.
    run(["ffmpeg", "-y", "-i", f"{WORK}/joined.mp4",
         "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-shortest",
         "-c:v", "copy", "-c:a", "aac", "-b:a", "128k",
         "-movflags", "+faststart", f"out/{name}"])

    shutil.rmtree(WORK, ignore_errors=True)

    total = DUR_COVER + DUR_VERSE * COUNT + DUR_OUTRO
    refs  = [x["ref"] for x in picked]

    with open("out/reel.json", "w", encoding="utf-8") as f:
        json.dump({"file": name, "refs": refs, "seconds": round(total, 1)},
                  f, ensure_ascii=False, indent=2)

    size = os.path.getsize(f"out/{name}") / 1024 / 1024
    print(f"릴스 생성: out/{name}  ({total:.1f}초, {size:.1f}MB)")
    print("담긴 구절: " + ", ".join(refs))


if __name__ == "__main__":
    main()
