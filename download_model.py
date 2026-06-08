# -*- coding: utf-8 -*-
"""
'의미 기반 AI' 모드용 1회성 다운로드 (모델 + transformers.js 라이브러리/wasm).
- 임베딩 모델(multilingual-e5-small, ONNX) → models/
- transformers.js 브라우저 빌드 + ONNX 런타임 wasm → vendor/transformers/

직접 실행하거나(`python download_model.py`), server.py 가 첫 사용 시 자동 호출한다.
한 번 받아두면 이후엔 인터넷 없이도 의미 기반 검색이 동작한다.
"""
import os
import sys
import urllib.request

import paths

UA = {"User-Agent": "Mozilla/5.0"}

HF_BASE = "https://huggingface.co/Xenova/multilingual-e5-small/resolve/main/"
JSDELIVR = "https://cdn.jsdelivr.net/npm/@huggingface/transformers@3.3.3/dist/"

# 다운로드 대상은 쓰기 가능한 데이터 폴더(개발=레포, exe=%APPDATA%\dbd-assistant).
# 서버의 /models, /vendor 정적 라우팅도 같은 폴더를 가리킨다.
MODEL_DIR = os.path.join(paths.data_dir(), "models", "Xenova", "multilingual-e5-small")
VENDOR_DIR = os.path.join(paths.data_dir(), "vendor", "transformers")

MODEL_FILES = [
    "config.json",
    "tokenizer.json",
    "tokenizer_config.json",
    "special_tokens_map.json",
    "onnx/model_quantized.onnx",   # q8 양자화본 (~113MB)
]
LIB_FILES = [
    "transformers.min.js",            # 브라우저용 ESM 빌드
    "ort-wasm-simd-threaded.jsep.mjs",
    "ort-wasm-simd-threaded.jsep.wasm",
]


def _targets():
    """(원격 url, 로컬 저장경로) 전체 목록."""
    out = []
    for rel in MODEL_FILES:
        out.append((HF_BASE + rel, os.path.join(MODEL_DIR, *rel.split("/"))))
    for rel in LIB_FILES:
        out.append((JSDELIVR + rel, os.path.join(VENDOR_DIR, rel)))
    return out


def _present(dest):
    return os.path.exists(dest) and os.path.getsize(dest) > 0


def missing():
    """아직 받지 않은 파일들의 (url, dest) 목록."""
    return [(u, d) for (u, d) in _targets() if not _present(d)]


def all_present():
    return not missing()


def fetch(url, dest, progress=None):
    """url → dest 다운로드. progress(read_bytes, total_bytes) 콜백 선택."""
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    tmp = dest + ".part"
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=120) as r, open(tmp, "wb") as f:
        total = int(r.headers.get("Content-Length", 0))
        read = 0
        while True:
            chunk = r.read(1 << 16)
            if not chunk:
                break
            f.write(chunk)
            read += len(chunk)
            if progress:
                progress(read, total)
    os.replace(tmp, dest)


def download_all(on_file=None, on_progress=None):
    """누락 파일을 모두 다운로드.
    on_file(index, count, name) / on_progress(read, total) 콜백 선택."""
    todo = missing()
    n = len(todo)
    for i, (url, dest) in enumerate(todo):
        name = os.path.basename(dest)
        if on_file:
            on_file(i + 1, n, name)
        fetch(url, dest, on_progress)
    return n


def main():
    todo = missing()
    if not todo:
        sys.stderr.write("이미 모두 받아져 있습니다.\n")
        return

    def on_file(i, n, name):
        sys.stderr.write(f"[{i}/{n}] {name}\n")

    def on_progress(read, total):
        if total:
            sys.stderr.write(f"\r    {read*100//total}% ({read//1024}/{total//1024} KB)")
            sys.stderr.flush()

    sys.stderr.write(f"다운로드 시작 ({len(todo)}개 파일)...\n")
    download_all(on_file, on_progress)
    sys.stderr.write("\n완료. 의미 기반 AI 모드가 로컬에서 동작합니다.\n")


if __name__ == "__main__":
    main()
