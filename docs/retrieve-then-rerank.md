# 설계 메모 — Retrieve-then-Rerank (LLM 정밀 검색 2단계화)

> 상태: **아이디어 / 미구현**. LLM 매칭 누락이 프롬프트·`max_tokens` 수정 후에도
> 남으면 검토할 다음 단계. 작성 2026-06-11.

## 배경 — 왜 이 메모가 있나

`/ask`(AI 정밀 검색)는 현재 역할별 퍽 **전체**(살인마 139 / 생존자 167개)를
system 코퍼스에 통째로 넣고 한 번에 매칭한다 — [server.py](../server.py) 의
`build_corpus()` / `_ask_anthropic()` / `_ask_openai()`.

"가끔 매칭이 몇 개 누락된다"는 증상에 대해, 먼저 적용한 두 가지(둘 다 적용 완료):

1. 프롬프트를 precision → **recall 우선**으로 변경 (`build_instructions`, "애매하면 낮은
   confidence로라도 포함").
2. `MAX_OUTPUT_TOKENS` 2048 → 8192 상향 + `stop_reason`/`finish_reason` 잘림 경고 로깅.

이걸로도 부족하면 — 즉 **단일 패스로 167개를 한 번에 훑는 것 자체가 한계**라고
판단되면 — 아래 retrieve-then-rerank로 간다. (배치로 코퍼스를 N등분하는 방식은
호출 N배·confidence 배치 간 정규화·전역 랭킹 상실 때문에 **비추천**.)

## 핵심 아이디어

검색을 2단계로 쪼갠다:

1. **후보 추출 (recall 단계, 싸고 빠름):** 질의와 의미적으로 가까운 퍽 **top-K개**
   (예: 40~60)만 추린다.
2. **재랭킹 (precision 단계, LLM):** 그 K개만 `/ask` 코퍼스로 넣어 LLM이
   confidence·reason 생성. 후보당 추론 여력이 커져 recall·precision 동시 개선,
   프롬프트도 작아져 빠르고 싸다.

## 이미 가진 것 — 재활용

이 앱엔 **"의미 기반 AI" 모드용 임베딩 모델이 이미 탑재**돼 있다:
`Xenova/multilingual-e5-small` (ONNX, 브라우저 transformers.js).
- 후보 추출 로직이 사실상 이미 구현돼 있음 → [index.html](../index.html) 의
  `semantic.rank(q)` (질의 임베딩 → 전체 퍽과 cosine → 점수순 정렬).
- 즉 1단계(후보 추출)에 **새 인프라가 거의 필요 없다.**

## 통합 방안 (권장: 클라이언트 후보 추출)

브라우저가 이미 임베딩 행렬과 질의 임베딩을 갖고 있으므로, 후보 추출을
**프론트에서** 하고 top-K id만 서버로 넘기는 게 추가 의존성이 가장 적다.

- **프론트** ([index.html](../index.html), `runLLM` 근처 — `/ask` POST 본문):
  - LLM 모드 진입 시 의미 모델이 준비돼 있으면 `semantic.rank(q)` 로 상위 K개
    퍽 id 추출.
  - **이름/부분문자열 키워드 매칭과 합집합**으로 보강 (임베딩이 놓치는 정확한
    이름 조각 보호).
  - `/ask` 본문에 `candidate_ids: [...]` 추가.
- **백엔드** ([server.py](../server.py), `do_POST`/`ask_llm`/`build_corpus`):
  - `/ask` 가 선택적 `candidate_ids` 를 받음.
  - `build_corpus()` 가 `PERKS_BY_ROLE[role]` 대신 그 id 집합만으로 코퍼스 구성.
  - `candidate_ids` 가 없으면(=의미 모델 미다운로드 등) 기존 전체-코퍼스 경로로 폴백.

> 서버 측 임베딩(onnxruntime 등)으로 옮기는 대안도 있으나 파이썬 의존성이 늘어남.
> 브라우저 경로가 인프라 변경 최소.

## ⚠️ 트레이드오프 / 주의

- **1단계 recall 상한이 전체 상한이 된다.** 임베딩이 떨어뜨린 정답 퍽은 2단계
  LLM이 절대 복구 못 함 → **K를 넉넉히**(40~60), 키워드 매칭과 합집합 필수.
  e5-small은 다국어지만 완벽하지 않다.
- **프롬프트 캐시 이점 상실.** 지금은 역할별 코퍼스가 모든 질의에서 **동일**해서
  prompt caching이 거의 100% 히트한다 (`cache_control` ephemeral,
  [server.py](../server.py) `_ask_anthropic` system 블록).
  후보 집합은 질의마다 달라지므로 매번 cache write → read 0.
  즉 "프롬프트 작아져 싸짐" vs "캐시 못 써서 비싸짐"이 상쇄될 수 있다.
  → 명령부(instructions) 프리픽스만이라도 안정 블록으로 분리해 일부 캐시,
    혹은 비용 영향 측정 후 판단.
- **LLM 모드가 임베딩 모델(113MB)에 의존**하게 됨. 현재 LLM 모드는 모델 다운로드
  없이도 동작 → 폴백(전체 코퍼스) 경로를 반드시 유지해 이 속성 보존.
- 의미 모델 미준비 상태에서 LLM 모드 첫 사용 시 UX(다운로드 대기) 고려.

## 적용 순서 / 측정

1. 위 1·2번 수정 후 실제 누락이 줄었는지 먼저 확인. (stop_reason 경고 로그도 관찰)
2. 그래도 남으면 이 메모대로 retrieve-then-rerank 프로토타입.
3. K값(40/60/80)과 캐시 비용을 A/B로 측정해 결정.
