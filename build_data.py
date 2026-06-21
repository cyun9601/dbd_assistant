# -*- coding: utf-8 -*-
"""
dbd-db.com 에서 살인마(killer)·생존자(survivor) 퍽 데이터를 추출하고,
한글 설명문을 /api/localization/resolve API로 채운 뒤 perks.json 으로 저장.
각 퍽엔 role("killer"/"survivor") 필드가 붙고, 아이콘은 진영별
icons/killer/, icons/survivor/ 폴더에 내려받는다.

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


def _lower_first_after_prefix(base):
    """파일명에서 'iconPerks_' 뒤 첫 글자를 소문자로 (BlastMine -> blastMine)."""
    m = re.search(r"(?i)(iconperks_)(.)", base)
    if m and m.group(2).isupper():
        i = m.start(2)
        return base[:i] + base[i].lower() + base[i + 1:]
    return base


def _icon_candidates(path):
    """CDN 경로 후보들. 일부 퍽은 'Perks/' 아래 하위 폴더가 없거나
    파일명 첫 글자가 소문자라 원본 경로로는 404 가 난다 (예: Blast Mine)."""
    fname = path.split("/")[-1]
    cands = [path]
    # 'Perks/' 아래 하위 폴더 제거(평면화): .../Perks/Eclipse/x.webp -> .../Perks/x.webp
    if "/Perks/" in path:
        cands.append(path.split("/Perks/")[0] + "/Perks/" + fname)
    # 위 후보들의 파일명 첫 글자를 소문자로 한 변형도 추가
    out = []
    for c in cands:
        if c not in out:
            out.append(c)
        head, sep, base = c.rpartition("/")
        lc = _lower_first_after_prefix(base)
        alt = (head + sep + lc) if sep else lc
        if alt not in out:
            out.append(alt)
    return out


def download_icons(perks):
    # 아이콘은 진영별 하위 폴더에 저장: icons/killer/, icons/survivor/
    os.makedirs(ICON_DIR, exist_ok=True)
    for p in perks:
        p["icon_path"] = norm_icon_path(p["icon_path"])
        candidates = _icon_candidates(p["icon_path"])
        role_dir = os.path.join(ICON_DIR, p["role"])
        os.makedirs(role_dir, exist_ok=True)
        rel = f"icons/{p['role']}/"

        def local(c):
            return os.path.join(role_dir, c.split("/")[-1])

        # 이미 받아둔 파일이 있으면(어떤 후보 이름으로든) 그대로 사용
        have = next((c for c in candidates
                     if os.path.exists(local(c)) and os.path.getsize(local(c)) > 0), None)
        if have:
            p["icon_file"] = rel + have.split("/")[-1]
            continue

        saved = None
        for c in candidates:
            try:
                data = fetch(CDN + c)
                fname = c.split("/")[-1]
                with open(local(c), "wb") as f:
                    f.write(data)
                sys.stderr.write(f"  icon {p['role']}/{fname}\n")
                saved = fname
                break
            except Exception:  # noqa  (다음 후보 시도)
                continue
        # 받은 파일명으로 icon_file 기록 (못 받으면 원본 파일명 그대로 — 앱은 동작)
        p["icon_file"] = rel + (saved or p["icon_path"].split("/")[-1])
        if not saved:
            sys.stderr.write(f"  ICON FAIL {p['icon_path'].split('/')[-1]}\n")


def add_nightlight(clean):
    """각 퍽에 nl_id(nightlight 숫자 id) 와 usage(기준 사용률 %) 필드를 채운다.
    매핑 키는 dbd-db slug ↔ nightlight 이미지 slug. 실패해도 빌드는 계속(필드는 None)."""
    for p in clean:                      # 기본값 — 실패하거나 매칭 안 되면 그대로
        p.setdefault("nl_id", None)
        p.setdefault("usage", None)
    try:
        import re as _re
        import nightlight
        sys.stderr.write("Fetching nightlight usage...\n")
        perk_dict = nightlight.fetch_perk_dict()
        by_slug, by_norm = nightlight.slug_index(perk_dict)
        usage = nightlight.fetch_usage()

        def _norm(s):
            return _re.sub(r"[^a-z0-9]", "", (s or "").lower())

        mapped = 0
        for p in clean:
            slug = p.get("slug") or ""
            nid = by_slug.get(slug) or by_norm.get(_norm(slug))
            if not nid:
                continue
            p["nl_id"] = int(nid)
            row = usage.get(p["role"], {}).get("perks", {}).get(nid)
            p["usage"] = row["pct"] if row else None
            mapped += 1
        win = usage.get("killer", {})
        sys.stderr.write(
            f"  nightlight mapped {mapped}/{len(clean)} perks "
            f"(window {win.get('start', '?')[:10]}~{win.get('end', '?')[:10]})\n")
    except Exception as e:  # noqa — 오프라인/사이트 구조 변경 등은 조용히 건너뜀
        sys.stderr.write(f"  nightlight 사용률 수집 건너뜀: {e}\n")


def main():
    sys.stderr.write("Fetching perks page...\n")
    html = fetch(BASE + "/ko/perks").decode("utf-8", errors="replace")
    perks = parse_perks(html)
    # 살인마(killer) + 생존자(survivor) 퍽 모두 수집
    kept = [p for p in perks if p["role"] in ("killer", "survivor")]
    n_killer = sum(1 for p in kept if p["role"] == "killer")
    n_surv = sum(1 for p in kept if p["role"] == "survivor")
    sys.stderr.write(
        f"Parsed {len(perks)} total, keeping {len(kept)} "
        f"({n_killer} killer, {n_surv} survivor)\n")

    sys.stderr.write("Resolving Korean descriptions...\n")
    desc_keys = sorted({p["desc_key"] for p in kept})
    desc_map = resolve_keys(desc_keys, "ko")

    # 영어 원문도 함께 받는다 — 표시 언어 전환 + 한글 오역 대비.
    # 이름·소유자(캐릭터)는 영어 페이지(/en/perks)에서 그대로 가져오고(정식 표기),
    # 설명문은 페이지에 없으므로 로컬라이제이션 API 로 en 을 받는다.
    sys.stderr.write("Fetching English perk page + descriptions...\n")
    en_by_id = {}
    try:
        en_html = fetch(BASE + "/en/perks").decode("utf-8", errors="replace")
        en_by_id = {p["perk_id"]: p for p in parse_perks(en_html)}
    except Exception as e:  # noqa — 실패해도 설명문 en 은 API 로 받으므로 진행
        sys.stderr.write(f"  /en/perks 가져오기 실패(이름/소유자 en 생략): {e}\n")
    desc_map_en = resolve_keys(desc_keys, "en")

    for p in kept:
        raw = desc_map.get(p["desc_key"], "")
        filled = fill_tunables(raw, p["tunables"])
        p["desc_html"] = filled
        p["desc_text"] = strip_html(filled)
        # 영어 원문(이름·소유자·설명). 플레이스홀더는 같은 tunables 로 채운다(언어 무관).
        en = en_by_id.get(p["perk_id"], {})
        p["name_en"] = en.get("name", "")
        p["owner_en"] = en.get("owner", "")
        filled_en = fill_tunables(desc_map_en.get(p["desc_key"], ""), p["tunables"])
        p["desc_html_en"] = filled_en
        p["desc_text_en"] = strip_html(filled_en)
        p["icon_path"] = norm_icon_path(p["icon_path"])
        # 검색용 통합 텍스트
        p["search_blob"] = f"{p['name']} {p['owner']} {p['desc_text']}"

    sys.stderr.write("Downloading icons...\n")
    download_icons(kept)

    # 출력 정리 (앱에서 필요한 필드만)
    clean = [{
        "id": p["perk_id"],
        "role": p["role"],
        "name": p["name"],
        "name_en": p["name_en"],      # 영어 원문 이름 (표시 언어 전환 · 번역 검증용)
        "owner": p["owner"],
        "owner_en": p["owner_en"],    # 영어 소유자(캐릭터)
        "slug": p["slug"],            # nightlight 사용률 매핑 키 (영문 kebab-case)
        "icon_file": p["icon_file"],
        "desc_html": p["desc_html"],
        "desc_text": p["desc_text"],
        "desc_html_en": p["desc_html_en"],   # 영어 원문 설명 (HTML, 표시용)
        "desc_text_en": p["desc_text_en"],   # 영어 원문 설명 (평문, 검색용)
        "search_blob": p["search_blob"],
    } for p in kept]

    # nightlight.gg 사용률 매핑: slug → nightlight 숫자 id(nl_id, 배포 무관 고정) +
    # 기준 사용률(usage). nl_id 를 구워 두면 런타임 서버는 안정 API 만으로 갱신할 수 있다.
    # 수집 실패(오프라인/사이트 변경)해도 퍽 데이터 빌드는 계속되도록 감싼다.
    add_nightlight(clean)

    # 살인마("killer")가 생존자("survivor")보다 앞, 그 안에서 이름순
    clean.sort(key=lambda x: (x["role"], x["name"]))

    out_path = os.path.join(HERE, "perks.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(clean, f, ensure_ascii=False, indent=1)
    sys.stderr.write(f"Wrote {out_path} ({len(clean)} perks)\n")


if __name__ == "__main__":
    main()
