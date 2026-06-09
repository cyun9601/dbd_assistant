# -*- coding: utf-8 -*-
"""
DBD 어시스턴트 로컬 서버.
- 정적 파일(index.html, perks_data.js, icons/ ...)을 제공
- POST /ask    : 역할(살인마/생존자)별 퍽 전체를 LLM 컨텍스트에 넣고(프롬프트 캐싱) 질문과 매칭
- GET/POST /config : API 키를 웹 UI 에서 입력·저장 (DPAPI 암호화, 브라우저로 평문 노출 안 됨)

공급자는 모델 이름으로 구분: claude-* → Anthropic, 그 외 → OpenAI.
키 우선순위: 환경변수 → 저장된 config(secrets_store). 어느 쪽도 브라우저로 노출되지 않는다.
usage: python server.py (개발) · app.py (네이티브 창) · exe (배포)
"""
import json
import os
import posixpath
import socket
import sys
import threading
import urllib.request
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

import download_model as dm
import paths
import secrets_store
from version import __version__ as APP_VERSION

# 읽기 전용 번들 자산(index.html, perks.json, icons/ …)과 쓰기 가능한 사용자 데이터
# (즐겨찾기·사용자 태그·다운로드 모델)를 분리. 개발 모드에선 둘 다 레포 폴더.
BUNDLE = paths.bundle_dir()
DATA = paths.data_dir()
PORT = 8777

# 허용 모델 (프론트 드롭다운과 일치)
ALLOWED_MODELS = {
    "claude-opus-4-8": "Opus 4.8",
    "claude-haiku-4-5": "Haiku 4.5",
    "gpt-4.1": "GPT-4.1",
    "gpt-4.1-mini": "GPT-4.1 mini",
    "gpt-4o": "GPT-4o",
    "gpt-4o-mini": "GPT-4o mini",
}
DEFAULT_MODEL = "claude-opus-4-8"


def provider_of(model):
    return "anthropic" if model.startswith("claude") else "openai"


# 공급자별 SDK 패키지명 (미설치 시 안내 메시지에 사용)
PROVIDER_PKG = {"anthropic": "anthropic", "openai": "openai"}

# 퍽 데이터 로드 (서버 측) — 역할(살인마/생존자)별로 분리
with open(os.path.join(BUNDLE, "perks.json"), encoding="utf-8") as f:
    PERKS = json.load(f)
PERK_BY_ID = {p["id"]: p for p in PERKS}

ROLE_WORD = {"killer": "살인마", "survivor": "생존자"}
DEFAULT_ROLE = "killer"
PERKS_BY_ROLE = {
    role: [p for p in PERKS if p.get("role", "killer") == role]
    for role in ROLE_WORD
}

# ---- 즐겨찾기 (사용자별 로컬 파일, .gitignore 처리됨) ----
FAV_PATH = os.path.join(DATA, "favorites.json")
_fav_lock = threading.Lock()


def load_favorites():
    """favorites.json 에서 퍽 id 목록을 읽는다. 없거나 깨졌으면 빈 목록."""
    try:
        with open(FAV_PATH, encoding="utf-8") as f:
            data = json.load(f)
    except (FileNotFoundError, ValueError):
        return []
    ids = data.get("favorites", []) if isinstance(data, dict) else data
    # 실제 존재하는 퍽 id 만 유지 (데이터 갱신으로 사라진 id 정리)
    return [i for i in ids if i in PERK_BY_ID]


def save_favorites(ids):
    with open(FAV_PATH, "w", encoding="utf-8") as f:
        json.dump({"favorites": ids}, f, ensure_ascii=False, indent=1)


# ---- 태그 ----
# 기본 태그는 tags.json(레포에 포함, 공유). 사용자가 수정한 분량만 tags_user.json
# (.gitignore 처리)에 따로 저장하고, 조회 시 둘을 병합해 "유효 태그"를 만든다.
TAGS_BASE_PATH = os.path.join(BUNDLE, "tags.json")     # 공유 기본 태그 (읽기 전용 번들)
TAGS_USER_PATH = os.path.join(DATA, "tags_user.json")  # 사용자 수정분 (쓰기)
MAX_TAGS_PER_PERK = 8
_tags_lock = threading.Lock()


def _load_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, ValueError):
        return default


def _split_tags_doc(doc):
    """{tags:[...], perks:{id:[...]}} 문서를 (어휘, 퍽맵)으로."""
    if not isinstance(doc, dict):
        return [], {}
    vocab = doc.get("tags") if isinstance(doc.get("tags"), list) else []
    perks = doc.get("perks") if isinstance(doc.get("perks"), dict) else {}
    return vocab, perks


def save_user_tags(vocab_extra, perks_override):
    with open(TAGS_USER_PATH, "w", encoding="utf-8") as f:
        json.dump({"tags": vocab_extra, "perks": perks_override},
                  f, ensure_ascii=False, indent=1)


def effective_tags():
    """기본 + 사용자 오버라이드 병합. (어휘, 퍽맵, 오버라이드된 id목록) 반환."""
    base_vocab, base_perks = _split_tags_doc(_load_json(TAGS_BASE_PATH, {}))
    user_vocab, user_perks = _split_tags_doc(_load_json(TAGS_USER_PATH, {}))

    perks, overridden = {}, []
    for pid in PERK_BY_ID:                       # 실제 존재하는 퍽만
        if pid in user_perks and isinstance(user_perks[pid], list):
            perks[pid] = list(user_perks[pid])   # 사용자 오버라이드 우선
            overridden.append(pid)
        elif pid in base_perks:
            perks[pid] = list(base_perks[pid])

    # 어휘 순서: 기본 → 사용자 추가 → 실제 사용된 것 (중복 제거)
    vocab = list(base_vocab)
    for src in (user_vocab, *perks.values()):
        for t in src:
            if t not in vocab:
                vocab.append(t)
    return vocab, perks, overridden


def update_user_tag(pid, tags=None, reset=False):
    """사용자 오버라이드 갱신(또는 reset 시 제거)하고 저장. 락 안에서 호출."""
    user_vocab, user_perks = _split_tags_doc(_load_json(TAGS_USER_PATH, {}))
    base_vocab, _ = _split_tags_doc(_load_json(TAGS_BASE_PATH, {}))

    if reset:
        user_perks.pop(pid, None)
    else:
        clean = []
        for t in (tags or []):
            if isinstance(t, str):
                t = t.strip()
                if t and t not in clean:
                    clean.append(t)
        user_perks[pid] = clean[:MAX_TAGS_PER_PERK]

    # 기본 어휘에 없는데 실제 쓰이는 사용자 정의 태그만 user_vocab에 유지
    used = set()
    for v in user_perks.values():
        used.update(v)
    user_vocab = [t for t in dict.fromkeys(user_vocab) if t not in base_vocab and t in used]
    for t in used:
        if t not in base_vocab and t not in user_vocab:
            user_vocab.append(t)

    save_user_tags(user_vocab, user_perks)


def build_instructions(role):
    word = ROLE_WORD[role]
    return (
        f"당신은 데드 바이 데이라이트(DBD) {word} 퍽 검색 도우미입니다.\n"
        "사용자는 게임 중 겪은 현상이나 퍽 효과를 한국어로(때로는 모호하게) 설명합니다.\n"
        f"아래 {word} 퍽 목록에서 가장 가능성 높은 퍽들을 찾아 순위대로 반환하세요.\n\n"
        "규칙:\n"
        "- 질문이 퍽 이름의 일부와 겹치면 그 퍽을 최우선 포함하세요.\n"
        "- 사용자가 돌려 말하거나 줄임말/구어체를 써도 의미를 추론해 매칭하세요.\n"
        "- '태그'는 사용자가 그 퍽에 직접 붙여 둔 키워드입니다. 질문이 태그와 맞으면 강하게 매칭하세요.\n"
        "- 관련 있는 퍽만 포함하세요. 억지로 채우지 마세요.\n"
        "- confidence는 0~100 사이 정수 (확신도).\n"
        "- reason은 왜 매칭되는지 한국어 한 줄로 간결하게.\n"
        "- id는 반드시 아래 목록의 id를 그대로 사용하세요.\n\n"
        f"[{word} 퍽 목록]  형식: id | 이름 | 소유자 | 태그 | 효과  (태그 없으면 '-')\n"
    )


def build_corpus(role, tag_perks):
    lines = []
    for p in PERKS_BY_ROLE[role]:
        owner = "공용" if p["owner"] == "public" else p["owner"]
        tags = tag_perks.get(p["id"]) or []
        tag_str = ", ".join(tags) if tags else "-"
        lines.append(f"{p['id']} | {p['name']} | {owner} | {tag_str} | {p['desc_text']}")
    return build_instructions(role) + "\n".join(lines)


# 역할별 코퍼스 (각각 프롬프트 캐싱 대상). 사용자 태그가 바뀌면 rebuild_corpus() 로 갱신.
CORPUS = {}


def rebuild_corpus():
    """현재 유효 태그(기본+사용자 오버라이드)를 반영해 역할별 코퍼스를 다시 만든다.
    태그 편집(/tags) 후 호출 → 다음 /ask 부터 새 태그가 프롬프트에 반영된다.
    (코퍼스 텍스트가 바뀌면 프롬프트 캐시는 1회 미스 후 재캐싱되므로 안전)"""
    _, tag_perks, _ = effective_tags()
    for role in ROLE_WORD:
        CORPUS[role] = build_corpus(role, tag_perks)


rebuild_corpus()  # 시작 시 1회 생성

OUTPUT_SCHEMA = {
    "type": "json_schema",
    "schema": {
        "type": "object",
        "properties": {
            "results": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "confidence": {"type": "integer"},
                        "reason": {"type": "string"},
                    },
                    "required": ["id", "confidence", "reason"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["results"],
        "additionalProperties": False,
    },
}

# 공급자별 (api_key, client) 캐시 — 키가 바뀌면 새 클라이언트로 교체(서버 재시작 불필요).
_clients = {}


def _client(provider, key):
    cached = _clients.get(provider)
    if cached and cached[0] == key:
        return cached[1]
    if provider == "anthropic":
        import anthropic  # 지연 임포트: 미설치 시 친절한 에러
        client = anthropic.Anthropic(api_key=key)
    else:
        from openai import OpenAI  # 지연 임포트
        client = OpenAI(api_key=key)
    _clients[provider] = (key, client)
    return client


def _ask_anthropic(query, model, role, key):
    client = _client("anthropic", key)

    # 역할별 퍽 코퍼스는 system 에 두고 캐싱 → 매 질문마다 캐시 읽기(원가 0.1배)
    system = [{"type": "text", "text": CORPUS[role], "cache_control": {"type": "ephemeral"}}]
    kwargs = dict(
        model=model,
        max_tokens=2048,
        system=system,
        messages=[{"role": "user", "content": query}],
        output_config={"format": OUTPUT_SCHEMA},
    )
    # Opus 4.x 는 적응형 사고 사용 (Haiku 4.5 는 미지원이라 생략)
    if model.startswith("claude-opus"):
        kwargs["thinking"] = {"type": "adaptive"}

    resp = client.messages.create(**kwargs)
    text = next((b.text for b in resp.content if b.type == "text"), "{}")
    u = resp.usage
    usage = {
        "input": getattr(u, "input_tokens", 0),
        "cache_read": getattr(u, "cache_read_input_tokens", 0),
        "cache_write": getattr(u, "cache_creation_input_tokens", 0),
        "output": getattr(u, "output_tokens", 0),
    }
    return json.loads(text), usage


def _ask_openai(query, model, role, key):
    client = _client("openai", key)

    # OpenAI 는 1024토큰 이상 프롬프트를 자동 캐싱(별도 설정 불필요).
    resp = client.chat.completions.create(
        model=model,
        max_completion_tokens=2048,
        messages=[
            {"role": "system", "content": CORPUS[role]},
            {"role": "user", "content": query},
        ],
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "perk_matches",
                "strict": True,
                "schema": OUTPUT_SCHEMA["schema"],
            },
        },
    )
    text = resp.choices[0].message.content or "{}"
    u = resp.usage
    cached = 0
    details = getattr(u, "prompt_tokens_details", None)
    if details is not None:
        cached = getattr(details, "cached_tokens", 0) or 0
    usage = {
        "input": getattr(u, "prompt_tokens", 0),
        "cache_read": cached,
        "cache_write": 0,
        "output": getattr(u, "completion_tokens", 0),
    }
    return json.loads(text), usage


def ask_llm(query, model, role, key):
    """질문을 LLM에 보내고 매칭된 퍽 결과를 반환."""
    if provider_of(model) == "anthropic":
        data, usage = _ask_anthropic(query, model, role, key)
    else:
        data, usage = _ask_openai(query, model, role, key)

    # id → 퍽 정보 매핑. 모르는 id, 또는 요청한 역할이 아닌 퍽은 버림(방어)
    out = []
    for r in data.get("results", []):
        perk = PERK_BY_ID.get(r.get("id"))
        if not perk or perk.get("role", "killer") != role:
            continue
        out.append({
            "perk": perk,
            "confidence": r.get("confidence", 0),
            "reason": r.get("reason", ""),
        })
    out.sort(key=lambda x: x["confidence"], reverse=True)
    return {"results": out, "usage": usage, "model": model, "role": role}


# ---- 의미기반 모델 자동 다운로드 (첫 사용 시 1회) ----
_dl = {"status": "idle", "index": 0, "count": 0, "file": "", "pct": 0, "error": None}
_dl_lock = threading.Lock()


def _run_download():
    def on_file(i, n, name):
        _dl.update(index=i, count=n, file=name, pct=0)

    def on_progress(read, total):
        _dl["pct"] = (read * 100 // total) if total else 0

    try:
        dm.download_all(on_file, on_progress)
        _dl.update(status="done", pct=100)
    except Exception as e:  # noqa
        _dl.update(status="error", error=str(e))


def start_download():
    """누락 모델/라이브러리를 백그라운드로 받기 시작 (이미 진행 중이면 무시)."""
    with _dl_lock:
        if _dl["status"] == "running":
            return
        _dl.update(status="running", index=0, count=len(dm.missing()),
                   file="", pct=0, error=None)
        threading.Thread(target=_run_download, daemon=True).start()


# ---- 업데이트 확인 (GitHub Releases) ----
# 앱 시작 시 1회 GitHub 에 최신 릴리스 태그를 물어보고 현재 버전과 비교한다.
# 결과는 캐시해 두고 프론트는 /update_check 로 즉시 읽어 배너를 띄운다.
# 네트워크 호출은 백그라운드 스레드 1회뿐 — 오프라인/레이트리밋은 조용히 무시한다.
GITHUB_REPO = "cyun9601/dbd_assistant"
RELEASES_API = f"https://api.github.com/repos/{GITHUB_REPO}/releases?per_page=20"
RELEASES_PAGE = f"https://github.com/{GITHUB_REPO}/releases"

_update = {
    "checked": False,            # GitHub 응답을 받아봤는지 (성공/실패 무관)
    "current": APP_VERSION,
    "latest": None,              # 최신 릴리스 태그 (예: "0.1.2")
    "update_available": False,
    "html_url": RELEASES_PAGE,   # "업데이트" 버튼이 열 페이지
    "error": None,
}
_update_lock = threading.Lock()


def _parse_version(tag):
    """'v0.1.1' / '0.1.1-beta' → (0, 1, 1). 숫자 버전이 아니면 None."""
    if not tag:
        return None
    core = tag.lstrip("vV").strip().split("-", 1)[0].split("+", 1)[0]
    try:
        nums = tuple(int(p) for p in core.split("."))
    except ValueError:
        return None
    return nums or None


def _is_newer(latest, current):
    """latest 가 current 보다 높은 버전이면 True (자리수 차이는 0 패딩)."""
    a, b = _parse_version(latest), _parse_version(current)
    if a is None or b is None:
        return False
    n = max(len(a), len(b))
    a += (0,) * (n - len(a))
    b += (0,) * (n - len(b))
    return a > b


def _fetch_latest_release():
    """드래프트를 제외한(프리릴리스 포함) 릴리스 중 가장 높은 버전의 (태그, 페이지URL)."""
    req = urllib.request.Request(RELEASES_API, headers={
        "User-Agent": f"dbd-assistant/{APP_VERSION}",   # GitHub 은 UA 없으면 403
        "Accept": "application/vnd.github+json",
    })
    with urllib.request.urlopen(req, timeout=4) as resp:
        releases = json.loads(resp.read().decode("utf-8"))

    best_ver = best_tag = best_url = None
    for rel in releases:
        if rel.get("draft"):
            continue
        ver = _parse_version(rel.get("tag_name"))
        if ver is None:
            continue
        if best_ver is None or ver > best_ver:
            best_ver, best_tag = ver, rel.get("tag_name")
            best_url = rel.get("html_url") or RELEASES_PAGE
    return best_tag, best_url


def _run_update_check():
    try:
        latest, url = _fetch_latest_release()
        with _update_lock:
            _update["latest"] = latest
            _update["html_url"] = url or RELEASES_PAGE
            _update["update_available"] = _is_newer(latest, APP_VERSION)
            _update["checked"] = True
    except Exception as e:  # noqa — 오프라인/레이트리밋/타임아웃 등은 무시
        with _update_lock:
            _update["error"] = str(e)
            _update["checked"] = True


def start_update_check():
    """업데이트 확인을 백그라운드로 시작 (서버를 점유한 프로세스에서 1회)."""
    threading.Thread(target=_run_update_check, daemon=True).start()


class Handler(SimpleHTTPRequestHandler):
    # 로컬 모델/라이브러리 제공에 필요한 MIME 타입 보강
    extensions_map = {
        **SimpleHTTPRequestHandler.extensions_map,
        ".mjs": "text/javascript",
        ".js": "text/javascript",
        ".wasm": "application/wasm",
        ".json": "application/json",
        ".onnx": "application/octet-stream",
    }

    def __init__(self, *a, **kw):
        super().__init__(*a, directory=BUNDLE, **kw)

    def log_message(self, fmt, *args):  # 조용히
        pass

    def translate_path(self, path):
        # 다운로드 모델/라이브러리는 쓰기 가능한 데이터 폴더(DATA)에 있다.
        # 그 외 정적 자산은 번들(BUNDLE)에서 제공. 개발 모드에선 둘이 같은 폴더.
        clean = posixpath.normpath(path.split("?", 1)[0].split("#", 1)[0])
        if clean.startswith(("/models/", "/vendor/")) or clean in ("/models", "/vendor"):
            full = os.path.normpath(os.path.join(DATA, *clean.lstrip("/").split("/")))
            base = os.path.normpath(DATA)
            if full == base or full.startswith(base + os.sep):
                return full
        return super().translate_path(path)

    def do_GET(self):
        path = self.path.split("?")[0].rstrip("/")
        if path == "/config":
            self._send_json(200, {"providers": secrets_store.status()})
            return
        if path == "/model_status":
            self._send_json(200, {
                "ready": dm.all_present(),
                "status": _dl["status"],
                "index": _dl["index"],
                "count": _dl["count"],
                "file": _dl["file"],
                "pct": _dl["pct"],
                "error": _dl["error"],
            })
            return
        if path == "/update_check":
            with _update_lock:
                self._send_json(200, dict(_update))
            return
        if path == "/favorites":
            self._send_json(200, {"favorites": load_favorites()})
            return
        if path == "/tags":
            vocab, perks, overridden = effective_tags()
            self._send_json(200, {"tags": vocab, "perks": perks, "overridden": overridden})
            return
        super().do_GET()

    def _send_json(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        path = self.path.rstrip("/")
        if path == "/ensure_model":
            # 의미기반 모델/라이브러리가 없으면 백그라운드 다운로드 시작
            if not dm.all_present():
                start_download()
            self._send_json(200, {"ready": dm.all_present(), "status": _dl["status"]})
            return
        if path == "/open_release":
            # 캐시된 릴리스 페이지를 시스템 기본 브라우저로 연다(프론트 입력 URL 안 받음 → 안전).
            # 네이티브 창(pywebview)에서도 외부 브라우저로 확실히 열기 위해 서버 측에서 처리.
            import webbrowser
            with _update_lock:
                url = _update.get("html_url") or RELEASES_PAGE
            try:
                opened = webbrowser.open(url)
            except Exception:  # noqa
                opened = False
            self._send_json(200, {"opened": opened, "url": url})
            return
        if path == "/config":
            # API 키 저장/삭제: {"provider": "anthropic"|"openai", "key": "..."}
            #   key 가 빈 문자열이거나 {"clear": true} 면 삭제.
            # 평문 키는 응답에 절대 포함하지 않고, 갱신된 상태(마스킹)만 돌려준다.
            try:
                length = int(self.headers.get("Content-Length", 0))
                payload = json.loads(self.rfile.read(length) or b"{}")
            except Exception as e:  # noqa
                self._send_json(400, {"error": f"잘못된 요청: {e}"})
                return
            provider = payload.get("provider")
            if provider not in secrets_store.PROVIDERS:
                self._send_json(400, {"error": "알 수 없는 공급자"})
                return
            if payload.get("clear"):
                secrets_store.clear_key(provider)
            else:
                secrets_store.save_key(provider, payload.get("key", ""))
            self._send_json(200, {"providers": secrets_store.status()})
            return
        if path == "/favorites":
            # 즐겨찾기 토글: {"id": "...", "on": true/false}
            # 또는 전체 설정: {"favorites": ["id1", "id2", ...]}
            try:
                length = int(self.headers.get("Content-Length", 0))
                payload = json.loads(self.rfile.read(length) or b"{}")
            except Exception as e:  # noqa
                self._send_json(400, {"error": f"잘못된 요청: {e}"})
                return
            with _fav_lock:
                favs = load_favorites()
                if isinstance(payload.get("favorites"), list):
                    favs = [i for i in payload["favorites"] if i in PERK_BY_ID]
                else:
                    pid = payload.get("id")
                    if pid in PERK_BY_ID:
                        if payload.get("on") and pid not in favs:
                            favs.append(pid)
                        elif not payload.get("on") and pid in favs:
                            favs.remove(pid)
                save_favorites(favs)
            self._send_json(200, {"favorites": favs})
            return
        if path == "/tags":
            # 한 퍽의 태그 설정: {"id": "...", "tags": [...]} 또는 {"id": "...", "reset": true}
            try:
                length = int(self.headers.get("Content-Length", 0))
                payload = json.loads(self.rfile.read(length) or b"{}")
            except Exception as e:  # noqa
                self._send_json(400, {"error": f"잘못된 요청: {e}"})
                return
            pid = payload.get("id")
            if pid not in PERK_BY_ID:
                self._send_json(400, {"error": "알 수 없는 퍽 id"})
                return
            with _tags_lock:
                update_user_tag(pid, tags=payload.get("tags"),
                                reset=bool(payload.get("reset")))
                vocab, perks, overridden = effective_tags()
                rebuild_corpus()  # 새 태그를 LLM 검색 프롬프트에 즉시 반영
            self._send_json(200, {
                "id": pid,
                "tags": perks.get(pid, []),
                "vocab": vocab,
                "overridden": pid in set(overridden),
            })
            return
        if path != "/ask":
            self.send_error(404)
            return
        try:
            length = int(self.headers.get("Content-Length", 0))
            payload = json.loads(self.rfile.read(length) or b"{}")
        except Exception as e:  # noqa
            self._send_json(400, {"error": f"잘못된 요청: {e}"})
            return

        query = (payload.get("query") or "").strip()
        model = payload.get("model") or DEFAULT_MODEL
        if model not in ALLOWED_MODELS:
            model = DEFAULT_MODEL
        role = payload.get("role") or DEFAULT_ROLE
        if role not in CORPUS:
            role = DEFAULT_ROLE
        if not query:
            self._send_json(400, {"error": "질문이 비어 있습니다."})
            return

        provider = provider_of(model)
        key = secrets_store.get_key(provider)
        if not key:
            name = "Anthropic" if provider == "anthropic" else "OpenAI"
            self._send_json(503, {
                "error": f"{name} API 키가 없습니다. 우측 상단 ⚙️ 설정에서 키를 입력하세요.",
                "code": "no_key",
                "provider": provider,
            })
            return

        try:
            result = ask_llm(query, model, role, key)
            self._send_json(200, result)
        except ModuleNotFoundError:
            pkg = PROVIDER_PKG[provider]
            self._send_json(503, {
                "error": f"{pkg} 패키지가 없습니다. 'pip install {pkg}' 후 다시 실행하세요.",
                "code": "no_sdk",
            })
        except Exception as e:  # noqa
            self._send_json(500, {"error": f"LLM 호출 실패: {e}"})


class Server(ThreadingHTTPServer):
    # 기본값(allow_reuse_address=True)은 Windows에서 SO_REUSEADDR 때문에 이미 떠 있는
    # 서버와 같은 포트를 "공유"하게 만든다 → 옛 서버가 요청을 가로채 구버전으로 응답하는
    # 혼란이 생긴다. 단독 점유로 바꿔, 중복 실행 시 조용히 공유하지 않고 명확히 실패하게 한다.
    allow_reuse_address = False

    def server_bind(self):
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):   # Windows
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


URL = f"http://localhost:{PORT}/index.html"


def create_server():
    """포트를 점유해 서버 객체를 만든다. 이미 떠 있으면(포트 사용 중) None."""
    try:
        return Server(("127.0.0.1", PORT), Handler)
    except OSError:
        return None


def serve(server):
    """서버를 블로킹으로 구동 (Ctrl+C / 종료 시 빠져나옴)."""
    start_update_check()   # 시작 시 1회 GitHub 최신 릴리스 확인 (백그라운드)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


def main():
    os.chdir(BUNDLE)
    server = create_server()
    if server is None:
        sys.stderr.write(
            f"포트 {PORT} 를 열 수 없습니다. 이미 다른 DBD 서버가 실행 중인 것 같습니다.\n"
            f"  - 브라우저에서 {URL} 를 새로고침하거나,\n"
            f"  - 기존 서버 창을 닫은(Ctrl+C) 뒤 다시 실행하세요.\n")
        return
    st = secrets_store.status()
    fmt = lambda p: ("설정됨 ✓ (" + ("환경변수" if p["source"] == "env" else "저장됨") + ")") \
        if p["set"] else "미설정"  # noqa: E731
    sys.stderr.write(f"DBD 어시스턴트 v{APP_VERSION}: {URL}\n")
    sys.stderr.write(f"  Anthropic: {fmt(st['anthropic'])}   OpenAI: {fmt(st['openai'])}\n")
    sys.stderr.write("  (AI 정밀 검색 모드는 선택한 모델의 공급자 키만 필요 · 웹 ⚙️ 설정에서 입력)\n")
    sys.stderr.write("  종료: Ctrl+C\n")
    serve(server)


if __name__ == "__main__":
    main()
