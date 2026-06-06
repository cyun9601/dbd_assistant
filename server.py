# -*- coding: utf-8 -*-
"""
DBD 퍽 검색기 로컬 서버.
- 정적 파일(index.html, perks_data.js, icons/ ...)을 제공
- POST /ask : 살인마 퍽 전체를 LLM 컨텍스트에 넣고(프롬프트 캐싱) 질문과 매칭

공급자는 모델 이름으로 구분: claude-* → Anthropic, 그 외 → OpenAI.
API 키는 각각 환경변수 ANTHROPIC_API_KEY / OPENAI_API_KEY 에서 읽는다 (브라우저로 노출 안 됨).
usage: python server.py  (또는 run.bat)
"""
import json
import os
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
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


# 공급자별 필요한 환경변수와 SDK 패키지
PROVIDER_KEY = {"anthropic": "ANTHROPIC_API_KEY", "openai": "OPENAI_API_KEY"}
PROVIDER_PKG = {"anthropic": "anthropic", "openai": "openai"}

# 살인마 퍽 데이터 로드 (서버 측)
with open(os.path.join(HERE, "perks.json"), encoding="utf-8") as f:
    PERKS = json.load(f)
PERK_BY_ID = {p["id"]: p for p in PERKS}

INSTRUCTIONS = (
    "당신은 데드 바이 데이라이트(DBD) 살인마 퍽 검색 도우미입니다.\n"
    "사용자는 게임 중 겪은 현상이나 퍽 효과를 한국어로(때로는 모호하게) 설명합니다.\n"
    "아래 살인마 퍽 목록에서 가장 가능성 높은 퍽들을 찾아 순위대로 반환하세요.\n\n"
    "규칙:\n"
    "- 사용자가 돌려 말하거나 줄임말/구어체를 써도 의미를 추론해 매칭하세요.\n"
    "- 관련 있는 퍽만 포함하세요. 보통 1~6개. 억지로 채우지 마세요.\n"
    "- confidence는 0~100 사이 정수 (확신도).\n"
    "- reason은 왜 매칭되는지 한국어 한 줄로 간결하게.\n"
    "- id는 반드시 아래 목록의 id를 그대로 사용하세요.\n\n"
    "[살인마 퍽 목록]  형식: id | 이름 | 소유자 | 효과\n"
)


def build_corpus():
    lines = []
    for p in PERKS:
        owner = "공용" if p["owner"] == "public" else p["owner"]
        lines.append(f"{p['id']} | {p['name']} | {owner} | {p['desc_text']}")
    return INSTRUCTIONS + "\n".join(lines)


CORPUS = build_corpus()

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

_clients = {}


def _ask_anthropic(query, model):
    import anthropic  # 지연 임포트: 미설치 시 친절한 에러
    client = _clients.get("anthropic") or _clients.setdefault("anthropic", anthropic.Anthropic())

    # 살인마 퍽 코퍼스는 system 에 두고 캐싱 → 매 질문마다 캐시 읽기(원가 0.1배)
    system = [{"type": "text", "text": CORPUS, "cache_control": {"type": "ephemeral"}}]
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


def _ask_openai(query, model):
    from openai import OpenAI  # 지연 임포트
    client = _clients.get("openai") or _clients.setdefault("openai", OpenAI())

    # OpenAI 는 1024토큰 이상 프롬프트를 자동 캐싱(별도 설정 불필요).
    resp = client.chat.completions.create(
        model=model,
        max_completion_tokens=2048,
        messages=[
            {"role": "system", "content": CORPUS},
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


def ask_llm(query, model):
    """질문을 LLM에 보내고 매칭된 퍽 결과를 반환."""
    if provider_of(model) == "anthropic":
        data, usage = _ask_anthropic(query, model)
    else:
        data, usage = _ask_openai(query, model)

    # id → 퍽 정보 매핑, 모르는 id 는 버림
    out = []
    for r in data.get("results", []):
        perk = PERK_BY_ID.get(r.get("id"))
        if not perk:
            continue
        out.append({
            "perk": perk,
            "confidence": r.get("confidence", 0),
            "reason": r.get("reason", ""),
        })
    out.sort(key=lambda x: x["confidence"], reverse=True)
    return {"results": out, "usage": usage, "model": model}


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
        super().__init__(*a, directory=HERE, **kw)

    def log_message(self, fmt, *args):  # 조용히
        pass

    def _send_json(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if self.path.rstrip("/") != "/ask":
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
        if not query:
            self._send_json(400, {"error": "질문이 비어 있습니다."})
            return

        provider = provider_of(model)
        key_env = PROVIDER_KEY[provider]
        if not os.environ.get(key_env):
            self._send_json(503, {
                "error": f"API 키가 없습니다. 환경변수 {key_env} 를 설정한 뒤 서버를 다시 실행하세요.",
                "code": "no_key",
            })
            return

        try:
            result = ask_llm(query, model)
            self._send_json(200, result)
        except ModuleNotFoundError:
            pkg = PROVIDER_PKG[provider]
            self._send_json(503, {
                "error": f"{pkg} 패키지가 없습니다. 'pip install {pkg}' 후 다시 실행하세요.",
                "code": "no_sdk",
            })
        except Exception as e:  # noqa
            self._send_json(500, {"error": f"LLM 호출 실패: {e}"})


def main():
    os.chdir(HERE)
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    a_ok = "설정됨 ✓" if os.environ.get("ANTHROPIC_API_KEY") else "미설정"
    o_ok = "설정됨 ✓" if os.environ.get("OPENAI_API_KEY") else "미설정"
    sys.stderr.write(f"DBD 퍽 검색기: http://localhost:{PORT}/index.html\n")
    sys.stderr.write(f"  ANTHROPIC_API_KEY: {a_ok}   OPENAI_API_KEY: {o_ok}\n")
    sys.stderr.write("  (AI 정밀 검색 모드는 선택한 모델의 공급자 키만 필요)\n")
    sys.stderr.write("  종료: Ctrl+C\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
