# -*- coding: utf-8 -*-
"""nightlight.gg 에서 퍽 사용률(pick rate)을 가져온다.

두 가지 용도:
- 런타임(server.py): fetch_usage() — 안정적인 공개 API
  GET /api/v1/stats/global/{killer|survivor}-perks 만 호출한다.
  각 퍽의 nightlight 숫자 id → 사용률(pct)·표본수를 돌려준다.
  이 숫자 id 는 사이트 배포와 무관하게 고정이라, 우리 퍽에 한 번 구워둔
  nl_id(=build_data 가 매핑) 로 그대로 join 하면 된다.
- 빌드(build_data.py): fetch_perk_dict() — slug↔숫자id 매핑 사전.
  이 사전은 해시된 JS 청크 안에 임베드돼 있어 파일명이 배포마다 바뀐다.
  그래서 /perks 페이지 → perks 라우트 모듈 → import 청크들을 따라가며
  '퍽 사전처럼 생긴' JSON.parse(...) 블록을 찾아 추출한다(빌드 시 1회).

외부 의존성 없음(urllib 만 사용) — exe 번들에 그대로 들어간다.
"""
import json
import re
import urllib.request

BASE = "https://nightlight.gg"
# Cloudflare 가 UA 없는 요청을 403 으로 막으므로 브라우저 UA 를 보낸다.
UA = {"User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                     "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")}


def _get(url, timeout=20):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


# ---- 런타임용: 사용률 (안정 API) -------------------------------------------

def fetch_usage(timeout=20):
    """역할별 사용률을 반환.

    {"killer":  {"perks": {nl_id(str): {"pct":float, "count":int, "rate":float}},
                 "start": iso, "end": iso, "latest": iso},
     "survivor": {...}}
    rate 는 killer=kill_rate, survivor=escape_rate.
    """
    out = {}
    for role in ("killer", "survivor"):
        d = json.loads(_get(f"{BASE}/api/v1/stats/global/{role}-perks", timeout))["data"]
        rate_key = "kill_rate" if role == "killer" else "escape_rate"
        perks = {
            str(p["id"]): {
                "pct": p.get("pct", 0),
                "count": p.get("count", 0),
                "rate": p.get(rate_key, 0),
            }
            for p in d.get("perks", [])
        }
        out[role] = {
            "perks": perks,
            "start": d.get("start"),
            "end": d.get("end"),
            "latest": d.get("latest_queryable_day"),
        }
    return out


# ---- 빌드용: slug ↔ 숫자id 사전 (JS 청크에서 추출) -------------------------

_CTRL = {"n": "\n", "r": "\r", "t": "\t", "b": "\b", "f": "\f", "v": "\v", "0": "\0"}


def _eval_template(r):
    """JS 템플릿 리터럴 escape 를 실제 문자열(=유효 JSON)로 평가.
    minify 된 사전이 \\xA0 같은 hex escape 를 쓰므로 \\u·\\x 까지 처리해야 한다."""
    out = []
    k, n = 0, len(r)
    while k < n:
        c = r[k]
        if c != "\\":
            out.append(c)
            k += 1
            continue
        nx = r[k + 1]
        if nx == "x":
            out.append(chr(int(r[k + 2:k + 4], 16)))
            k += 4
        elif nx == "u":
            if r[k + 2] == "{":
                e = r.index("}", k + 2)
                out.append(chr(int(r[k + 3:e], 16)))
                k = e + 1
            else:
                out.append(chr(int(r[k + 2:k + 6], 16)))
                k += 6
        elif nx in _CTRL:
            out.append(_CTRL[nx])
            k += 2
        else:                       # ` $ \ / " ' 또는 기타 → 백슬래시 제거 후 그 문자
            out.append(nx)
            k += 2
    return "".join(out)


def _perkdict_from_js(js):
    """JS 소스에서 '퍽 사전처럼 생긴' JSON.parse(`...`) 블록을 찾아 파싱."""
    for m in re.finditer(r"=JSON\.parse\(`", js):
        i = m.end()
        try:
            j = js.index("`", i)
            obj = json.loads(_eval_template(js[i:j]))
        except Exception:           # noqa — 다른 JSON.parse 블록일 수 있음
            continue
        sample = next(iter(obj.values()), None)
        if isinstance(sample, dict) and "/perks/" in str(sample.get("u", "")):
            return obj
    return None


def fetch_perk_dict(timeout=20):
    """{nl_id(str): {"n":영문명, "i":slug, "u":url, "t":tier, ...}} 반환.

    /perks 페이지 → perks 라우트 모듈 → 그 모듈이 import 하는 청크들을 훑어
    퍽 사전 블록을 찾는다. 사이트 구조가 바뀌면 RuntimeError.
    """
    page = _get(f"{BASE}/perks", timeout)
    mod_paths = re.findall(r'/assets/perks\._?[A-Za-z0-9._-]+\.js', page)
    seen, queue = set(), list(dict.fromkeys(mod_paths))
    # 라우트 모듈이 import 하는 청크들까지 따라간다(퍽 사전은 보통 공용 청크에 있음).
    for path in list(queue):
        try:
            mod = _get(BASE + path, timeout)
        except Exception:           # noqa
            continue
        for c in re.findall(r'from"\./(chunk-[A-Za-z0-9._-]+\.js)"', mod):
            p = "/assets/" + c
            if p not in queue:
                queue.append(p)
    for path in queue:
        if path in seen:
            continue
        seen.add(path)
        try:
            js = _get(BASE + path, timeout)
        except Exception:           # noqa
            continue
        d = _perkdict_from_js(js)
        if d:
            return d
    raise RuntimeError("nightlight 퍽 사전을 찾지 못했습니다 (사이트 구조 변경?)")


def slug_index(perk_dict):
    """퍽 사전에서 매핑 인덱스 (정확 slug, 정규화 fallback) 두 개를 만든다."""
    def norm(s):
        return re.sub(r"[^a-z0-9]", "", s.lower())

    by_slug, by_norm = {}, {}
    for nid, e in perk_dict.items():
        by_slug[e.get("i", "")] = nid
        for key in (e.get("i", ""), e.get("n", ""), e.get("u", "").split("/perks/")[-1]):
            if key:
                by_norm.setdefault(norm(key), nid)
    return by_slug, by_norm


if __name__ == "__main__":   # 간단 점검: python nightlight.py
    import sys
    pd = fetch_perk_dict()
    us = fetch_usage()
    sys.stderr.write(f"perk_dict {len(pd)} entries; "
                     f"killer {len(us['killer']['perks'])}, "
                     f"survivor {len(us['survivor']['perks'])} usage rows\n")
