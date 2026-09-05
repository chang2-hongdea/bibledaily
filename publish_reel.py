#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
주간 요약 릴스를 인스타그램에 발행합니다.

영상은 사진과 달리 인스타가 내려받아 인코딩하는 시간이 걸리므로,
컨테이너를 만든 뒤 준비가 끝날 때까지 기다렸다가 발행합니다.

필요한 환경변수 (GitHub Secrets)
  IG_USER_ID, IG_TOKEN
"""

import json, os, sys, time
import urllib.parse, urllib.request, urllib.error

GRAPH  = "https://graph.instagram.com/v23.0"
BRANCH = os.environ.get("GITHUB_REF_NAME", "main")

HASHTAGS = "#말씀 #오늘의말씀 #성경말씀 #큐티 #묵상 #성경구절 #매일말씀 #릴스"

POLL_TRIES, POLL_GAP = 20, 15      # 최대 5분 대기


def api_post(url, data):
    body = urllib.parse.urlencode(data).encode()
    req  = urllib.request.Request(url, data=body, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        raise SystemExit(f"인스타 API 오류 {e.code}: {e.read().decode()[:600]}")


def api_get(url):
    try:
        with urllib.request.urlopen(url, timeout=40) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        raise SystemExit(f"인스타 API 오류 {e.code}: {e.read().decode()[:600]}")


def reachable(url, tries=8, gap=15):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, method="HEAD")
            with urllib.request.urlopen(req, timeout=20) as r:
                if r.status == 200:
                    print(f"  영상 확인됨 ({r.headers.get('Content-Type')})")
                    return True
        except Exception:
            pass
        print(f"  영상 대기 중… ({i+1}/{tries})")
        time.sleep(gap)
    return False


def main():
    user_id = os.environ.get("IG_USER_ID")
    token   = os.environ.get("IG_TOKEN")
    repo    = os.environ.get("GITHUB_REPOSITORY")
    for name, val in [("IG_USER_ID", user_id), ("IG_TOKEN", token),
                      ("GITHUB_REPOSITORY", repo)]:
        if not val:
            sys.exit(f"환경변수 {name} 가 없습니다.")

    with open("out/reel.json", encoding="utf-8") as f:
        reel = json.load(f)

    owner, name = repo.split("/", 1)
    # GitHub Pages 는 mp4 를 올바른 형식으로 내보내므로 이쪽을 우선 사용합니다.
    pages_url = f"https://{owner}.github.io/{name}/out/{reel['file']}"
    raw_url   = f"https://raw.githubusercontent.com/{repo}/{BRANCH}/out/{reel['file']}"

    print(f"Pages 주소 확인: {pages_url}")
    if reachable(pages_url):
        video_url = pages_url
    else:
        print("Pages 주소를 못 읽어 raw 주소로 시도합니다.")
        if not reachable(raw_url, tries=4, gap=10):
            sys.exit("영상이 공개 주소에서 안 보입니다. 잠시 후 다시 실행하세요.")
        video_url = raw_url

    caption = ("이번 주 말씀\n\n"
               + "\n".join(f"· {r}" for r in reel["refs"])
               + f"\n\n{HASHTAGS}")

    print("컨테이너 생성 중…")
    container = api_post(f"{GRAPH}/{user_id}/media", {
        "media_type": "REELS",
        "video_url": video_url,
        "caption": caption,
        "access_token": token,
    })
    cid = container["id"]
    print(f"  컨테이너: {cid}")

    # 인스타가 영상 처리를 끝낼 때까지 기다립니다.
    for i in range(POLL_TRIES):
        st = api_get(f"{GRAPH}/{cid}?fields=status_code&access_token={token}")
        code = st.get("status_code")
        print(f"  처리 상태: {code} ({i+1}/{POLL_TRIES})")
        if code == "FINISHED":
            break
        if code == "ERROR":
            sys.exit(f"인스타가 영상 처리에 실패했습니다: {st}")
        time.sleep(POLL_GAP)
    else:
        sys.exit("영상 처리가 제한 시간 안에 끝나지 않았습니다.")

    result = api_post(f"{GRAPH}/{user_id}/media_publish", {
        "creation_id": cid, "access_token": token})
    print(f"릴스 발행 완료: {result}")


if __name__ == "__main__":
    main()
