# 2026-10-07 DBD 데이터 갱신

정식 기준은 **10.2.0**(Mid-Chapter, Steam 공지 2026-10-06 UTC)입니다. 변경 예정 데이터는 없습니다(다음 PTB 미공개).

## 왜 10.2.0 정식 노트가 빠져 있었나

0.6.1 수집은 10월 6일 19:48(KST)에 돌렸고, 10.2.0 정식 공지는 같은 날 23:33(KST)에 올라왔습니다. 수집 시점 이후에 게시된 글이라 `patchnotes.json`에 없었습니다. `python update_patchnotes_from_steam.py --count 20`으로 다시 수집해 21개가 됐습니다.

## 확인한 출처

- [10.2.0 | Mid-Chapter](https://store.steampowered.com/news/app/381210/view/716791824502491334) — 공식 Steam 공지(2026-10-06). 'Changes from PTB' 절에 PTB 대비 변경이 정리돼 있음
- [Developer Update | 10.2.0 PTB to Live Changes](https://store.steampowered.com/news/app/381210/view/716791824502491130) — 공식 Steam 공지(2026-10-05)
- [10.2.0 | PTB Patch Notes](https://store.steampowered.com/news/app/381210/view/706656822950364293) — 공식 Steam 공지
- [공식 위키 퍽 목록](https://deadbydaylight.wiki.gg/wiki/Perks) — **아직 PTB 기준 설명**(정식 수치 미반영, 10.2.0 안내 배너 유지)

## 승격

`python update_en_from_wiki.py --no-icons`가 10.2.0을 `released`로 인식해 예정 퍽 57개의 예정본을 본문으로 승격(`PROMOTE`)했습니다. `upcoming*`·`pending` 키는 모두 제거됐습니다.

## 정식 노트가 PTB와 다른 퍽 (한글·영문 모두 보정)

0.6.1에서 개발자 업데이트로 미리 반영한 3건(어둠의 오만함·부담 감당·이런 일이 일어나다니) 외에, 정식 노트에서 추가로 바뀐 퍽입니다. 한글은 승격된 본문을 직접 고쳤고, 영문은 위키가 PTB 기준이라 `data_corrections.json`으로 보정했습니다.

| 진영 | 퍽 | PTB | 정식 |
|---|---|---|---|
| 살인마 | 격렬한 중얼거림 | 발전기 완료 시 8초, 전부 완료 시 10/12/14초 | **10초**, **16/18/20초** |
| 살인마 | 구인 | 효과 100/110/120초 | **70/80/90초** |
| 살인마 | 주술: 사냥의 전율 | 토템당 6/7/8초 봉쇄 | **4/5/6초** |
| 살인마 | 때려눕히기 | 둔화 3/4/5초 | **2/3/4초** |
| 살인마 | 머신 러닝 | 신속 10% | **8%** |
| 생존자 | 어두운 감각 | 살인마 24미터 접근 시 8/9/10초, 판자·창문 24미터 | **20미터**, **13/14/15초**, **32미터** |
| 생존자 | 무해함 | 치료 30/40/50% | **30/35/40%** (영문 최대치 60/70/80%) |
| 생존자 | 공감대 형성 | 치료 40/45/50% | **30/35/40%** |
| 생존자 | 불길한 예감 | 재사용 대기 70/65/60초 | **55/50/45초** |
| 생존자 | 도로 위에 삶 | 자가 치료 속도 100% 증가 | **10% 증가** (공식 노트 "10% faster (was 100% on PTB)" 그대로) |
| 생존자 | 잠복 근무 | 특수 스킬체크 실패 시 진행도 4% 추가 손실 | **실패 시 손실 삭제** |

## 영문 보정 (`data_corrections.json`, reviewed 2026-10-07, 16건)

- 위 11개 퍽: 정식 수치로 치환
- 어둠의 오만함: "all basic-attack recovery speeds" → "missed and obstructed basic-attack recovery speeds"
- 부담 감당: "deactivated for all Survivors" 줄 삭제
- 이런 일이 일어나다니: "Great Skill Check +30 %" 줄 삭제
- 빌려온 시간: 위키의 PTB 리워크 설명(Deep Wound 자동 붕대) → 라이브 설명(인내 연장) 전체 복원
- 기회의 창: 위키 오타 "revealed to you within 40/35/30 seconds.." → "within 24 metres"

각 보정은 위키 원문 해시(`expected_text_sha256`)에 묶여 있어, 위키가 정식 기준으로 바뀌면 `update_en_from_wiki.py`가 `ValueError(재검토)`를 냅니다. 그때 해당 항목을 지우면 됩니다. `update_en_from_wiki.py`를 다시 돌려도 결과가 같음을 확인했습니다.

## 적용 범위

- 퍽 321개 대조. 업데이트 예정 퍽 57개 → **0개**. 승격 57 + 추가 보정(한글 11·영문 16).
- 살인마 44명·애드온 880개는 재수집하지 않았습니다. 정식 노트의 'Killer Adjustments'는 마스터마인드 Virulent Bound 충돌·관성·사이드스텝 조정뿐이라 능력 설명이 바뀌지 않습니다.
- 임베딩 multi / same-ko / same-en 재생성(321×384).

## 검증

- 회귀 테스트: `python -m unittest discover -s tests -v` — 14개 통과. 예정 키 전무, 변경 퍽 58개 양쪽 설명 존재, 정식 수치 11건, 개발자 업데이트 3건·빌려온 시간·기회의 창 영문, 보정 16건 출처 검사
- 데이터: 퍽 321 / 살인마 44 / 애드온 880, ID 중복·아이콘 누락 없음

## 다음 할 일

- 위키가 10.2.0 정식 기준으로 갱신되면 `update_en_from_wiki.py`가 재검토 오류를 냅니다. 오류가 난 퍽의 2026-10-07 보정 항목을 `data_corrections.json`에서 지우고 다시 돌리면 됩니다.
- 다음 PTB(10.3.0) 공지가 올라오면 `update_patchnotes_from_steam.py` → `update_en_from_wiki.py --no-icons` 순으로 돌리고, 예정 퍽의 한글 예정본을 번역합니다.
