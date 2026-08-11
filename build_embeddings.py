# -*- coding: utf-8 -*-
"""'의미 기반 AI' 모드용 퍽 임베딩을 미리 구워 둔다 → embeddings/.

의미검색은 코퍼스(퍽 설명) 벡터와 질의 벡터의 코사인 유사도로 순위를 매긴다.
코퍼스 벡터는 퍽 데이터가 그대로면 **결과가 항상 같으므로** 앱이 켜질 때마다
브라우저에서 321개를 다시 임베딩할 이유가 없다. 여기서 한 번 구워 파일로 두면
프런트는 그냥 읽어 쓰고, 모델은 질의 한 줄을 임베딩할 때만 필요해진다.

프런트(index.html)의 `semanticPassage()` 와 **똑같은 규칙**으로 패시지를 만든다.
검색 프로파일 3종을 각각 굽는다:
  multi    — 한글 + 영어를 한 패시지에 (기본값)
  same-ko  — 한글만
  same-en  — 영어만

출력:
  embeddings/index.json   메타(모델·차원·퍽 id 순서·패시지 해시)
  embeddings/<프로파일>.bin  float32 리틀엔디언 행렬 (count × dim)

패시지 해시를 함께 저장하는 이유: 출시 예정 퍽은 출시일이 지나면 프런트가
`pending` 설명으로 갈아타므로(= 패시지가 바뀜) 구워 둔 벡터가 낡는다. 프런트는
해시를 대조해 바뀐 퍽만 그 자리에서 다시 임베딩한다 — 파일을 다시 굽지 않아도
틀린 벡터를 쓰지 않는다.

usage:
  python build_embeddings.py            # 3개 프로파일 전부
  python build_embeddings.py multi      # 특정 프로파일만

필요 패키지(빌드 전용, 앱 실행엔 불필요):  pip install onnxruntime tokenizers numpy
모델 파일은 download_model.py 가 받아 둔 것을 그대로 쓴다.
"""
import datetime
import json
import os
import sys

import numpy as np

import paths

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(HERE, "embeddings")

# index.html 과 반드시 같아야 하는 값들
MODEL_ID = "Xenova/multilingual-e5-small"
DTYPE = "q8"                       # transformers.js pipeline(..., {dtype: "q8"})
PROFILES = ("multi", "same-ko", "same-en")
MAX_LEN = 512
BATCH = 32

MODEL_DIR = os.path.join(paths.data_dir(), "models", *MODEL_ID.split("/"))
ONNX_PATH = os.path.join(MODEL_DIR, "onnx", "model_quantized.onnx")
TOKENIZER_PATH = os.path.join(MODEL_DIR, "tokenizer.json")


# ───────────────────────── 패시지 (index.html 과 동일 규칙) ─────────────────────────
def _today():
    return datetime.date.today().isoformat()


def _pending_active(p, today):
    """출시일이 지난 '업데이트 예정' 퍽은 pending 설명이 본문이 된다 (프런트 eff()와 동일)."""
    if not (p.get("pending") and p.get("upcoming")):
        return False
    d = p.get("upcoming_date")
    return bool(d and d <= today)      # 출시일이 지났으면 pending 이 활성


def _eff(p, today):
    if not _pending_active(p, today):
        return p
    q = dict(p)
    for f in ("desc_html", "desc_text", "desc_html_en", "desc_text_en"):
        if p["pending"].get(f):
            q[f] = p["pending"][f]
    return q


def _join(*parts):
    return " ".join(x for x in parts if x)


def passage(perk, profile, today):
    p = _eff(perk, today)
    aliases = " ".join(p.get("aliases") or [])
    kx = _join(aliases, " ".join(p.get("former_names") or []))
    ex = _join(aliases, " ".join(p.get("former_names_en") or []))
    ko = f"{p.get('name', '')}. {p.get('desc_text', '')}" + (f" {kx}" if kx else "")
    en = f"{p.get('name_en') or ''}. {p.get('desc_text_en') or ''}" + (f" {ex}" if ex else "")
    if profile == "multi":
        return f"passage: {ko} {en}"
    return f"passage: {en if profile == 'same-en' else ko}"


def passage_hash(s):
    """FNV-1a 32bit (UTF-8 바이트 기준). 프런트에도 같은 함수가 있다."""
    h = 0x811C9DC5
    for b in s.encode("utf-8"):
        h = ((h ^ b) * 0x01000193) & 0xFFFFFFFF
    return f"{h:08x}"


# ───────────────────────── 임베딩 ─────────────────────────
class Embedder:
    """transformers.js 의 feature-extraction 파이프라인과 같은 처리:
    토크나이즈(512 자름) → ONNX → attention mask 평균 풀링 → L2 정규화."""

    def __init__(self):
        import onnxruntime as ort
        from tokenizers import Tokenizer

        for f in (ONNX_PATH, TOKENIZER_PATH):
            if not os.path.exists(f):
                raise SystemExit(
                    f"모델 파일이 없습니다: {f}\n"
                    "먼저 `python download_model.py` 로 임베딩 모델을 받아 주세요.")

        self.tok = Tokenizer.from_file(TOKENIZER_PATH)
        self.tok.enable_truncation(max_length=MAX_LEN)
        with open(os.path.join(MODEL_DIR, "special_tokens_map.json"), encoding="utf-8") as f:
            pad = json.load(f).get("pad_token") or "<pad>"
        pad = pad["content"] if isinstance(pad, dict) else pad
        self.tok.enable_padding(pad_id=self.tok.token_to_id(pad), pad_token=pad)
        self.sess = ort.InferenceSession(ONNX_PATH,
                                         providers=["CPUExecutionProvider"])
        self.inputs = {i.name for i in self.sess.get_inputs()}

    def __call__(self, texts):
        enc = self.tok.encode_batch(list(texts))
        ids = np.array([e.ids for e in enc], dtype=np.int64)
        mask = np.array([e.attention_mask for e in enc], dtype=np.int64)
        feed = {"input_ids": ids, "attention_mask": mask}
        if "token_type_ids" in self.inputs:
            feed["token_type_ids"] = np.zeros_like(ids)
        feed = {k: v for k, v in feed.items() if k in self.inputs}

        out = self.sess.run(None, feed)[0]                      # (B, T, H)
        m = mask.astype(np.float32)[..., None]
        pooled = (out * m).sum(axis=1) / np.clip(m.sum(axis=1), 1e-9, None)
        norm = np.linalg.norm(pooled, axis=1, keepdims=True)
        return (pooled / np.clip(norm, 1e-12, None)).astype(np.float32)


def embed_all(embed, passages):
    vecs = []
    for i in range(0, len(passages), BATCH):
        vecs.append(embed(passages[i:i + BATCH]))
        sys.stderr.write(f"\r    {min(i + BATCH, len(passages))}/{len(passages)}")
        sys.stderr.flush()
    sys.stderr.write("\n")
    return np.vstack(vecs)


# ───────────────────────── 메인 ─────────────────────────
def main(argv):
    want = [p for p in argv if p in PROFILES] or list(PROFILES)
    bad = [p for p in argv if p not in PROFILES]
    if bad:
        raise SystemExit(f"알 수 없는 프로파일: {bad} (가능: {', '.join(PROFILES)})")

    with open(os.path.join(HERE, "perks.json"), encoding="utf-8") as f:
        perks = json.load(f)
    today = _today()
    sys.stderr.write(f"퍽 {len(perks)}개 · 기준일 {today}\n")

    os.makedirs(OUT_DIR, exist_ok=True)
    meta_path = os.path.join(OUT_DIR, "index.json")
    try:
        with open(meta_path, encoding="utf-8") as f:
            meta = json.load(f)
    except (FileNotFoundError, ValueError):
        meta = {}

    embed = Embedder()
    sys.stderr.write(f"모델 로드 완료 (입력: {sorted(embed.inputs)})\n")

    profiles = meta.get("profiles", {}) if meta.get("model") == MODEL_ID else {}
    dim = None
    for prof in want:
        sys.stderr.write(f"  [{prof}] 임베딩…\n")
        passages = [passage(p, prof, today) for p in perks]
        matrix = embed_all(embed, passages)
        dim = matrix.shape[1]
        fname = f"{prof}.bin"
        with open(os.path.join(OUT_DIR, fname), "wb") as f:
            f.write(matrix.tobytes(order="C"))
        profiles[prof] = {
            "file": fname,
            "count": len(perks),
            "hashes": [passage_hash(s) for s in passages],
        }
        sys.stderr.write(f"    → embeddings/{fname} "
                         f"({matrix.shape[0]}×{matrix.shape[1]}, "
                         f"{matrix.nbytes / 1024:.0f} KB)\n")

    meta = {
        "model": MODEL_ID,
        "dtype": DTYPE,
        "dim": dim or meta.get("dim"),
        "built": today,
        "ids": [p["id"] for p in perks],
        "profiles": profiles,
    }
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=1)
    sys.stderr.write(f"Wrote {meta_path} (프로파일 {len(profiles)}개)\n")

    # 간단 자가검증 — 질의 하나를 임베딩해 상위 퍽이 말이 되는지 눈으로 확인.
    if "multi" in profiles and os.path.exists(os.path.join(OUT_DIR, "multi.bin")):
        n = profiles["multi"]["count"]
        raw = open(os.path.join(OUT_DIR, "multi.bin"), "rb").read()
        m = np.frombuffer(raw, dtype=np.float32).reshape(n, -1)
        q = embed(["query: 발전기 수리 속도를 올려주는 퍽"])[0]
        top = np.argsort(-(m @ q))[:5]
        sys.stderr.write("자가검증 — '발전기 수리 속도' 상위 5:\n")
        for i in top:
            sys.stderr.write(f"  {float(m[i] @ q):.3f}  {perks[i]['name']} "
                             f"({perks[i].get('role')})\n")


if __name__ == "__main__":
    main(sys.argv[1:])
