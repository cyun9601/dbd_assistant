# -*- coding: utf-8 -*-
"""deadbydaylight.wiki.gg(공식 위키) 의 Perks 페이지에서 살인마·생존자 퍽의
영어 설명문과 아이콘을 받아 기존 perks.json 에 덮어쓴다.

- 한글 필드(name/owner/desc_html/desc_text 등)는 건드리지 않는다.
- desc_html_en / desc_text_en 만 위키 최신본으로 갱신한다.
- 아이콘은 위키 PNG 를 webp 로 변환해 기존 icon_file 경로에 덮어쓴다(경로 불변).
- 위키 개요표에 없는 신규 퍽(예: 최신 챕터 퍽)은 기존값을 그대로 둔다.
- 아직 안 나온 패치의 퍽에는 `upcoming` 표시(앱 카드의 칩)를 붙인다. 두 종류다 —
  미출시 챕터의 퍽 자체는 `upcoming_kind: "new"`(앱에서 **출시 예정**),
  이미 있는 퍽의 설명만 바뀌는 경우는 `"update"`(**업데이트 예정**).
  미출시 패치 기준으로 위키가 미리 고쳐 둔 설명은 그대로 받는다.
  표시는 위키 패치노트의 Release Dates 표에서 읽은 **출시일이 지나면 자동으로 해제**된다.
  위키 표가 아직 TBA 인 패치는 이 파일 위의 `PATCH_DATES` 에 적어 둔 날짜를 쓴다
  (표에 날짜가 올라오면 위키 값이 이를 덮는다).
- perks.json 에 아직 없는 위키 퍽은 **신규 후보로 보고**만 한다(한글 번역이
  수동이라 자동 추가하지 않음). 개명 일반퍽은 이미 아는 것/모르는 것으로 나눠 표시.

매칭 키: 아이콘 파일명(캐멀케이스 코어) → 정규화 이름 → 별칭 → ID 오버라이드.
개명으로 일반퍽이 된 퍽("Identical to X")은 해당 일반퍽의 설명을 끌어와
본문 내 일반퍽 이름을 원래(소유) 퍽 이름으로 치환한다.

usage: python update_en_from_wiki.py [--no-icons]
"""
import re, json, os, sys, io, time, datetime, urllib.request, urllib.parse, html as htmllib
from html.parser import HTMLParser
from PIL import Image

BASE = "https://deadbydaylight.wiki.gg"
UA = {"User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                     "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36")}
HERE = os.path.dirname(os.path.abspath(__file__))

# 영국식 철자 등 이름/아이콘이 둘 다 어긋나는 소수 보정 (우리 정규화이름 -> 위키 정규화이름)
ALIAS = {
    "hexbloodfavor": "hexbloodfavour",
}
# 이름·아이콘 모두 매칭 불가한 예외 (우리 perk id -> 위키 정규화이름)
ID_OVERRIDE = {
    "BBQAndChilli": "barbecuechilli",   # 우리 name_en 의 '&' 가 깨져 있고 아이콘명도 다름
}
# 위키가 다음 패치 기준으로 미리 고쳐 둔 설명에 붙는 안내 문구 (패치 번호 포함)
PTB_BANNER = re.compile(
    r'This description is based on the changes announced for or featured in '
    r'the upcoming Patch\s*(\d+\.\d+(?:\.\d+)?)', re.I)
TODAY = datetime.date.today().isoformat()
# 위키 Release Dates 표가 아직 TBA 인 패치의 출시일을 손으로 적어 두는 곳.
# 표에 날짜가 올라오면 위키 값이 이걸 덮으므로, 나중에 지우지 않아도 된다.
PATCH_DATES = {
    "10.1.0": "2026-08-25",
}
# 아직 출시 전인 챕터의 캐릭터 → 그 퍽들이 나올 패치. 위키는 미출시 챕터 퍽도
# 일반 퍽처럼 실어서(안내 문구 없음) 배너로는 못 가려낸다. 출시일이 지나면
# 다른 표시와 똑같이 자동으로 해제되므로 여기서 지우지 않아도 된다.
UPCOMING_OWNERS = {
    "The Judgment": "10.1.0",
    "Aurora Stardotter": "10.1.0",
}
MONTHS = {m: i for i, m in enumerate(
    ['January', 'February', 'March', 'April', 'May', 'June', 'July',
     'August', 'September', 'October', 'November', 'December'], 1)}
_dates_cache = {}


def patch_release_date(patch):
    """'10.1.0' → 라이브 출시일 'YYYY-MM-DD'. 아직 TBA/미기재면 None.

    위키 패치노트(`Patch Notes 10.1.X`)의 Release Dates 표를 그대로 읽는다.
    PTB 날짜가 아니라 **라이브 패치 날짜**만 본다(표의 'PTB 10.1.0' 행은 무시).
    """
    series = '.'.join(patch.split('.')[:2]) + '.X'
    if series not in _dates_cache:
        table = {}
        try:
            api = (f"{BASE}/api.php?action=parse&page=Patch_Notes_{series}"
                   f"&prop=text&format=json")
            html = json.loads(fetch(api).decode('utf-8', 'replace'))['parse']['text']['*']
            for ver, raw in re.findall(r'<th>\s*([\w.\s]+?)\s*</th>\s*<td>\s*(.*?)\s*</td>',
                                       html, re.S):
                m = re.match(r'(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})', htmllib.unescape(raw))
                if m and m.group(2) in MONTHS:
                    table[ver] = f"{m.group(3)}-{MONTHS[m.group(2)]:02d}-{int(m.group(1)):02d}"
                else:
                    table[ver] = None          # TBA
        except Exception as e:  # noqa
            sys.stderr.write(f"  (패치 {series} 날짜 표를 읽지 못함: {e!r} — 출시일 미정 처리)\n")
        _dates_cache[series] = table
    return _dates_cache[series].get(patch)


def is_upcoming(date, today=None):
    """출시일이 아직 안 왔거나(미래) 아직 미정(None)이면 '출시 예정'."""
    return not (date and date <= (today or TODAY))


def pending_perk_updates():
    """아직 안 나온 패치에서 수치가 바뀌는 퍽 → {perk id: 패치}.

    `patchnotes.json`(Steam 공식 노트) 의 'perk updates' 목록을 쓴다. 위키가 어떤
    퍽에는 미출시 안내 문구를 빠뜨리기 때문에(10.1.0 의 Deliverance) 배너만으로는
    놓친다. 파일이 없으면 빈 dict — 그 경우 배너 감지로만 동작한다.
    """
    try:
        data = json.load(open(os.path.join(HERE, "patchnotes.json"), encoding='utf-8'))
    except (FileNotFoundError, ValueError):
        sys.stderr.write("  (patchnotes.json 없음 — 미출시 퍽 변경은 위키 배너로만 감지)\n")
        return {}
    out = {}
    for pt in data.get('patches') or []:
        ver = pt.get('version')
        if not ver:
            continue
        if not is_upcoming(patch_release_date(ver) or PATCH_DATES.get(ver)):
            continue                      # 이미 나온 패치
        for pid in pt.get('perk_updates') or []:
            out.setdefault(pid, ver)
    return out


def fetch(url, retries=3):
    last = None
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.read()
        except Exception as e:  # noqa
            last = e
            time.sleep(1 + i)
    raise last


# ───────────────────────── 행 추출 ─────────────────────────
def balanced_td(s, start):
    """start('<td' 위치)부터 중첩 td/th 를 고려해 매칭 </td> 까지 반환."""
    i, depth = start, 0
    while i < len(s):
        if s.startswith('<td', i) or s.startswith('<th', i):
            depth += 1; i += 3; continue
        if s.startswith('</td>', i) or s.startswith('</th>', i):
            depth -= 1
            if depth == 0:
                return s[start:i + 5]
            i += 5; continue
        i += 1
    return s[start:]


def parse_rows(html):
    allt = [m.start() for m in re.finditer(r'<table class="wikitable', html)]
    tbl = [m.start() for m in re.finditer(r'<table class="wikitable overflowScroll sortable">', html)]
    if len(tbl) < 2:
        raise RuntimeError("퍽 테이블(survivor/killer)을 찾지 못함 — 위키 구조 변경?")
    surv_start, kill_start = tbl[0], tbl[1]
    kill_end = next(t for t in allt if t > kill_start)

    rows = []
    # 아이콘 파일명은 'IconPerks_'/'IconsPerks_' 또는 접두사 붙은 'T_UI_iconsPerks_'
    # (최신 퍽들) 등 다양 → 'icon(s)Perks_' 코어를 포함하는 파일명을 모두 잡는다.
    for m in re.finditer(r'<a href="/wiki/File:(\w*?[Ii]cons?[Pp]erks_[^."]+\.png)"[^>]*class="image"[^>]*>', html):
        pos = m.start()
        if pos < surv_start or pos > kill_end:
            continue
        icon = m.group(1)
        low = icon.lower()
        if low.endswith('_old.png') or '_originalicon' in low:
            continue  # 옛 아이콘 갤러리 등 노이즈
        role = 'survivor' if pos < kill_start else 'killer'
        win = html[m.end():m.end() + 900]
        lk = re.search(r'<th>\s*<a href="(/wiki/[^"]+)"[^>]*>(.*?)</a>', win, re.S)
        link = lk.group(1) if lk else ''
        name = htmllib.unescape(re.sub(r'<[^>]+>', '', lk.group(2))).strip() if lk else ''
        td_pos = html.find('<td', m.end() + (lk.end() if lk else 0))
        raw = balanced_td(html, td_pos)
        inner = re.sub(r'^<td[^>]*>', '', raw)
        inner = re.sub(r'</td>\s*$', '', inner)
        rows.append({'role': role, 'name': name, 'link': link, 'icon': icon, 'desc_raw': inner})

    # "Identical to <link>" → 참조 일반퍽의 설명으로 치환
    by_link = {r['link']: r for r in rows if r['link']}
    ident = re.compile(r'^\s*Identical to\s*<a href="(/wiki/[^"]+)"')
    for r in rows:
        r['desc_src'] = r['desc_raw']
        mm = ident.match(r['desc_raw'])
        if mm:
            ref = by_link.get(mm.group(1))
            if ref and not ident.match(ref['desc_raw']) and ref['desc_raw'].strip():
                r['desc_src'] = ref['desc_raw']
                r['identical_to'] = ref['name']
    return rows


# ───────────────────────── 설명 정제 ─────────────────────────
def _map_clr(classattr):
    toks = classattr.split()
    if 'clr9' in toks or 'clrbeige' in toks:
        return 'FlavorText'
    if 'clr2' in toks:
        return 'Highlight1'
    if 'clr3' in toks:
        return 'Highlight2'
    if 'clr4' in toks:
        return 'Highlight3'
    if 'clryellow' in toks or 'clr6' in toks or 'clr1' in toks:
        return 'Highlight1'
    return None  # rarity/label 등 그 외 색은 색 강조 없이 통과


class _Cleaner(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out, self.stack, self.skip = [], [], 0

    def handle_starttag(self, tag, attrs):
        if self.skip:
            self.skip += 1; return
        cls = dict(attrs).get('class', '')
        if 'iconLink' in cls:
            self.skip = 1; return
        if tag == 'span':
            if 'luaClr' in cls:
                m = _map_clr(cls)
                if m:
                    self.out.append(f'<span class="{m}">'); self.stack.append('</span>')
                else:
                    self.stack.append('')
            else:
                self.stack.append('')
        elif tag in ('b', 'strong'):
            self.out.append('<b>'); self.stack.append('</b>')
        elif tag in ('i', 'em'):
            self.out.append('<i>'); self.stack.append('</i>')
        elif tag == 'p':
            self.stack.append('<br><br>')
        elif tag == 'li':
            self.out.append('<br>• '); self.stack.append('')
        elif tag == 'br':
            self.out.append('<br>')
        else:
            self.stack.append('')  # a / ul / 기타 태그는 투명(텍스트만 유지)

    def handle_startendtag(self, tag, attrs):
        if not self.skip and tag == 'br':
            self.out.append('<br>')

    def handle_endtag(self, tag):
        if self.skip:
            self.skip -= 1; return
        if tag == 'br':
            return
        if self.stack:
            self.out.append(self.stack.pop())

    def handle_data(self, data):
        if not self.skip:
            self.out.append(data)


def clean_html(raw):
    c = _Cleaner(); c.feed(raw)
    s = ''.join(c.out).replace('\xa0', ' ')
    s = re.sub(r'[ \t]+', ' ', s)
    s = re.sub(r'\s*<br>\s*', '<br>', s)
    s = re.sub(r'(<br>){3,}', '<br><br>', s)
    s = re.sub(r'^(<br>)+', '', s)
    s = re.sub(r'(<br>)+$', '', s)
    s = re.sub(r'<b>\s*</b>', '', s)
    s = re.sub(r'<i>\s*</i>', '', s)
    return s.strip()


def to_text(html):
    t = re.sub(r'<br>', ' ', html)
    t = re.sub(r'<[^>]+>', '', t).replace('•', '')
    return re.sub(r'\s+', ' ', t).strip()


# ───────────────────────── 매칭 키 ─────────────────────────
def ikey(fn):
    b = urllib.parse.unquote(fn.split('/')[-1]).rsplit('.', 1)[0].lower()
    m = re.search(r'icons?perks?_(.+)$', b)
    core = m.group(1) if m else b
    return re.sub(r'[^a-z0-9]', '', core)


def nkey(s):
    return re.sub(r'[^a-z0-9]', '', htmllib.unescape(s or '').lower())


# ───────────────────────── 아이콘 ─────────────────────────
def save_icon_webp(wiki_name, dest_rel):
    """위키 원본 PNG → webp 로 변환해 dest_rel(레포 상대경로) 에 저장."""
    data = fetch(f"{BASE}/images/{wiki_name}")
    im = Image.open(io.BytesIO(data))
    if im.mode not in ('RGB', 'RGBA'):
        im = im.convert('RGBA')
    dest = os.path.join(HERE, dest_rel.replace('/', os.sep))
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    im.save(dest, 'WEBP', quality=90, method=6)


# ───────────────────────── 메인 ─────────────────────────
def main():
    sys.stderr.write("Fetching wiki Perks page...\n")
    api = (BASE + "/api.php?action=parse&page=Perks&prop=text&format=json")
    html = json.loads(fetch(api).decode('utf-8', 'replace'))['parse']['text']['*']
    rows = parse_rows(html)
    real = [r for r in rows if r['name']]
    sys.stderr.write(f"  parsed {len(real)} perk rows "
                     f"({sum(r['role']=='survivor' for r in real)} surv / "
                     f"{sum(r['role']=='killer' for r in real)} kill)\n")

    # 이름 우선 매칭(역할 인지) → 아이콘키 폴백.
    # 이름이 퍽의 정체성을 가장 잘 나타낸다. 일부 퍽은 우리 데이터의 아이콘
    # 파일명이 잘못(예: Teamwork 두 퍽이 뒤바뀜) 저장돼 있어 아이콘 우선 매칭은
    # 설명을 엇갈리게 한다. 개명된 일반퍽(소유 퍽)은 이름 매칭이 "Identical to"
    # 가 있는 소유 행을 잡아 자기참조 치환까지 올바르게 동작한다.
    nidx, iidx, n_any, i_any = {}, {}, {}, {}
    for r in real:
        nidx.setdefault((r['role'], nkey(r['name'])), r)
        iidx.setdefault((r['role'], ikey(r['icon'])), r)
        n_any.setdefault(nkey(r['name']), r)
        i_any.setdefault(ikey(r['icon']), r)

    def match(p):
        role, nk, ik = p['role'], nkey(p['name_en']), ikey(p['icon_file'])
        return (nidx.get((role, nk))                      # 1) 같은 역할·이름
                or iidx.get((role, ik))                   # 2) 같은 역할·아이콘
                or nidx.get((role, ALIAS.get(nk, '')))    # 3) 영국식 철자 등 별칭
                or nidx.get((role, ID_OVERRIDE.get(p['id'], '')))  # 4) 예외
                or n_any.get(nk) or i_any.get(ik))        # 5) 역할 무시 폴백

    no_icons = '--no-icons' in sys.argv
    pending_updates = pending_perk_updates()
    perks = json.load(open(os.path.join(HERE, "perks.json"), encoding='utf-8'))
    n_desc = n_icon = n_pending = 0
    icon_fail, unmatched, upcoming, promoted = [], [], [], []
    seen_rows = set()
    for p in perks:
        r = match(p)
        if not r:
            unmatched.append(p)
            continue
        seen_rows.add(id(r))
        # 설명 갱신
        h = clean_html(r['desc_src'])
        if r.get('identical_to'):
            h = h.replace(r['identical_to'], r['name'])  # 일반퍽명 → 소유퍽명
        ptb = PTB_BANNER.search(h)
        if ptb:
            h = PTB_BANNER.sub('', h).strip()   # 안내 문구는 설명에서 걷어낸다
        # 예정 표시 — 출시일이 지나면(또는 위키가 안내 문구를 떼면) 해제.
        # 두 종류를 구분한다:
        #   new    = 아직 안 나온 챕터의 퍽 자체가 출시 예정   → 앱에서 "출시 예정"
        #   update = 이미 있는 퍽의 설명이 바뀔 예정(PTB 배너) → 앱에서 "업데이트 예정"
        # 날짜는 위키 Release Dates 표를 먼저 보고, 아직 TBA 면 PATCH_DATES 를 쓴다.
        owner_patch = UPCOMING_OWNERS.get(p.get('owner_en'))
        patch, kind = ((owner_patch, 'new') if owner_patch else
                       (pending_updates[p['id']], 'update') if p['id'] in pending_updates else
                       (ptb.group(1), 'update') if ptb else (None, None))
        date = (patch_release_date(patch) or PATCH_DATES.get(patch)) if patch else None
        if patch and is_upcoming(date):
            p['upcoming'] = True
            p['upcoming_kind'] = kind
            p['upcoming_patch'] = patch
            p['upcoming_date'] = date
            if kind == 'update':
                # 기존 퍽이 바뀌는 경우: 본문은 **라이브 설명**을 그대로 두고,
                # 위키가 주는 예정 설명은 pending 에만 담는다. 앱이 출시일부터
                # pending 을 본문으로 쓰고, 그전까지는 라이브를 보여준다.
                pend = p.setdefault('pending', {})
                pend['desc_html_en'] = h
                pend['desc_text_en'] = to_text(h)
                pend.setdefault('desc_html', '')   # 한글 예정 설명은 손번역
                pend.setdefault('desc_text', '')
                n_pending += 1
            else:
                p['desc_html_en'] = h              # 신규 퍽은 라이브 설명이 따로 없다
                p['desc_text_en'] = to_text(h)
                n_desc += 1
            upcoming.append((p, patch, date, kind))
        else:
            # 패치가 나갔거나(출시일 지남) 위키가 예정 표시를 뗐다 → 예정본을 본문으로 승격
            pend = p.pop('pending', None)
            if pend:
                for f in ('desc_html', 'desc_text'):
                    if pend.get(f):
                        p[f] = pend[f]             # 손번역해 둔 한글 예정본
                p['search_blob'] = f"{p['name']} {p['owner']} {p['desc_text']}"
                promoted.append(p)
            p['desc_html_en'] = h                  # 영어는 위키 최신본이 곧 라이브
            p['desc_text_en'] = to_text(h)
            n_desc += 1
            for k in ('upcoming', 'upcoming_kind', 'upcoming_patch', 'upcoming_date'):
                p.pop(k, None)
        # 예전 방식(날짜 출처 표시)에서 남은 키 정리 — 이제 날짜는 PATCH_DATES 로 관리한다
        for k in ('upcoming_date_source', 'upcoming_date_estimated'):
            p.pop(k, None)
        # 아이콘 갱신(기존 경로에 덮어쓰기)
        if not no_icons:
            try:
                save_icon_webp(r['icon'], p['icon_file'])
                n_icon += 1
            except Exception as e:  # noqa
                icon_fail.append((p['name_en'], r['icon'], repr(e)[:60]))
        sys.stderr.write(f"  [{n_desc:3}] {p['role']:8} {p['name_en']}\n")

    # perks.json 에 없는 위키 퍽 = 신규 챕터 퍽 또는 아직 안 적어둔 개명 일반퍽.
    # 라이선스 만료로 생기는 일반퍽 쌍은 former_names_en 에 적어 두면 검색이 함께 잡는다.
    known_alt = {nkey(f) for p in perks for f in (p.get('former_names_en') or [])}
    new_rows = [r for r in real if id(r) not in seen_rows]
    new_perks = [r for r in new_rows if nkey(r['name']) not in known_alt]
    known_twins = [r for r in new_rows if nkey(r['name']) in known_alt]

    # 저장 (라운드트립 동일 포맷 — 변경 라인만 diff)
    with open(os.path.join(HERE, "perks.json"), "w", encoding='utf-8') as f:
        json.dump(perks, f, ensure_ascii=False, indent=1)

    sys.stderr.write(
        f"\nDone. desc updated={n_desc}, pending(예정본만 갱신)={n_pending}, "
        f"promoted(예정→본문)={len(promoted)}, icons updated={n_icon}, "
        f"icon_fail={len(icon_fail)}, unmatched(위키에 없음/유지)={len(unmatched)}, "
        f"upcoming(예정 표시)={len(upcoming)}, wiki-only(신규 후보)={len(new_perks)}\n")
    for p in promoted:
        sys.stderr.write(f"  PROMOTE {p['role']:8} {p['name_en']!r} — 패치가 나갔으니 "
                         f"예정 설명을 본문으로 올렸습니다\n")
    for p in unmatched:
        sys.stderr.write(f"  KEEP  {p['role']:8} {p['name_en']!r} (id={p['id']})\n")
    if upcoming:
        sys.stderr.write("  ※ 예정 설명의 영어는 자동 갱신됩니다. '한글 예정본 없음' 으로 표시된 퍽은 "
                         "pending.desc_html 을 손으로 채워 주세요(비어 있으면 앱이 라이브 설명을 씁니다).\n")
    for p, patch, date, kind in upcoming:
        label = "출시 예정" if kind == 'new' else "업데이트 예정"
        need_ko = kind == 'update' and not (p.get('pending') or {}).get('desc_html')
        sys.stderr.write(f"  UP    {p['role']:8} {p['name_en']!r} — {patch} {label} "
                         f"({date + ' 예정' if date else '출시일 미정(TBA)'})"
                         f"{' · 한글 예정본 없음' if need_ko else ''}\n")
    for r in new_perks:
        sys.stderr.write(f"  NEW   {r['role']:8} {r['name']!r} icon={r['icon']} "
                         f"— perks.json 에 없음(수동 추가 + 한글 번역 필요)\n")
    for r in known_twins:
        sys.stderr.write(f"  TWIN  {r['role']:8} {r['name']!r} — 개명 일반퍽, "
                         f"former_names_en 으로 커버됨\n")
    for nm, ic, err in icon_fail:
        sys.stderr.write(f"  ICONFAIL {nm!r} {ic} {err}\n")


if __name__ == "__main__":
    main()
