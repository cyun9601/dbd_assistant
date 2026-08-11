# -*- coding: utf-8 -*-
"""Steam 공식 공지(DBD)에서 패치노트를 받아 `patchnotes.json` 으로 굽는다.

앱의 📜 패치노트 탭이 이 파일을 읽는다(서버 `GET /patchnotes`).

- 출처는 Steam 파트너 이벤트 API — 스토어 뉴스 페이지와 같은 원문이며,
  제목·작성일·본문(BBCode)이 그대로 들어 있다. 위키보다 1차 자료에 가깝다.
- 본문 BBCode 는 앱이 그대로 그릴 수 있는 최소 HTML(<b>/<i>/<a>)과
  블록 목록(h2/h3/p/li)으로 바꾼다. 이미지는 오프라인에서 못 받으므로 버린다.
- 각 패치가 언급한 퍽을 `perk_ids` 로 뽑아 둔다 — 앱에서 한글 퍽 이름 칩으로
  보여주고 누르면 그 퍽 카드로 이동한다. 공식 노트가 라이선스 만료 이름
  (예: Keep Them Waiting)을 쓰므로 `former_names_en` 까지 같이 대조한다.

usage: python update_patchnotes_from_steam.py [--count 50]
"""
import datetime
import html as htmllib
import json
import os
import re
import sys
import urllib.request

APPID = 381210
BASE = "https://store.steampowered.com"
EVENTS = (f"{BASE}/events/ajaxgetpartnereventspageable/"
          f"?clan_accountid=0&appid={APPID}&offset=0&count=%d&l=english")
NEWS_URL = BASE + "/news/app/%d/view/%s" % (APPID, "%s")
UA = {"User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                     "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")}
HERE = os.path.dirname(os.path.abspath(__file__))

# 패치노트로 볼 글 — "10.1.0 | PTB Patch Notes", "10.0.1", "9.6.2 | Bugfix Patch" 등
VERSION_RE = re.compile(r'(\d+\.\d+\.\d+)')
NOTE_TITLE_RE = re.compile(r'^\s*\d+\.\d+\.\d+|patch notes|bugfix patch', re.I)


def fetch(url, retries=3):
    last = None
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.read().decode('utf-8', 'replace')
        except Exception as e:  # noqa
            last = e
    raise last


# ───────────────────────── BBCode → 블록 ─────────────────────────
def _inline(s):
    """인라인 서식만 남긴다 — 굵게/기울임/링크. 나머지 태그는 버린다."""
    s = re.sub(r'\[/?(?:b|strong)\]', lambda m: '</b>' if m.group(0)[1] == '/' else '<b>', s)
    s = re.sub(r'\[/?(?:i|em)\]', lambda m: '</i>' if m.group(0)[1] == '/' else '<i>', s)
    s = re.sub(r'\[url=([^\]]+)\](.*?)\[/url\]',
               lambda m: f'<a href="{htmllib.escape(m.group(1), quote=True)}" '
                         f'target="_blank" rel="noopener">{m.group(2)}</a>', s, flags=re.S)
    s = re.sub(r'\[img[^\]]*\].*?\[/img\]', '', s, flags=re.S)   # 이미지는 오프라인 불가
    s = re.sub(r'\[/?[a-zA-Z][^\]]*\]', '', s)                   # 남은 BBCode 제거
    # 원문에 비줄바꿈 공백(\xa0)이 섞여 있다 — 퍽 데이터(clean_html)와 같게 보통 공백으로
    s = s.replace('\r', ' ').replace('\n', ' ').replace('\xa0', ' ')
    s = re.sub(r'\s{2,}', ' ', s)
    return s.strip()


def to_blocks(body):
    """공지 본문(BBCode)을 h2/h3/p/li 블록 목록으로 편다.

    Steam 본문은 `[list][*][p]문장[/p][/*][/list]` 처럼 li 안에 p 를 넣는다.
    그래서 p 라도 열려 있는 [*] 안이면 **불릿(li)** 으로 보고, [list] 중첩
    깊이를 들여쓰기(lvl)로 쓴다. 블록은 닫힐 때 만들어지므로(= 자식이 먼저
    닫힘) 마지막에 원문 위치 순으로 정렬해 순서를 되돌린다.
    """
    blocks, depth, pos, stack = [], 0, 0, []
    token = re.compile(r'\[(/?)(h1|h2|h3|p|list|\*)\]', re.I)
    while True:
        m = token.search(body, pos)
        if not m:
            break
        closing, tag = m.group(1) == '/', m.group(2).lower()
        if not closing:
            if tag == 'list':
                depth += 1
            else:
                stack.append((tag, m.end(), depth))
        elif tag == 'list':
            depth = max(0, depth - 1)
        else:
            # 같은 태그의 여는 짝을 찾아 닫는다 (짝이 안 맞는 본문도 견디게)
            for i in range(len(stack) - 1, -1, -1):
                if stack[i][0] != tag:
                    continue
                t, start, d = stack.pop(i)
                raw = body[start:m.start()]
                cut = token.search(raw)                  # 자식 블록 앞까지가 자기 몫
                text = _inline(raw[:cut.start()] if cut else raw)
                if text:
                    if t in ('h1', 'h2', 'h3'):
                        blocks.append((start, {"t": 'h2' if t != 'h3' else 'h3',
                                               "html": text}))
                    else:
                        open_li = [s for s in stack if s[0] == '*']
                        if t == '*' or open_li:
                            lvl = d if t == '*' else open_li[-1][2]
                            blocks.append((start, {"t": "li", "html": text,
                                                   "lvl": max(0, lvl - 1)}))
                        else:
                            blocks.append((start, {"t": "p", "html": text}))
                break
        pos = m.end()

    blocks.sort(key=lambda b: b[0])
    out = []
    for _, b in blocks:                                  # 인접 중복 문장 제거
        if out and out[-1]["html"] == b["html"]:
            continue
        out.append(b)
    return out


# ───────────────────────── 퍽 언급 추출 ─────────────────────────
def nkey(s):
    return re.sub(r'[^a-z0-9]', '', htmllib.unescape(s or '').lower())


def perk_index():
    """퍽 이름(영문) + 라이선스 만료 개명 이름 → perk id"""
    perks = json.load(open(os.path.join(HERE, "perks.json"), encoding='utf-8'))
    idx = {}
    for p in perks:
        for nm in [p['name_en']] + (p.get('former_names_en') or []):
            if nm and len(nkey(nm)) >= 4:      # 너무 짧은 이름은 오탐 위험
                idx.setdefault(nkey(nm), p['id'])
    return idx


def perks_mentioned(body, idx):
    """굵게 표시된 조각과 '퍽 이름:' 형태에서만 찾는다 — 오탐을 줄이려는 제한."""
    found = []
    cands = re.findall(r'\[b\](.*?)\[/b\]', body, re.S)
    cands += re.findall(r'\[/?[a-z]*\]?([A-Z][\w\'\- ]{3,40}):', body)
    for c in cands:
        k = nkey(re.sub(r'\(.*?\)', '', c))
        pid = idx.get(k)
        if pid and pid not in found:
            found.append(pid)
    return found


PERK_SECTION_RE = re.compile(r'perk\s+(?:updates?|changes?)', re.I)


def perks_changed(blocks, idx):
    """'Killer/Survivor perk updates' 섹션의 최상위 불릿 = 이번 패치에 수치가 바뀌는 퍽.

    단순 언급(perk_ids)과 달리 **실제 변경 대상**만 추린다. 위키가 어떤 퍽에는
    미출시 안내 문구를 빠뜨리기도 해서(예: 10.1.0 의 Deliverance), 공식 노트의
    이 목록이 '무엇이 바뀌는가' 에 대해서는 더 믿을 만하다.
    """
    out, inside = [], False
    for b in blocks:
        if b['t'] in ('h2', 'h3'):
            inside = bool(PERK_SECTION_RE.search(b['html']))
            continue
        if not inside or b['t'] != 'li' or b.get('lvl', 0) != 0:
            continue
        m = re.match(r'\s*<b>(.+?)</b>\s*$', b['html'])
        if not m:
            continue
        pid = idx.get(nkey(re.sub(r'</?[bi]>|\(.*?\)', '', m.group(1)).rstrip(': ')))
        if pid and pid not in out:
            out.append(pid)
    return out


# ───────────────────────── 메인 ─────────────────────────
def main():
    count = 50
    if '--count' in sys.argv:
        count = int(sys.argv[sys.argv.index('--count') + 1])
    sys.stderr.write(f"Fetching Steam announcements (count={count})...\n")
    data = json.loads(fetch(EVENTS % count))
    events = data.get('events') or []
    idx = perk_index()

    patches = []
    for e in events:
        title = (e.get('event_name') or '').strip()
        if not NOTE_TITLE_RE.search(title):
            continue
        body = (e.get('announcement_body') or {}).get('body') or ''
        if not body:
            continue
        gid = str(e['gid'])
        ver = VERSION_RE.search(title)
        date = datetime.date.fromtimestamp(e['rtime32_start_time']).isoformat()
        blocks = to_blocks(body)
        patches.append({
            "id": gid,
            "version": ver.group(1) if ver else "",
            "title": title,
            "date": date,
            "ptb": bool(re.search(r'\bPTB\b', title, re.I)),
            "url": NEWS_URL % gid,
            "perk_ids": perks_mentioned(body, idx),
            "perk_updates": perks_changed(blocks, idx),
            "blocks": blocks,
        })
        sys.stderr.write(f"  {date}  {title[:48]:50} blocks={len(blocks):4} "
                         f"perks={len(patches[-1]['perk_ids']):3} "
                         f"changed={len(patches[-1]['perk_updates'])}\n")

    patches.sort(key=lambda p: (p['date'], p['version']), reverse=True)
    out = {
        "source": "Steam 공식 공지 (Dead by Daylight)",
        "source_url": f"{BASE}/news/app/{APPID}",
        "fetched": datetime.date.today().isoformat(),
        "note": "본문은 공식 원문(영어) 그대로입니다 — Steam 에 한국어판 공지가 없습니다.",
        "patches": patches,
    }
    path = os.path.join(HERE, "patchnotes.json")
    with open(path, "w", encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    size = os.path.getsize(path) / 1024
    sys.stderr.write(f"\nDone. {len(patches)} patches -> patchnotes.json ({size:.0f} KB)\n")


if __name__ == "__main__":
    main()
