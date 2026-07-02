# -*- coding: utf-8 -*-
"""killers.json / addons.json 의 영어 필드(*_en)를 한국어로 번역해 빈 한글 필드를 채운다.

- 위키 파이프라인(update_killers_from_wiki.py)은 영어만 채운다. 이 스크립트가 그 영어를
  LLM(Anthropic/OpenAI)으로 번역해 name/real_name/power_name/overview_html·text/
  power_html·text/desc_html·text 를 채운다(퍽의 수동 한글 번역을 자동화한 것).
- HTML 태그(<b><i><br>, Highlight/FlavorText span, 불릿 •)는 그대로 두고 텍스트만 번역한다.
- 이미 채워진 한글 필드는 건드리지 않는다(--force 로 덮어쓰기). → 재실행 시 이어서 번역.
- _text 는 번역한 _html 에서 태그를 벗겨 파생한다(중복 번역 방지).
- 번역 후 search_blob 을 한/영 합쳐 다시 굽는다(추후 도감 검색이 퍽처럼 언어 반영되게).

키: server.py 와 동일하게 secrets_store → 환경변수 순. 모델로 공급자 구분(claude*→Anthropic).

usage:
  python translate_killers.py                     # 빈 한글 필드 전체 번역(기본 모델)
  python translate_killers.py --model gpt-4.1     # 모델 지정
  python translate_killers.py --only killers      # 살인마만 (또는 addons)
  python translate_killers.py --limit 3           # 앞 N개만 (샘플/검증용)
  python translate_killers.py --ids The_Trapper The_Nurse
  python translate_killers.py --force             # 이미 채워진 한글도 다시 번역
"""
import argparse, json, os, re, sys

import secrets_store

HERE = os.path.dirname(os.path.abspath(__file__))

DEFAULT_MODEL = "gpt-4.1"

# DBD 한국어 용어집 — 기존 perks.json 한글 번역과 일관되도록 주요 용어를 고정한다.
GLOSSARY = """\
[핵심 용어] (반드시 이 번역어를 사용)
Killer=살인마, Survivor=생존자, Perk=퍽, The Trial/Trial=시련, Trial Grounds=시련장,
Aura=오라, Obsession=집착 대상, Terror Radius=공포 범위, Status Effect=상태 효과,
Basic Attack=기본 공격, Special Attack=특수 공격, cooldown=재사용 대기시간, Token=토큰,
Generator=발전기, Pallet=판자, Vault=넘어가기, Window=창문, Hook=갈고리, Locker=로커,
Totem=토템, Hex=저주, Dull Totem=무효 토템, Bloodpoints=블러드포인트,
Injured=부상, Healthy=건강, Dying State=빈사 상태, Downed=쓰러진, Chase=추격, Stun=기절,
Scratch Marks=긁힌 자국, charge=충전, meter/gauge=게이지, Endurance=인내,
[상태 효과] Haste=신속, Hindered=둔화, Exposed=노출, Undetectable=은신, Oblivious=무지,
Incapacitated=무력화, Broken=상처, Deep Wound=깊은 상처, Hemorrhage=출혈, Mangled=손상,
Blindness=실명, Exhausted=탈진, Mending=붕대 감기, Bloodlust=블러드러스트,
[살인마 공식 한글명 예] The Trapper=트래퍼, The Wraith=레이스, The Hillbilly=힐빌리,
The Nurse=널스, The Huntress=헌트리스, The Shape=셰이프, The Doctor=닥터, The Hag=마녀,
The Spirit=스피릿, The Legion=리전, The Plague=플레이그, The Nightmare=나이트메어,
The Pig=피그, The Clown=클라운, The Oni=오니, The Blight=블라이트."""

SYSTEM = (
    "당신은 비대칭 공포 게임 Dead by Daylight(데드 바이 데이라이트)의 한국어 로컬라이제이션 "
    "전문가입니다. 살인마·애드온의 영어 원문을 자연스러운 한국어로 번역합니다.\n\n"
    "규칙:\n"
    "1) HTML 태그(<b>, <i>, <br>, <span class=\"Highlight1\">, class=\"FlavorText\" 등)와 "
    "불릿 기호 '•' 는 위치·개수를 원문과 동일하게 그대로 유지하고, 태그 안의 텍스트만 번역합니다. "
    "class 이름이나 태그 이름은 절대 번역/변경하지 않습니다. 태그를 새로 추가하거나 삭제하지 말고, "
    "특히 <br> 줄바꿈과 Highlight span 은 원문과 같은 개수를 유지하세요.\n"
    "2) 숫자·퍼센트·초 단위 값은 그대로 둡니다 (예: 16 metres → 16미터, 5 seconds → 5초).\n"
    "3) 아래 용어집의 번역어를 반드시 그대로 사용해 기존 게임 번역과 일관성을 지킵니다.\n"
    "4) name 은 게임 내 공식 한글 명칭, real_name 은 인물명 한글 표기(예: Evan MacMillan→에반 맥밀런), "
    "power_name 은 파워의 한글 명칭입니다.\n"
    "5) 문체는 게임 내 설명체(간결한 서술)로 합니다. 과한 의역·설명 추가 금지.\n"
    "6) 반드시 입력의 각 항목 id 를 그대로 유지해 같은 개수·순서로 반환합니다.\n\n"
    + GLOSSARY
)

KILLER_FIELDS = [
    ("name", "name_en"), ("power_name", "power_name_en"),
    ("overview_html", "overview_html_en"), ("power_html", "power_html_en"),
]
ADDON_FIELDS = [("name", "name_en"), ("desc_html", "desc_html_en")]


def strip_html(t):
    t = re.sub(r"<br\s*/?>", " ", t or "")
    t = re.sub(r"<[^>]+>", "", t).replace("•", "")
    return re.sub(r"\s+", " ", t).strip()


# ───────────────────────── LLM 호출 ─────────────────────────
def provider_of(model):
    return "anthropic" if model.startswith("claude") else "openai"


def make_client(provider, key):
    if provider == "anthropic":
        import anthropic
        return anthropic.Anthropic(api_key=key)
    from openai import OpenAI
    return OpenAI(api_key=key)


def _schema(item_props):
    item = {"type": "object",
            "properties": {k: {"type": "string"} for k in item_props},
            "required": list(item_props), "additionalProperties": False}
    return {"type": "object",
            "properties": {"items": {"type": "array", "items": item}},
            "required": ["items"], "additionalProperties": False}


def call_llm(client, provider, model, user, schema):
    if provider == "anthropic":
        resp = client.messages.create(
            model=model, max_tokens=16000,
            system=[{"type": "text", "text": SYSTEM}],
            messages=[{"role": "user", "content": user}],
            output_config={"format": {"type": "json_schema", "schema": schema}})
        text = next((b.text for b in resp.content if b.type == "text"), "{}")
    else:
        resp = client.chat.completions.create(
            model=model, max_completion_tokens=16000,
            messages=[{"role": "system", "content": SYSTEM},
                      {"role": "user", "content": user}],
            response_format={"type": "json_schema",
                             "json_schema": {"name": "translation", "strict": True,
                                             "schema": schema}})
        text = resp.choices[0].message.content or "{}"
    return json.loads(text)


# ───────────────────────── 번역 (적응형 배치) ─────────────────────────
def translate_batch(client, provider, model, records, src_fields, schema):
    """records(원본 dict 목록)의 영어 필드를 번역해 {id: {ko필드: 값}} 반환.
    파싱 실패·개수 불일치 시 배치를 반으로 쪼개 재시도(트렁케이션 방어)."""
    payload = []
    for r in records:
        item = {"id": r["id"]}
        for ko, en in src_fields:
            item[ko] = r.get(en, "") or ""
        payload.append(item)
    user = ("다음 항목들을 번역해 같은 형식(JSON)으로 반환하세요. 각 항목의 id 는 그대로.\n"
            + json.dumps(payload, ensure_ascii=False))
    try:
        out = call_llm(client, provider, model, user, schema)
        items = out.get("items", [])
        by_id = {it["id"]: it for it in items if "id" in it}
        if all(r["id"] in by_id for r in records):
            return by_id
        raise ValueError(f"id 누락 (got {len(by_id)}/{len(records)})")
    except Exception as e:  # noqa
        if len(records) == 1:
            sys.stderr.write(f"    ! 번역 실패 {records[0]['id']}: {repr(e)[:80]}\n")
            return {}
        mid = len(records) // 2
        sys.stderr.write(f"    · 배치 분할 재시도 ({len(records)} → {mid}+{len(records)-mid})\n")
        res = {}
        res.update(translate_batch(client, provider, model, records[:mid], src_fields, schema))
        res.update(translate_batch(client, provider, model, records[mid:], src_fields, schema))
        return res


def needs(rec, fields, force):
    return [en for ko, en in fields
            if (rec.get(en) or "").strip() and (force or not (rec.get(ko) or "").strip())]


def apply_translation(rec, tr, fields, force):
    """번역 결과를 레코드에 반영. 빈 한글 필드만(또는 force) 채우고 _text 파생."""
    for ko, en in fields:
        if not (force or not (rec.get(ko) or "").strip()):
            continue
        val = (tr.get(ko) or "").strip()
        if not val:
            continue
        rec[ko] = val
        if ko.endswith("_html"):                     # _text 는 태그 벗겨 파생
            rec[ko[:-5] + "_text"] = strip_html(val)


def rebuild_killer_blob(k):
    k["search_blob"] = " ".join(filter(None, [
        k.get("name"), k.get("name_en"),
        k.get("power_name"), k.get("power_name_en"),
        k.get("overview_text"), k.get("overview_text_en"),
        k.get("power_text"), k.get("power_text_en")]))


def rebuild_addon_blob(a):
    a["search_blob"] = " ".join(filter(None, [
        a.get("name"), a.get("name_en"), a.get("desc_text"), a.get("desc_text_en")]))


def run(kind, records, fields, schema, client, provider, model, batch, force, save):
    todo = [r for r in records if needs(r, fields, force)]
    if not todo:
        sys.stderr.write(f"{kind}: 번역할 빈 필드 없음\n")
        return
    sys.stderr.write(f"{kind}: {len(todo)}/{len(records)} 항목 번역 (batch={batch}, model={model})\n")
    done = 0
    for i in range(0, len(todo), batch):
        chunk = todo[i:i + batch]
        by_id = translate_batch(client, provider, model, chunk, fields, schema)
        for r in chunk:
            tr = by_id.get(r["id"])
            if tr:
                apply_translation(r, tr, fields, force)
                (rebuild_killer_blob if kind == "killers" else rebuild_addon_blob)(r)
                done += 1
        save()   # 배치마다 저장 — 중단돼도 진행분 보존
        sys.stderr.write(f"  {min(i + batch, len(todo))}/{len(todo)} "
                         f"(예: {chunk[0]['id']} → {chunk[0].get('name', '')!r})\n")
    sys.stderr.write(f"{kind}: 완료 {done}/{len(todo)}\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--only", choices=["killers", "addons"])
    ap.add_argument("--limit", type=int)
    ap.add_argument("--ids", nargs="*")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--kbatch", type=int, default=3)   # 살인마 배치(파워 설명이 길어 작게)
    ap.add_argument("--abatch", type=int, default=20)  # 애드온 배치
    args = ap.parse_args()

    provider = provider_of(args.model)
    key = secrets_store.get_key(provider)
    if not key:
        sys.stderr.write(f"{provider} API 키가 없습니다. 환경변수나 앱 설정에 키를 넣으세요.\n")
        sys.exit(1)
    client = make_client(provider, key)

    kpath = os.path.join(HERE, "killers.json")
    apath = os.path.join(HERE, "addons.json")
    killers = json.load(open(kpath, encoding="utf-8"))
    addons = json.load(open(apath, encoding="utf-8"))

    def save_k():
        json.dump(killers, open(kpath, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    def save_a():
        json.dump(addons, open(apath, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    ksel = killers
    asel = addons
    if args.ids:
        ids = set(args.ids)
        ksel = [k for k in killers if k["id"] in ids]
        asel = [a for a in addons if a["killer_id"] in ids or a["id"] in ids]
    if args.limit:
        ksel = ksel[:args.limit]
        asel = asel[:args.limit]

    kschema = _schema([ko for ko, _ in KILLER_FIELDS] + ["id"])
    aschema = _schema([ko for ko, _ in ADDON_FIELDS] + ["id"])

    if args.only != "addons":
        run("killers", ksel, KILLER_FIELDS, kschema, client, provider, args.model,
            args.kbatch, args.force, save_k)
    if args.only != "killers":
        run("addons", asel, ADDON_FIELDS, aschema, client, provider, args.model,
            args.abatch, args.force, save_a)
    sys.stderr.write("Done.\n")


if __name__ == "__main__":
    main()
