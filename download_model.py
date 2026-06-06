# -*- coding: utf-8 -*-
"""
'의미 기반 AI' 모드를 완전 오프라인으로 돌리기 위한 1회성 다운로드.
- 임베딩 모델(multilingual-e5-small, ONNX) → models/
- transformers.js 라이브러리 + ONNX 런타임 wasm → vendor/transformers/

한 번 받아두면 이후엔 인터넷 없이도 의미 기반 검색이 동작한다.
usage: python download_model.py
"""
import os
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
UA = {"User-Agent": "Mozilla/5.0"}

HF_BASE = "https://huggingface.co/Xenova/multilingual-e5-small/resolve/main/"
JSDELIVR = "https://cdn.jsdelivr.net/npm/@huggingface/transformers@3.3.3/dist/"

MODEL_DIR = os.path.join(HERE, "models", "Xenova", "multilingual-e5-small")
VENDOR_DIR = os.path.join(HERE, "vendor", "transformers")

# (원격경로, 저장경로)
MODEL_FILES = [
    "config.json",
    "tokenizer.json",
    "tokenizer_config.json",
    "special_tokens_map.json",
    "onnx/model_quantized.onnx",   # q8 양자화본 (~30MB)
]
LIB_FILES = [
    "transformers.min.js",            # 브라우저용 ESM 빌드 (fs/path 미사용)
    "ort-wasm-simd-threaded.jsep.mjs",
    "ort-wasm-simd-threaded.jsep.wasm",
]


def fetch(url, dest):
    if os.path.exists(dest) and os.path.getsize(dest) > 0:
        sys.stderr.write(f"  skip (있음): {os.path.relpath(dest, HERE)}\n")
        return
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    sys.stderr.write(f"  받는 중: {url}\n")
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=120) as r, open(dest, "wb") as f:
        total = int(r.headers.get("Content-Length", 0))
        read = 0
        while True:
            chunk = r.read(1 << 16)
            if not chunk:
                break
            f.write(chunk)
            read += len(chunk)
            if total:
                pct = read * 100 // total
                sys.stderr.write(f"\r    {pct}%  ({read//1024}/{total//1024} KB)")
                sys.stderr.flush()
        sys.stderr.write("\n")


def main():
    sys.stderr.write("모델 파일 다운로드 → models/\n")
    for rel in MODEL_FILES:
        fetch(HF_BASE + rel, os.path.join(MODEL_DIR, *rel.split("/")))
    sys.stderr.write("라이브러리 다운로드 → vendor/transformers/\n")
    for rel in LIB_FILES:
        fetch(JSDELIVR + rel, os.path.join(VENDOR_DIR, rel))
    sys.stderr.write("완료. 이제 의미 기반 AI 모드가 로컬에서 동작합니다.\n")


if __name__ == "__main__":
    main()
