# -*- coding: utf-8 -*-
"""살인마/애드온 한글 번역을 청크로 나눠(split) 서브에이전트가 채운 결과를 병합(apply)한다.

OpenAI 대신 Claude(서브에이전트)로 직접 번역할 때 쓰는 오프라인 도구:
  1) split : 아직 한글이 빈 레코드의 영어 원문을 N개 청크 JSON 으로 <dir> 에 쓴다.
             각 청크 파일(src_*.json)은 [{id, ...영어필드}] 목록.
  2) apply : <dir> 의 번역 결과 파일(tr_*.json = [{id, ...한글필드}])을 읽어
             killers.json/addons.json 의 빈 한글 필드를 채우고(_text 파생·search_blob 재빌드),
             커버리지를 보고한다. 이미 채워진 필드는 건드리지 않는다(--force 로 덮어쓰기).

translate_killers.py 의 검증된 로직(strip_html·apply_translation·search_blob·필드정의)을 재사용.

usage:
  python ko_merge.py split --dir <chunkdir> [--kchunks 4] [--achunks 6]
  python ko_merge.py apply --dir <chunkdir> [--force]
"""
import argparse, glob, json, os, sys

from translate_killers import (
    KILLER_FIELDS, ADDON_FIELDS, apply_translation, needs,
    rebuild_killer_blob, rebuild_addon_blob,
)

HERE = os.path.dirname(os.path.abspath(__file__))
KPATH = os.path.join(HERE, "killers.json")
APATH = os.path.join(HERE, "addons.json")


def _load():
    return (json.load(open(KPATH, encoding="utf-8")),
            json.load(open(APATH, encoding="utf-8")))


def _chunks(seq, n):
    n = max(1, min(n, len(seq))) if seq else 0
    if not n:
        return []
    size = (len(seq) + n - 1) // n
    return [seq[i:i + size] for i in range(0, len(seq), size)]


def _src_item(rec, fields):
    it = {"id": rec["id"]}
    for ko, en in fields:
        it[ko] = rec.get(en, "") or ""   # 키는 목표 한글 필드명, 값은 영어 원문
    return it


def do_split(args):
    killers, addons = _load()
    os.makedirs(args.dir, exist_ok=True)
    ktodo = [k for k in killers if needs(k, KILLER_FIELDS, False)]
    atodo = [a for a in addons if needs(a, ADDON_FIELDS, False)]
    manifest = []
    for i, ch in enumerate(_chunks(ktodo, args.kchunks), 1):
        p = os.path.join(args.dir, f"src_killers_{i}.json")
        json.dump([_src_item(r, KILLER_FIELDS) for r in ch],
                  open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        manifest.append((p, os.path.join(args.dir, f"tr_killers_{i}.json"), len(ch), "killers"))
    for i, ch in enumerate(_chunks(atodo, args.achunks), 1):
        p = os.path.join(args.dir, f"src_addons_{i}.json")
        json.dump([_src_item(r, ADDON_FIELDS) for r in ch],
                  open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        manifest.append((p, os.path.join(args.dir, f"tr_addons_{i}.json"), len(ch), "addons"))
    sys.stderr.write(f"split: killers {len(ktodo)} → {len(_chunks(ktodo, args.kchunks))} chunks, "
                     f"addons {len(atodo)} → {len(_chunks(atodo, args.achunks))} chunks\n")
    for src, tr, n, kind in manifest:
        sys.stderr.write(f"  {kind:8} n={n:3}  src={src}  tr={tr}\n")


def _read_tr(dir, pattern):
    by_id = {}
    for p in sorted(glob.glob(os.path.join(dir, pattern))):
        try:
            for it in json.load(open(p, encoding="utf-8")):
                if isinstance(it, dict) and it.get("id"):
                    by_id[it["id"]] = it
        except Exception as e:  # noqa
            sys.stderr.write(f"  ! 읽기 실패 {p}: {repr(e)[:60]}\n")
    return by_id


def do_apply(args):
    killers, addons = _load()
    ktr = _read_tr(args.dir, "tr_killers_*.json")
    atr = _read_tr(args.dir, "tr_addons_*.json")

    kdone = 0
    for k in killers:
        tr = ktr.get(k["id"])
        if tr:
            apply_translation(k, tr, KILLER_FIELDS, args.force)
            rebuild_killer_blob(k)
            if k.get("name"):
                kdone += 1
    adone = 0
    for a in addons:
        tr = atr.get(a["id"])
        if tr:
            apply_translation(a, tr, ADDON_FIELDS, args.force)
            rebuild_addon_blob(a)
            if a.get("name"):
                adone += 1

    json.dump(killers, open(KPATH, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    json.dump(addons, open(APATH, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    kfilled = sum(1 for k in killers if k.get("name") and k.get("overview_html") and k.get("power_html"))
    afilled = sum(1 for a in addons if a.get("name") and a.get("desc_html"))
    sys.stderr.write(f"apply: translations found — killers {len(ktr)}, addons {len(atr)}\n")
    sys.stderr.write(f"apply: now filled — killers {kfilled}/{len(killers)}, addons {afilled}/{len(addons)}\n")
    missing_k = [k["id"] for k in killers if not (k.get("name") and k.get("overview_html") and k.get("power_html"))]
    missing_a = [a["id"] for a in addons if not (a.get("name") and a.get("desc_html"))]
    if missing_k:
        sys.stderr.write(f"  아직 빈 살인마({len(missing_k)}): {missing_k[:10]}\n")
    if missing_a:
        sys.stderr.write(f"  아직 빈 애드온({len(missing_a)}): {missing_a[:10]}\n")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sp = sub.add_parser("split"); sp.add_argument("--dir", required=True)
    sp.add_argument("--kchunks", type=int, default=4); sp.add_argument("--achunks", type=int, default=6)
    sp.set_defaults(fn=do_split)
    ap_ = sub.add_parser("apply"); ap_.add_argument("--dir", required=True)
    ap_.add_argument("--force", action="store_true"); ap_.set_defaults(fn=do_apply)
    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
