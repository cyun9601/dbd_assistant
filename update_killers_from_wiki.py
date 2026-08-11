# -*- coding: utf-8 -*-
"""deadbydaylight.wiki.gg(공식 위키) 에서 살인마별 개요·파워·애드온 정보를 받아
killers.json / addons.json 으로 굽는다.

- 영어 필드(*_en)와 아이콘만 위키 최신본으로 갱신한다.
- 한글 필드(name/real_name/power_name/overview_html·text/power_html·text/desc_html·text)와
  별칭(aliases)·예전이름(former_names*)은 손으로 채우는 값 → 재실행 시 id 로 보존한다.
- 아이콘(초상화·파워·애드온)은 위키 PNG 를 webp 로 변환해 icons/ 하위에 저장한다.

퍽 파이프라인(update_en_from_wiki.py)의 검증된 유틸(fetch/clean_html/to_text/
save_icon_webp)을 그대로 재사용한다 — 색강조(Highlight)·줄바꿈 정제 규칙이 퍽과 동일.

설계 근거: docs/killers_addons_design.md

usage:
  python update_killers_from_wiki.py                 # 전체 살인마 수집
  python update_killers_from_wiki.py The_Trapper ...  # 특정 살인마만 (개발/검증용)
"""
import re, json, os, sys, html as htmllib, urllib.parse

from update_en_from_wiki import (
    BASE, HERE, fetch, clean_html, to_text, save_icon_webp,
    PTB_BANNER, PATCH_DATES, patch_release_date, is_upcoming,
)

# 아직 출시 전인 챕터의 살인마 → 그가 나올 패치. 위키는 미출시 살인마도 목록에
# 그냥 실어서(초상화 갤러리에 바로 뜬다) 구조만으로는 못 가려낸다. 퍽 쪽
# UPCOMING_OWNERS 와 같은 방식이며, 출시일이 지나면 자동으로 해제된다.
UPCOMING_KILLERS = {
    "The Judgment": "10.1.0",
}

# 위키가 쓰는 애드온 등급 클래스(<등급>-item-element) → 우리 표기.
# 최고 등급(이리데슨트)은 위키가 'visceral' 로 표기한다(= ultra-rare).
RARITY = {
    "common": "common", "uncommon": "uncommon", "rare": "rare",
    "very-rare": "very_rare", "visceral": "ultra_rare", "ultra-rare": "ultra_rare",
}


def api_parse(page):
    """MediaWiki parse API 로 페이지 HTML 과 (리다이렉트 추적된) 최종 제목을 받는다.
    page 가 이미 %-인코딩(예: The_Onry%C5%8D)돼 있어도 unquote 후 다시 quote 해
    이중 인코딩을 막는다."""
    url = (BASE + "/api.php?action=parse&format=json&redirects=1"
           "&prop=text|title&page=" + urllib.parse.quote(urllib.parse.unquote(page)))
    d = json.loads(fetch(url).decode("utf-8", "replace"))["parse"]
    return d["text"]["*"], d["title"]


# ───────────────────────── 살인마 목록 ─────────────────────────
def killer_list():
    """Killers 페이지의 'List of Killers' 갤러리에서 살인마 목록을 뽑는다.
    반환: [(id=표시명페이지, name_en=표시명, portrait_png)]  — 위키 나열 순서 유지."""
    html, _ = api_parse("Killers")
    m = re.search(r'id="List_of_Killers"', html)
    if not m:
        raise RuntimeError("Killers 페이지에서 'List of Killers' 를 찾지 못함 — 위키 구조 변경?")
    nxt = re.search(r'<h[1-6][ >]', html[m.end():])
    sec = html[m.end(): m.end() + (nxt.start() if nxt else len(html))]

    out, seen = [], set()
    # <div class="charPortraitImage ..."><a href="/wiki/The_X" title="The X"><img ... src="/images/PORTRAIT.png?..">
    pat = re.compile(
        r'<div class="charPortraitImage[^"]*"[^>]*>\s*'
        r'<a href="/wiki/([^"]+)"[^>]*title="([^"]+)"[^>]*>\s*'
        r'<img[^>]+src="/images/([^"?]+)')
    for a in pat.finditer(sec):
        kid = urllib.parse.unquote(a.group(1))   # 예: The_Onry%C5%8D → The_Onryō
        if kid in seen:
            continue
        seen.add(kid)
        out.append((kid, htmllib.unescape(a.group(2)).strip(), a.group(3)))
    if not out:
        raise RuntimeError("살인마 초상화 갤러리를 파싱하지 못함 — 위키 구조 변경?")
    return out


# ───────────────────────── 구획 추출 ─────────────────────────
def section(html, id_regex):
    """헤드라인(id 가 id_regex 에 매칭) 다음부터 다음 헤드라인 전까지의 HTML 과
    헤드라인 텍스트를 반환. 없으면 (None, None)."""
    m = re.search(r'<span class="mw-headline" id="(%s)"[^>]*>(.*?)</span>' % id_regex,
                  html, re.S)
    if not m:
        return None, None
    title = to_text(m.group(2))
    hclose = re.search(r'</h[1-6]>', html[m.end():])       # 현재 헤딩 태그의 끝
    start = m.end() + (hclose.end() if hclose else 0)
    nxt = re.search(r'<h[1-6][ >]', html[start:])          # 다음 헤딩 시작
    end = start + (nxt.start() if nxt else len(html) - start)
    return title, html[start:end]


# ───────────────────────── 애드온 표 ─────────────────────────
def parse_addons(html, killer_id):
    """'Add-ons for <파워>' 헤드라인 직후 wikitable 에서 애드온 행들을 뽑는다."""
    a = re.search(r'<span class="mw-headline" id="Add-ons_for_[^"]+"', html)
    if not a:
        return []
    t = html.find('<table class="wikitable overflowScroll"', a.end())
    if t < 0:
        return []
    tend = html.find('</table>', t)
    tbl = html[t:tend if tend > 0 else len(html)]

    rows = []
    for tr in re.findall(r'<tr[^>]*>(.*?)</tr>', tbl, re.S):
        td = re.search(r'<td[^>]*>(.*?)</td>', tr, re.S)   # 설명 셀 (데이터 행에만 존재)
        if not td:
            continue                                        # 헤더 행(<th> only) 스킵
        # 이름: 링크 텍스트가 비지 않은 <a href="/wiki/..."> (아이콘 셀 링크는 <img>라 텍스트 없음)
        name = pageid = None
        for lk in re.finditer(r'<a href="/wiki/([^"]+)"[^>]*>(.*?)</a>', tr, re.S):
            txt = to_text(lk.group(2))
            if txt:
                pageid = urllib.parse.unquote(lk.group(1))
                name = htmllib.unescape(txt).strip()
                break
        if not pageid:
            continue
        # 아이콘: 구형은 'IconAddon_', 신형(최신 챕터)은 접두사 붙은 'T_UI_iconAddon_'.
        icon = re.search(r'/images/((?:T_UI_)?[Ii]conAddon_[^"?/]+\.png)', tr)
        rc = re.search(r'([a-z-]+)-item-element', tr)
        desc, _ = strip_banner(clean_html(td.group(1)))
        rows.append({
            "id": pageid,
            "killer_id": killer_id,
            "name_en": name,
            "rarity": RARITY.get(rc.group(1)) if rc else None,
            "icon_wiki": icon.group(1) if icon else None,
            "desc_html_en": desc,
            "desc_text_en": to_text(desc),
        })
    return rows


def strip_banner(html):
    """위키가 다음 패치 기준으로 미리 고쳐 둔 설명 앞에 붙이는 안내 문구를 걷어낸다.
    그대로 두면 본문에 섞여 들어간다(퍽 파이프라인과 동일한 처리).
    반환: (정제된 html, 안내 문구가 가리킨 패치 번호 or None)."""
    if not html:
        return html, None
    m = PTB_BANNER.search(html)
    if not m:
        return html, None
    return clean_html(PTB_BANNER.sub('', html).strip()), m.group(1)


def _pick_power_icon(pw_html, power_name_en):
    """파워 구획의 파워 아이콘 파일명. 구형 'IconPowers_' + 신형 'T_UI_iconPowers_'.
    일부 살인마(쉐이프 등)는 하위 능력 아이콘이 여러 개라, 파워 이름과 일치하는
    것을 우선 고르고 없으면 첫 번째(주 능력)를 쓴다."""
    if not pw_html:
        return None
    cands = list(dict.fromkeys(
        re.findall(r'/images/((?:T_UI_)?[Ii]conPowers_[^"?/]+\.png)', pw_html)))
    if not cands:
        return None
    pn = re.sub(r"[^a-z0-9]", "", (power_name_en or "").lower())
    for c in cands:
        core = re.sub(r"[^a-z0-9]", "",
                      re.sub(r".*iconPowers_", "", c, flags=re.I).rsplit(".", 1)[0].lower())
        if pn and (core == pn or core in pn or pn in core):
            return c
    return cands[0]


# ───────────────────────── 살인마 파싱 ─────────────────────────
def parse_killer(kid, name_en, portrait_png):
    html, _ = api_parse(kid)

    _, ov_html = section(html, "Overview")
    ov_html, ov_patch = strip_banner(clean_html(ov_html) if ov_html else "")

    pw_title, pw_html = section(html, r"Power:_[^\"]+")
    power_name_en = re.sub(r"^Power:\s*", "", pw_title or "").strip()
    power_icon_wiki = _pick_power_icon(pw_html, power_name_en)
    pw_clean, pw_patch = strip_banner(clean_html(pw_html) if pw_html else "")

    addons = parse_addons(html, kid)

    killer = {
        "id": kid,
        "name": "",
        "name_en": name_en,
        "power_name": "",
        "power_name_en": power_name_en,
        "portrait_wiki": portrait_png,
        "power_icon_wiki": power_icon_wiki,
        "overview_html": "",
        "overview_text": "",
        "overview_html_en": ov_html,
        "overview_text_en": to_text(ov_html),
        "power_html": "",
        "power_text": "",
        "power_html_en": pw_clean,
        "power_text_en": to_text(pw_clean),
        "addon_ids": [a["id"] for a in addons],
    }

    # 출시 예정 표시 — 미출시 챕터 살인마이거나, 위키가 개요/파워에 안내 문구를 달아 둔 경우.
    # 날짜는 위키 Release Dates 표를 먼저 보고, 아직 TBA 면 PATCH_DATES 를 쓴다.
    # 출시일이 지나면 다음 실행 때 자동으로 빠진다.
    patch = UPCOMING_KILLERS.get(name_en) or ov_patch or pw_patch
    date = (patch_release_date(patch) or PATCH_DATES.get(patch)) if patch else None
    if patch and is_upcoming(date):
        killer["upcoming"] = True
        killer["upcoming_patch"] = patch
        killer["upcoming_date"] = date

    return killer, addons


# ───────────────────────── 아이콘 ─────────────────────────
def dl_icon(wiki_name, dest_rel):
    try:
        save_icon_webp(wiki_name, dest_rel)
        return True
    except Exception as e:  # noqa
        sys.stderr.write(f"  ICONFAIL {dest_rel} <- {wiki_name}: {repr(e)[:60]}\n")
        return False


# ───────────────────────── 병합(수동 필드 보존) ─────────────────────────
KILLER_MANUAL = ("name", "power_name",
                 "overview_html", "overview_text", "power_html", "power_text",
                 "aliases", "former_names", "former_names_en")
ADDON_MANUAL = ("name", "desc_html", "desc_text")


def _load(path):
    try:
        with open(path, encoding="utf-8") as f:
            return {x["id"]: x for x in json.load(f)}
    except (FileNotFoundError, ValueError):
        return {}


def carry(new, old, fields, defaults):
    """기존(old) 레코드의 수동 필드를 new 로 이어받는다. 없으면 defaults."""
    for f in fields:
        new[f] = old.get(f, defaults.get(f, ""))


# ───────────────────────── 메인 ─────────────────────────
def main(argv):
    only = {urllib.parse.unquote(a) for a in argv}   # 인코딩된 id(The_Onry%C5%8D)로도 지정 가능
    sys.stderr.write("Fetching Killers list...\n")
    lst = killer_list()
    if only:
        lst = [x for x in lst if x[0] in only]
    sys.stderr.write(f"  {len(lst)} killers to fetch\n")

    prev_k = _load(os.path.join(HERE, "killers.json"))
    prev_a = _load(os.path.join(HERE, "addons.json"))

    killers, addons = [], []
    n_icon = 0
    for kid, name_en, portrait in lst:
        try:
            k, ax = parse_killer(kid, name_en, portrait)
        except Exception as e:  # noqa — 개별 실패는 건너뛰고 계속
            sys.stderr.write(f"  FAIL {kid}: {repr(e)[:80]}\n")
            continue

        # 초상화 · 파워 아이콘 (위키 원본 파일명은 임시 필드로 넘어옴 → pop 후 다운로드)
        k.pop("portrait_wiki", None)
        pw_wiki = k.pop("power_icon_wiki", None)
        k["portrait_file"] = f"icons/killer_portrait/{kid}.webp"
        if dl_icon(portrait, k["portrait_file"]):
            n_icon += 1
        if pw_wiki:
            k["power_icon"] = f"icons/power/{kid}.webp"
            if dl_icon(pw_wiki, k["power_icon"]):
                n_icon += 1
        else:
            k["power_icon"] = ""

        carry(k, prev_k.get(kid, {}), KILLER_MANUAL,
              {"aliases": [], "former_names": [], "former_names_en": []})
        k["search_blob"] = " ".join(filter(None, [
            k["name"], k["name_en"], k["power_name_en"],
            k["overview_text_en"], k["power_text_en"]]))
        killers.append(k)

        # 애드온
        for a in ax:
            iw = a.pop("icon_wiki", None)
            if iw:
                a["icon_file"] = f"icons/addon/{iw.rsplit('.', 1)[0]}.webp"
                if dl_icon(iw, a["icon_file"]):
                    n_icon += 1
            else:
                a["icon_file"] = ""
            carry(a, prev_a.get(a["id"], {}), ADDON_MANUAL, {})
            a["search_blob"] = " ".join(filter(None, [
                a["name"], a["name_en"], a["desc_text_en"]]))
            addons.append(a)

        sys.stderr.write(f"  [{len(killers):2}] {name_en:22} "
                         f"power={k['power_name_en']!r:28} addons={len(ax)}\n")

    # 저장 (perks.json 과 동일 포맷)
    _dump(os.path.join(HERE, "killers.json"), killers, only, prev_k, "id")
    _dump(os.path.join(HERE, "addons.json"), addons, only, prev_a, "id")
    sys.stderr.write(
        f"\nDone. killers={len(killers)}, addons={len(addons)}, icons={n_icon}\n")


def _dump(path, records, only, prev, key):
    """부분 실행(only) 시 기존 레코드를 유지하며 갱신분만 덮어써 저장."""
    if only:
        merged = dict(prev)
        for r in records:
            merged[r[key]] = r
        records = list(merged.values())
    with open(path, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=1)
    sys.stderr.write(f"Wrote {path} ({len(records)} records)\n")


if __name__ == "__main__":
    main(sys.argv[1:])
