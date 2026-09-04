#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
오늘 만든 카드를 인스타그램에 발행합니다.

필요한 환경변수 (GitHub Secrets 로 등록)
  IG_USER_ID  : Instagram user_id
  IG_TOKEN    : 장기 액세스 토큰 (60일)
  GITHUB_REPOSITORY : Actions 가 자동으로 넣어줍니다 (owner/repo)
"""

import json, os, sys, time
import urllib.parse, urllib.request

GRAPH   = "https://graph.instagram.com/v23.0"
BRANCH  = os.environ.get("GITHUB_REF_NAME", "main")

HASHTAGS = "#말씀 #오늘의말씀 #성경말씀 #큐티 #묵상 #성경구절 #매일말씀"


def post(url, data):
    body = urllib.parse.urlencode(data).encode()
    req  = urllib.request.Request(url, data=body, method="POST")
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode())


def wait_until_public(url, tries=10, gap=15):
    """푸시 직후 이미지가 아직 안 보일 수 있어 잠시 기다립니다."""
    for i in range(tries):
        try:
            req = urllib.request.Request(url, method="HEAD")
            with urllib.request.urlopen(req, timeout=20) as r:
                if r.status == 200:
                    return True
        except Exception:
            pass
        print(f"  이미지 대기 중… ({i+1}/{tries})")
        time.sleep(gap)
    return False


def main():
    user_id = os.environ.get("IG_USER_ID")
    token   = os.environ.get("IG_TOKEN")
    repo    = os.environ.get("GITHUB_REPOSITORY")

    for name, val in [("IG_USER_ID", user_id), ("IG_TOKEN", token),
                      ("GITHUB_REPOSITORY", repo)]:
        if not val:
            sys.exit(f"환경변수 {name} 가 없습니다. GitHub Secrets 를 확인하세요.")

    with open("out/today.json", encoding="utf-8") as f:
        card = json.load(f)

    image_url = f"https://raw.githubusercontent.com/{repo}/{BRANCH}/out/{card['file']}"
    print(f"이미지 주소: {image_url}")

    if not wait_until_public(image_url):
        sys.exit("이미지가 공개 주소에서 아직 안 보입니다. 잠시 후 다시 실행하세요.")

    caption = (f"{card['text']}\n"
               f"— {card['ref']} ({card['translation']})\n\n"
               f"{HASHTAGS}")

    # ① 컨테이너 생성
    container = post(f"{GRAPH}/{user_id}/media", {
        "image_url": image_url, "caption": caption, "access_token": token})
    print(f"컨테이너 생성: {container['id']}")
    time.sleep(5)

    # ② 발행
    result = post(f"{GRAPH}/{user_id}/media_publish", {
        "creation_id": container["id"], "access_token": token})
    print(f"발행 완료: {result}")


if __name__ == "__main__":
    main()
