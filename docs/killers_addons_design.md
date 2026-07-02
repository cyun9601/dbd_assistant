# 살인마 · 애드온 데이터 파이프라인 설계 (B)

> 위키(deadbydaylight.wiki.gg)에서 **살인마별 설명**과 **애드온 정보**를 받아
> `killers.json` / `addons.json` 으로 굽는 파이프라인의 설계 문서.
> 실제 구현은 `update_killers_from_wiki.py`(A) 이며, 이 문서는 그 설계 근거를 담는다.

---

## 1. 목표 & 범위

- **가져올 것**: 살인마별 ① 개요(Overview) ② 파워(이름·설명·아이콘) ③ 애드온(이름·설명·아이콘·등급) ④ 초상화(portrait)
- **출처**: [deadbydaylight.wiki.gg](https://deadbydaylight.wiki.gg) 공식 위키 MediaWiki API — 퍽과 동일한 `action=parse` 방식
- **범위**: **살인마(killer) 전용**. 생존자 아이템/애드온은 이번 범위 밖("살인마별 애드온" 요청 기준).
- **비범위(향후)**: 앱 UI(살인마 탭)·서버 엔드포인트·애드온 LLM 검색은 §7 에 설계만 남기고 이번 스크립트에는 포함하지 않는다.

규모: 살인마 약 **43명**, 각 ~20개 애드온 → 총 **~860개 애드온**. 1회 수집에 무리 없는 크기.

---

## 2. 데이터 출처 구조 (확인 완료)

퍽과 같은 MediaWiki API 를 쓴다:

```
GET /api.php?action=parse&page=<살인마>&prop=text&format=json&redirects=1
```

- 표시명 페이지(`The_Trapper`)는 **실제 캐릭터명 페이지(`Evan_MacMillan`)로 리다이렉트**된다.
  `redirects=1` 로 따라가거나, 리다이렉트 스텁(`<div class="redirectMsg">`)을 감지해 대상 페이지를 재요청한다.
- 살인마 목록: `page=Killers` 의 "List of Killers" 갤러리에서 `/wiki/The_*` 링크 + 초상화 썸네일 추출(신규 챕터 자동 반영).

각 살인마 페이지에서 뽑는 구획:

| 데이터 | 위치(마크업) | 비고 |
|---|---|---|
| 개요 | `<span class="mw-headline" id="Overview">` 이후 `<p>` 문단들 | 다음 헤드라인 전까지 |
| 파워 이름 | 헤드라인 `id="Power:_<파워명>"` 의 텍스트 | `Power_Trivia` 는 제외 |
| 파워 설명 | 위 헤드라인 이후 본문(플레이버 + 메커니즘) | 다음 헤드라인 전까지 |
| 파워 아이콘 | 파워 구획 내 대표 이미지 | webp 변환 저장 |
| 애드온 표 | `id="Add-ons_for_the_*"` 헤드라인 직후 `<table class="wikitable overflowScroll">` | 아래 참조 |
| 초상화 | `Killers` 갤러리 썸네일 또는 인포박스 이미지 | webp 변환 저장 |

애드온 표의 각 행 구조(퍽 표와 사실상 동일):

```html
<tr>
  <th>… <img alt="IconAddon bearOil.png" src="/images/IconAddon_bearOil.png"> …</th>  <!-- 아이콘 -->
  <th><a href="/wiki/Bear_Oil">Bear Oil</a></th>                                       <!-- 이름 -->
  <td>Melted animal fat …                                                             <!-- 설명 -->
      <ul><li>Setting a <b>Bear Trap</b> is silent.</li></ul></td>
</tr>
```

- 애드온 아이콘: `IconAddon_*.png` 패턴(퍽의 `IconPerks_*` 와 대응) → 퍽의 아이콘 다운로드 로직(`{BASE}/images/{name}`) 재사용.
- **등급(rarity)**: 아이콘 컨테이너 div 의 클래스에서 추출(`common-item-element`, `uncommon-…`, `rare-…`, `very-rare-…`, `ultra-rare-…`). 없으면 `null`.

---

## 3. 데이터 스키마

기존 `perks.json` 규약(한/영 병기, `desc_html`/`desc_text` + `_en`, `search_blob`, 수동 필드 보존)을 그대로 계승한다.
**두 파일로 분리**하고 외래키로 연결 — 평탄한 애드온 목록이 (a) 향후 애드온 LLM 검색 코퍼스 구성과 (b) 퍽과 동일한 렌더링 패턴에 유리하기 때문.

### 3.1 `killers.json` (살인마당 1개)

```jsonc
{
  "id": "The_Trapper",              // 안정 id = 위키 표시명 페이지(언더스코어)
  "name": "",                       // 한글 이름 (수동, 재빌드 시 보존)
  "name_en": "The Trapper",         // 영문 표시명 (위키)
  "power_name": "",                 // 한글 파워명 (수동)
  "power_name_en": "Bear Trap",     // 영문 파워명 (위키)
  "portrait_file": "icons/killer_portrait/The_Trapper.webp",
  "power_icon": "icons/power/The_Trapper.webp",
  "overview_html": "",              // 한글 개요 (수동)
  "overview_text": "",
  "overview_html_en": "…",          // 영문 개요 (위키)
  "overview_text_en": "…",
  "power_html": "",                 // 한글 파워 설명 (수동)
  "power_text": "",
  "power_html_en": "…",             // 영문 파워 설명 (위키)
  "power_text_en": "…",
  "addon_ids": ["Bear_Oil", "…"],   // addons.json 으로의 외래키(표시 순서 유지)
  "search_blob": "…",               // 검색용 통합 텍스트
  "aliases": [],                    // 별칭 (수동, 예: "덫잡이")
  "former_names": [], "former_names_en": []
}
```

### 3.2 `addons.json` (애드온당 1개, 평탄)

```jsonc
{
  "id": "Bear_Oil",                 // 안정 id = 위키 애드온 페이지명
  "killer_id": "The_Trapper",       // 소속 살인마 (외래키)
  "name": "",                       // 한글 이름 (수동)
  "name_en": "Bear Oil",            // 영문 이름 (위키)
  "rarity": "common",               // common|uncommon|rare|very_rare|ultra_rare|null
  "icon_file": "icons/addon/IconAddon_bearOil.webp",
  "desc_html": "",                  // 한글 설명 (수동)
  "desc_text": "",
  "desc_html_en": "…",              // 영문 설명 (위키, 플레이버+효과)
  "desc_text_en": "…",
  "search_blob": "…"
}
```

> **한글 필드는 첫 수집 시 빈 값**이다(위키는 영어 전용). `ko_merge.py`(청크 분할→번역→병합,
> HTML 색강조·불릿 보존, `_text`·`search_blob` 재빌드) 또는 `translate_killers.py`(API 자동 번역)로
> 채운다. 이미 채워진 한글은 재빌드/재번역 시 id 기준으로 **보존**된다(§6).

---

## 4. 아이콘 저장 구조

퍽의 진영별 폴더(`icons/killer/`, `icons/survivor/`) 규약을 확장한다. 원본 PNG → **webp**(quality 90) 변환:

```
icons/
├─ killer/            # (기존) 살인마 퍽
├─ survivor/          # (기존) 생존자 퍽
├─ killer_portrait/   # (신규) 살인마 초상화   ── The_Trapper.webp   (파일명 = killer id)
├─ power/             # (신규) 파워 아이콘      ── The_Trapper.webp   (파일명 = killer id)
└─ addon/             # (신규) 애드온 아이콘    ── IconAddon_bearOil.webp (파일명 = 위키 원본 아이콘명)
```

- 초상화·파워 아이콘은 **killer id** 로 명명한다(파워명은 `Spencer's Last Breath` 처럼 공백·아포스트로피가 있어 파일명에 부적합). 파워는 살인마와 1:1 이라 id 로 충분히 유일.
- 애드온 아이콘은 위키 원본 파일명(`IconAddon_*`)을 유지 — 퍽(`IconPerks_*`) 규약과 대응.
- 모두 안정 id 기반이라 재실행해도 경로 불변 → diff 최소.

---

## 5. 스크래핑 파이프라인 (`update_killers_from_wiki.py` = A)

`update_en_from_wiki.py` 의 검증된 유틸을 **재사용**한다(중복 구현 방지):
`fetch()`, `_Cleaner`/`clean_html()`(luaClr 색강조→Highlight 클래스 보존), `to_text()`, `save_icon_webp()`, `nkey()`.

처리 순서:

1. **살인마 목록 수집** — `page=Killers` 파싱 → `[(name_en, page, portrait_src)]`.
2. **살인마별 페이지 파싱**(리다이렉트 추적):
   - 실명(`real_name_en`) = 콘텐츠 페이지 제목,
   - `overview_*_en` = Overview 문단 정제,
   - `power_name_en` + `power_*_en` = Power 구획 정제,
   - 애드온 표 → 각 행에서 `(id, name_en, rarity, icon, desc_*_en)`.
3. **아이콘 다운로드** — 초상화/파워/애드온 PNG→webp.
4. **병합 & 저장** — 기존 `killers.json`/`addons.json` 의 수동 한글·별칭 필드를 id 로 이어받고, `perks.json` 과 동일한 포맷(`indent=1`, `ensure_ascii=False`)으로 라운드트립 저장.

실패 내성: 개별 살인마/아이콘 실패는 건너뛰고 로그로 남긴다(전체 빌드 계속). 위키 구조 변경으로 표를 못 찾으면 명확히 `RuntimeError`.

사용법:
```bash
python update_killers_from_wiki.py            # 전체 수집
python update_killers_from_wiki.py The_Trapper # (선택) 특정 살인마만 — 개발/검증용
```

---

## 6. 재빌드 안전성 (수동 필드 보존)

`build_data.py` 가 퍽의 `aliases`/`former_names` 를 보존하는 방식과 동일:
저장 직전 기존 파일을 id 로 읽어 **수동 필드**(`name`, `real_name`, `power_name`, `overview_html/text`, `power_html/text`, `desc_html/text`, `aliases`, `former_names*`)를 이어받는다.
위키에서 오는 `*_en` 필드와 아이콘만 최신본으로 덮어쓴다 → 손번역이 유실되지 않는다.

---

## 7. 앱 통합 (구현 완료)

퍽과 같은 경로로 노출한다:

- **server.py** ✅: `GET /killers`(killers.json), `GET /addons`(addons.json) 정적 제공.
  시작 시 두 파일을 로드(`_load_bundle_json`, 없으면 빈 목록으로 기능만 비활성).
- **index.html** ✅: 헤더에 **🔍 퍽 검색 / 📕 살인마 도감** 섹션 탭 추가. 도감 모드는 살인마
  그리드 → 상세(개요 · 파워 아이콘+설명 · 등급별 애드온 그리드)로 렌더. `dispLang`(한/영)
  토글을 그대로 재사용하되, 한글 필드가 비면 영어로 폴백(`pick(ko, en)`). Highlight 색강조는
  퍽 카드의 CSS(`.Highlight1~3`)를 공유.
- **dbd.spec** ✅: `killers.json`·`addons.json` 을 datas 에 추가. 아이콘은 기존 `("icons","icons")`
  가 재귀 포함하므로 신규 폴더(`killer_portrait`·`power`·`addon`)는 자동 번들.

향후(선택): 애드온을 역할 코퍼스처럼 LLM 검색 대상으로 추가 가능 — `build_corpus` 패턴 재사용.

---

## 8. 검증 계획

1. `The_Trapper`(단순), `The_Legion`/`The_Twins`(복수 캐릭터·표 변형), 라이선스 킬러(`The_Shape`) 로 스모크 테스트.
2. 살인마 수(~43) · 애드온 총수(~860 근처) · 아이콘 다운로드 성공률 로그 확인.
3. `desc_html_en` 에 Highlight 색강조/줄바꿈이 퍽과 같은 품질로 보존되는지 육안 확인.
4. 재실행 시 diff 가 (내용 변화 없으면) 비어야 함 — id 기반 파일명/정렬 안정성 검증.
