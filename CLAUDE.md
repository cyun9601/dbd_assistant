# dbd_assistant

## 번역 규칙 (필수)

- 영→한 번역(퍽/살인마/애드온/패치노트 등 모든 문서)은 **glossary.json 의 용어를 반드시 그대로 사용**한다.
  - 예: `Oblivious` = **인지 불가능** (구버전 번역 "망각", "무지"는 사용 금지 — 검색 유의어로만 유지)
- 새 용어의 번역을 정하면 glossary.json 에 먼저 추가하고, 기존 데이터
  (perks.json / killers.json / addons.json)에 이전 번역이 있으면 함께 치환한다.
- 자동 번역 파이프라인(translate_killers.py)은 glossary.json 을 읽어 LLM 프롬프트 용어집을
  만들므로, 용어 변경은 glossary.json 수정만으로 반영된다.
- ko_merge.py(서브에이전트 수동 번역)로 번역할 때도 glossary.json 을 먼저 읽고 용어를 맞춘다.
- 용어를 바꾸면 synonyms.js 의 해당 유의어 그룹도 갱신한다(새 용어를 그룹 맨 앞에,
  옛 용어는 검색용 유의어로 유지).
