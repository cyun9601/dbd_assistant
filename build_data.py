# -*- coding: utf-8 -*-
"""
dbd-db.com 에서 살인마(killer) 퍽 데이터를 추출하고,
한글 설명문을 /api/localization/resolve API로 채운 뒤 perks.json 으로 저장.
아이콘도 icons/ 폴더에 내려받는다.

usage: python build_data.py
"""
import re, json, os, sys, time, urllib.request, urllib.error

BASE = "https://dbd-db.com"
CDN = "https://pub-563d6f059a934468a5878194b3ab67ae.r2.dev/"
UA = {"User-Agent": "Mozilla/5.0"}
HERE = os.path.dirname(os.path.abspath(__file__))
ICON_DIR = os.path.join(HERE, "icons")


def fetch(url, data=None, headers=None, retries=3):
    h = dict(UA)
    if headers:
        h.update(headers)
    body = data.encode("utf-8") if isinstance(data, str) else data
    last = None
    for i in range(retries):
        try:
            req = urllib.request.Request(url, data=body, headers=h)
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read()
        except Exception as e:  # noqa
            last = e
            time.sleep(1 + i)
    raise last


def parse_perks(html):
    """임베드된 escaped JSON 에서 퍽 레코드들을 추출."""
    # 필드들이 \" 로 escape 되어 있다. 각 perk_id 블록을 잡는다.
    recs = re.findall(
        r'\{\\"perk_id\\":\\"(.*?)\\".*?'
        r'\\"role\\":\\"(.*?)\\".*?'
        r'\\"slug\\":\\"(.*?)\\".*?'
        r'\\"name_key\\":\\"(.*?)\\".*?'
        r'\\"desc_key\\":\\"(.*?)\\".*?'
        r'\\"icon_path\\":\\"(.*?)\\".*?'
        r'\\"perk_tunables\\":(\[.*?\]).*?'
        r'\\"name\\":\\"(.*?)\\",\\"owner_name\\":\\"(.*?)\\"',
        html,
    )
    out = []
    for perk_id, role, slug, name_key, desc_key, icon, tun, name, owner in recs:
        try:
            tunables = json.loads(tun)
        except Exception:
            tunables = []
        out.append({
            "perk_id": perk_id,
            "role": role,
            "slug": slug,
            "name_key": name_key,
            "desc_key": desc_key,
            "icon_path": icon,
            "tunables": tunables,
            "name": name,
            "owner": owner,
        })
    return out


def resolve_keys(keys, locale="ko", chunk=40):
    """desc_key -> 한글 텍스트 매핑."""
    result = {}
    for i in range(0, len(keys), chunk):
        batch = keys[i:i + chunk]
        payload = json.dumps({"locale": locale, "keys": batch, "fallbacks": ["en"]})
        raw = fetch(BASE + "/api/localization/resolve", data=payload,
                    headers={"content-type": "application/json"})
        m = json.loads(raw.decode("utf-8")).get("map", {})
        result.update(m)
        sys.stderr.write(f"  resolved {min(i+chunk,len(keys))}/{len(keys)}\n")
    return result


def fill_tunables(text, tunables):
    """{0},{1}.. 플레이스홀더를 perk_tunables 값으로 치환."""
    def repl(m):
        idx = int(m.group(1))
        if idx < len(tunables):
            return str(tunables[idx])
        return m.group(0)
    return re.sub(r"\{(\d+)\}", repl, text or "")


def strip_html(text):
    text = re.sub(r"<br\s*/?>", " ", text or "")
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def norm_icon_path(path):
    """일부 신규 퍽은 데이터엔 'IconPerks_' 로 기록되나 CDN 파일은 'iconPerks_' (소문자 i)."""
    return path.replace("/IconPerks_", "/iconPerks_")


def download_icons(perks):
    os.makedirs(ICON_DIR, exist_ok=True)
    for p in perks:
        p["icon_path"] = norm_icon_path(p["icon_path"])
        fname = p["icon_path"].split("/")[-1]
        dest = os.path.join(ICON_DIR, fname)
        p["icon_file"] = "icons/" + fname
        if os.path.exists(dest) and os.path.getsize(dest) > 0:
            continue
        try:
            data = fetch(CDN + p["icon_path"])
            with open(dest, "wb") as f:
                f.write(data)
            sys.stderr.write(f"  icon {fname}\n")
        except Exception as e:  # noqa
            sys.stderr.write(f"  ICON FAIL {fname}: {e}\n")


def main():
    sys.stderr.write("Fetching perks page...\n")
    html = fetch(BASE + "/ko/perks").decode("utf-8", errors="replace")
    perks = parse_perks(html)
    killers = [p for p in perks if p["role"] == "killer"]
    sys.stderr.write(f"Parsed {len(perks)} total, {len(killers)} killer perks\n")

    sys.stderr.write("Resolving Korean descriptions...\n")
    desc_keys = sorted({p["desc_key"] for p in killers})
    desc_map = resolve_keys(desc_keys, "ko")

    for p in killers:
        raw = desc_map.get(p["desc_key"], "")
        filled = fill_tunables(raw, p["tunables"])
        p["desc_html"] = filled
        p["desc_text"] = strip_html(filled)
        p["icon_path"] = norm_icon_path(p["icon_path"])
        # 검색용 통합 텍스트
        p["search_blob"] = f"{p['name']} {p['owner']} {p['desc_text']}"

    sys.stderr.write("Downloading icons...\n")
    download_icons(killers)

    # 출력 정리 (앱에서 필요한 필드만)
    clean = [{
        "id": p["perk_id"],
        "name": p["name"],
        "owner": p["owner"],
        "icon_file": p["icon_file"],
        "desc_html": p["desc_html"],
        "desc_text": p["desc_text"],
        "search_blob": p["search_blob"],
    } for p in killers]
    clean.sort(key=lambda x: x["name"])

    out_path = os.path.join(HERE, "perks.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(clean, f, ensure_ascii=False, indent=1)
    sys.stderr.write(f"Wrote {out_path} ({len(clean)} killer perks)\n")

    # file:// 더블클릭으로도 열 수 있게 JS 모듈로도 내보낸다 (fetch CORS 회피)
    js_path = os.path.join(HERE, "perks_data.js")
    with open(js_path, "w", encoding="utf-8") as f:
        f.write("// 자동 생성됨 - build_data.py\n")
        f.write("window.PERKS = ")
        json.dump(clean, f, ensure_ascii=False)
        f.write(";\n")
    sys.stderr.write(f"Wrote {js_path}\n")


if __name__ == "__main__":
    main()
