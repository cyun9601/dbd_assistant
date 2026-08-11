# 🔪 DBD 어시스턴트 (살인마 + 생존자)

게임하면서 퍽 효과를 **한국어로 설명**하면, 가장 비슷한 퍽을
아이콘과 함께 가능성 높은 순으로 찾아줍니다.
상단 **살인마 / 생존자 토글**로 검색할 진영을 고릅니다.

> (살인마) `"살인마 속도가 빨라졌어"` → 이동 속도 관련 퍽들
> (살인마) `"발전기 수리가 막혔어"` → 교착 상태, 주술: 파멸 …
> (생존자) `"다친 동료 위치가 보여"` → 유대, 공감 …
> (생존자) `"발전기 다 고치면 빨라지는 거"` → 아드레날린 …

각 퍽이 실제로 **얼마나 많이 쓰이는지**(🔥 사용률)도 카드에 함께 보여줍니다 — [nightlight.gg](https://nightlight.gg/perks) 의 커뮤니티 통계 기반. 전체 보기는 **사용률 높은 순**이 기본입니다.
한글 번역이 의심스러우면 카드의 **🇬🇧 영어 원문** 버튼으로 영어 퍽 이름·설명 원문을 펼쳐 볼 수 있습니다.

**⚙️ 언어 설정** — 설정에서 ① **표시 언어**(한국어/English, 카드에 보여줄 언어 · 검색과 무관)와 ② **검색 범위**(동일 언어 검색 / 다국어 검색)를 고를 수 있습니다. *다국어 검색*은 한국어·영어 어느 쪽으로 입력해도 매칭되며, 세 검색 모드 모두에 적용됩니다.

데이터 출처: 영어 설명·아이콘 [deadbydaylight.wiki.gg](https://deadbydaylight.wiki.gg/wiki/Perks) · 한글 설명은 위키 원문을 자체 번역 · 사용률 [nightlight.gg](https://nightlight.gg/perks) · 살인마 **145개** + 생존자 **176개** = **321개** 전부

---

## 데모

![DBD 어시스턴트 데모](assets/demo.gif)

> GIF 미리보기입니다. 소리·고화질 원본은 [assets/demo.mp4](assets/demo.mp4) 에서 볼 수 있어요.
> (GitHub README는 상대경로 `<video>` 재생을 지원하지 않아 GIF로 표시합니다.)

---

## 실행 방법

### 1) 가장 쉬운 방법 — exe 더블클릭 (배포본, 파이썬 불필요) ⭐
배포된 `DBD-Assistant` 폴더 안의 **`DBD-Assistant.exe`** 를 더블클릭하면 앱 창이 뜹니다.
- **파이썬 설치 불필요** — 인터프리터와 라이브러리가 exe 안에 포함돼 있습니다.
- **API 키는 환경변수 설정 없이** 창 우측 상단 **⚙️ 설정**에서 붙여넣으면 됩니다 (아래 [AI 정밀 검색 설정](#ai-정밀-검색-모드-설정-api-키) 참고).
- **종료**: 창을 닫으면 끝납니다 (백그라운드에 남지 않음).
- 세 가지 검색 모드 모두 동작합니다.

> 처음 실행 시 Windows SmartScreen 경고가 뜨면 **추가 정보 → 실행**을 누르세요(서명 안 된 자체 빌드라 그렇습니다).

### 2) 그냥 `index.html` 더블클릭
**키워드 검색 모드**는 인터넷 없이 바로 동작합니다.
단, **의미 기반 AI**와 **AI 정밀 검색** 모드는 로컬 서버(exe / `run.bat` / `app.py`)가 필요합니다.

### 3) 개발자용 — `run.bat`(콘솔+브라우저) 또는 `python app.py`(네이티브 창)
소스에서 바로 실행. **파이썬 필요.** `run.bat` 은 콘솔에 서버를 띄우고 브라우저를 엽니다.
`python app.py` 는 exe 와 동일한 네이티브 창으로 띄웁니다 (`pip install pywebview` 필요).

---

## 진영 토글 & 검색 모드

상단의 **🔪 살인마 / 🩹 생존자** 버튼으로 검색 대상을 전환합니다. 선택한 진영의 퍽 안에서만 결과가 나옵니다.
아래 세 가지 검색 모드는 양쪽 진영에서 모두 동작합니다.

| 모드 | 설명 | 특징 |
|------|------|------|
| **키워드 + 유의어** | "속도=이동속도=질주=무빙" 같은 게임 용어 사전으로 매칭 | 즉시 · 완전 오프라인 · 비용 0 |
| **의미 기반 AI** | 로컬 다국어 임베딩 모델로 문장 의미를 비교 | 모호한 표현에 강함 · **완전 오프라인**(모델 1회 다운로드 후) · 비용 0 |
| **AI 정밀 검색** | 선택한 진영의 퍽 **전체를 LLM에 보내** 가장 가능성 높은 퍽을 근거와 함께 반환 | 가장 정확 · API 키 필요 · 질문당 소액 과금 · Enter로 실행 |

- **키워드 모드**는 `발전기`, `갈고리`, `오라`, `판자` 처럼 구체적 단어가 들어간 질문에 특히 정확합니다.
- **의미 기반 AI**는 `"맞으면 한 방에 쓰러져"` 처럼 돌려 말해도 의미로 찾아줍니다. 모델·라이브러리를 **로컬에 받아두고**(`python download_model.py`, 1회) 브라우저 안에서 돌리므로, 그 뒤로는 **인터넷 없이** 동작하고 매번 다시 받지 않습니다. 퍽 쪽 벡터는 [미리 구워 두어](#의미검색-벡터-다시-굽기-퍽-데이터를-바꿨다면) 모드에 들어갈 때 기다림이 없습니다.

  ```bash
  python download_model.py   # 1회: 모델(ONNX)+라이브러리를 models/, vendor/ 에 저장 (~155MB)
  ```
- **AI 정밀 검색**은 가장 똑똑합니다. 선택한 진영의 퍽(살인마 145 / 생존자 176)을 통째로 LLM에 넣고(진영별로 프롬프트 캐싱되어 저렴), `confidence %`와 **매칭 근거**까지 보여줍니다.

### AI 정밀 검색 모드 설정 (API 키)

이 모드는 **Anthropic 또는 OpenAI** 중 하나의 API 키가 필요합니다. 드롭다운에서 모델을 고르면 해당 공급자 키를 사용합니다.

| 공급자 | 드롭다운 모델 | 키 발급 |
|--------|--------------|---------|
| **Anthropic** | Opus 4.8 (정확) · Haiku 4.5 (빠름) | [console.anthropic.com](https://console.anthropic.com/) |
| **OpenAI** | GPT-4.1 · GPT-4.1 mini · GPT-4o · GPT-4o mini | [platform.openai.com](https://platform.openai.com/api-keys) |

**입력 방법 (권장):** 창 우측 상단 **⚙️ 설정**을 열고, 쓰려는 공급자 칸에 키(`sk-ant-...` 또는 `sk-...`)를 붙여넣고 **저장**. 환경변수 설정이 필요 없습니다.

- 키는 **이 PC에만** 저장됩니다 — `%APPDATA%\dbd-assistant\config.json` 에 **Windows DPAPI 로 사용자 계정에 묶어 암호화**해 보관합니다. 다른 PC/계정으로 파일을 복사해도 복호화되지 않습니다.
- 키는 **로컬 서버에서만** 읽고 외부로 전송되지 않으며, 브라우저로도 평문이 노출되지 않습니다(설정 화면엔 마스킹값 `sk-ant…1234` 만 표시).
- 키가 없어도 **키워드/의미기반 모드는 정상 동작**합니다. AI 정밀 검색에서 키가 없으면 “⚙️ 설정 열기” 버튼이 안내됩니다.

**환경변수도 지원:** `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` 가 설정돼 있으면, ⚙️에 **저장한 키가 없을 때** 자동으로 그 값을 가져와 씁니다(“환경변수 사용 중”으로 표시). ⚙️에서 키를 저장하면 그 키가 **환경변수보다 우선** 적용되며(“환경변수 대신 사용”), 저장한 키를 삭제하면 다시 환경변수 값으로 되돌아갑니다. 즉 환경변수 유무와 상관없이 UI 에서 키를 설정·수정할 수 있습니다.

> 모델 목록을 바꾸려면 `index.html`의 `<select id="model">`과 `server.py`의 `ALLOWED_MODELS`를 함께 수정하세요. `claude-`로 시작하면 Anthropic, 그 외는 OpenAI로 라우팅됩니다.

---

## 🎙️ 음성 검색 (단축키 + STT)

게임이 풀스크린이라 창 전환이 번거로울 때, **전역 단축키 `Ctrl+Shift+Space`** 를 눌러 마이크로 퍽 효과를 말하면 음성을 받아써 검색창에 넣고 **현재 검색 모드로 자동 검색**합니다.

- **토글 방식** — 한 번 누르면 녹음 시작, 다시 누르면 종료·인식. 깜빡해도 20초 뒤 자동 종료합니다.
- **차임음 피드백** — 게임 화면 위에서도 상태를 귀로 알 수 있게 시작/종료/성공/오류를 서로 다른 부드러운 차임음으로 알립니다(사인파 합성 — 거슬리는 사각파 비프음이 아님).
- **게임 위에서도 동작** — Win32 `RegisterHotKey` 로 등록한 전역 단축키라 게임이 포그라운드여도 잡힙니다(OS 가 가로채 게임엔 전달 안 됨). 창이 포커스됐을 땐 검색창 옆 **🎙️ 버튼**으로도 같은 동작을 씁니다.
- **OpenAI 키 필요** — 음성 인식은 OpenAI 음성 인식 API(한국어)를 씁니다. AI 정밀 검색과 **같은 OpenAI 키**(⚙️ 설정 또는 `OPENAI_API_KEY`)면 됩니다. 키가 없으면 녹음 전에 안내합니다.
- **입력 장치 선택** — ⚙️ 설정의 **🎙️ 음성 검색 입력 장치**에서 사용할 마이크를 고를 수 있습니다(비워두면 Windows 기본 장치). 기본 입력이 가상 마이크 등으로 잘못 잡혀 무음만 녹음될 때 실제 마이크로 지정하세요. 선택은 `voice.json` 에 저장되어 다음 실행에도 유지됩니다. 녹음했는데 결과가 비면 앱이 **측정한 입력 볼륨(%)과 현재 장치 이름**을 함께 알려줘 "마이크가 소리를 못 잡음"인지 "잡았는데 못 알아들음"인지 바로 구분됩니다.
- **실행 조건** — 로컬 서버가 떠 있어야 합니다(`run.bat` · `python app.py` · exe). `run.bat` 은 마이크 녹음용 `sounddevice` 를 자동 설치합니다. `file://` 로 그냥 열면 음성 검색은 동작하지 않습니다.

> 단축키를 바꾸려면 `voice.py` 의 `HOTKEY_MODS` / `HOTKEY_VK` / `HOTKEY_LABEL` 만 고치면 됩니다.

---

## 유의어 사전 직접 늘리기

게임 용어/줄임말이 부족하면 [synonyms.js](synonyms.js) 를 편집하세요.
같은 개념의 말들을 한 줄(배열)로 묶으면, 그중 아무 단어로 검색해도 그룹 전체로 매칭됩니다.

```js
// 한 줄 = 한 그룹
["이동 속도", "속도", "빨라", "질주", "무빙", "이속", ...],
```

---

## 데이터 갱신 (새 퍽 추가 시)

```bash
python update_en_from_wiki.py
```

deadbydaylight.wiki.gg(공식 위키)에서 살인마·생존자 퍽의 **영어 설명문·아이콘**을 다시 받아
`perks.json` 의 `desc_html_en`/`desc_text_en` 과 `icons/` 를 갱신합니다(한글 필드는 건드리지 않음).
아이콘은 위키 PNG 를 webp 로 변환해 기존 경로에 덮어씁니다.

아직 안 나온 패치의 퍽에는 예정 배지를 붙입니다(실행 끝에 `UP` 로 표시 · 영어만 자동이라
**한글 설명은 같이 손봐야** 합니다). 두 종류를 구분합니다:

| `upcoming_kind` | 배지 | 무엇 | 어떻게 찾나 |
|---|---|---|---|
| `new` | 🔜 **출시 예정**(주황) | 미출시 챕터의 **퍽 자체가 새로 나옴** | 스크립트의 `UPCOMING_OWNERS` (예: `The Judgment`·`Aurora Stardotter` → 10.1.0) |
| `update` | 🔜 **업데이트 예정**(파랑) | 이미 있는 퍽의 **설명·수치만 바뀜** | `patchnotes.json` 의 *perk updates* 목록 + 위키의 미출시 패치 안내 문구 |

`update` 퍽은 **라이브 설명과 예정 설명을 둘 다** 들고 있습니다 — 본문(`desc_html` 등)은 **지금 게임에 적용된 값**이고,
바뀔 내용은 `pending`(`desc_html`/`desc_text`/`desc_html_en`/`desc_text_en`)에 담깁니다. 앱은 **출시일이 되면 그날부터
`pending` 을 본문처럼** 씁니다(표시·검색·의미검색·AI 정밀 검색 모두 같은 기준) — 데이터를 다시 굽지 않아도 알아서 갈아탑니다.
출시 전에는 카드에서 **`🔜 … 변경 예정 설명`** 버튼으로 바뀔 내용을 펼쳐 볼 수 있습니다.

패치가 나간 뒤 스크립트를 다시 돌리면 `pending` 을 본문으로 **승격**하고(로그에 `PROMOTE`) 예정 관련 필드를 정리합니다.
영어는 위키에서 자동으로 받지만 **`pending.desc_html`(한글 예정본)은 손번역**입니다 — 비어 있으면 실행 로그가
`한글 예정본 없음` 으로 알려주고, 앱은 그동안 라이브 설명을 그대로 보여줍니다.

위키는 미출시 챕터 퍽도 안내 문구 없이 일반 퍽처럼 실어서 배너로는 가려낼 수 없기 때문에,
새 챕터 캐릭터는 `UPCOMING_OWNERS` 에 적어 둡니다(출시일이 지나면 다른 표시와 똑같이 자동 해제).
바뀌는 퍽 쪽도 위키가 안내 문구를 빠뜨리는 경우가 있어(10.1.0 의 *구조*) **공식 패치노트의
`perk_updates` 목록을 함께 대조**합니다 — `patchnotes.json` 이 있으면 자동으로 씁니다.
배지는 위키 패치노트(`Patch Notes 10.1.X`)의 **Release Dates 표에서 읽은 라이브 출시일이 지나면 자동으로 사라집니다** —
데이터에 `upcoming`·`upcoming_patch`·`upcoming_date` 로 저장되고, 앱이 실행 시점 날짜와 비교하므로
데이터를 다시 굽지 않아도 그날부터 평범한 설명으로 표시됩니다.

위키 표가 아직 `TBA` 인 패치는 `update_en_from_wiki.py` 위쪽 **`PATCH_DATES`** 에 날짜를 적어 두면 그 값을 씁니다
(예: `"10.1.0": "2026-08-25"`). 표에 실제 날짜가 올라오면 **위키 값이 이를 덮으므로** 나중에 지우지 않아도 됩니다.
패치가 밀려 날짜가 바뀌면 이 한 줄만 고치면 됩니다.

아이콘까지 다시 받을 필요가 없으면 `--no-icons`.

`perks.json` 에 아직 없는 위키 퍽은 `NEW` 로 **보고만** 합니다(한글 번역이 수동이라 자동 추가하지 않음).
라이선스 만료로 생기는 **개명 일반퍽**(예: *Save the Best for Last* ↔ *Keep Them Waiting*)은
소유 퍽의 `former_names`/`former_names_en` 에 적어 두면 `TWIN` 으로 분류되고, 두 이름 모두 검색에 잡힙니다.

**한글 설명문은 위키 영어 원문을 직접 번역해 손으로 채웁니다**(`desc_html`/`desc_text`).
카드의 🇬🇧 버튼은 한글 번역이 의심스러울 때 위키 영어 원문을 펼쳐 보여 줍니다.
각 퍽엔 `role`(`killer`/`survivor`) 필드가 붙어, 앱의 진영 토글과 서버 코퍼스 분리에 쓰입니다.

사용률은 nightlight.gg 와 매핑해 `nl_id`(사용률 API용 고정 id)와 기준 사용률(`usage`)로 구워 둡니다
— 서버가 `/usage` 로 매일 갱신된 값을 주고, nightlight 가 오프라인이면 구운 기준값(`usage`)으로 폴백합니다.

> **참고**: 초기 `perks.json` 구조(퍽 목록·slug·role)는 예전에 `build_data.py`(dbd-db.com)로 만들었으나
> 더 이상 쓰지 않습니다. 지금은 위 위키 도구 + 수동 한글 번역으로 유지합니다.

### 패치노트 갱신

```bash
python update_patchnotes_from_steam.py            # 최근 공지 50개에서 패치노트만 추림
python update_patchnotes_from_steam.py --count 100
```

Steam 공식 공지(스토어 뉴스와 같은 원문)에서 패치노트를 받아 `patchnotes.json` 을 굽습니다 —
앱의 **📜 패치노트** 탭이 서버 `GET /patchnotes` 로 읽습니다. 본문 BBCode 는 앱이 그대로 그릴 수 있는
최소 HTML(`<b>`/`<i>`/`<a>`)과 블록 목록(h2/h3/p/li + 중첩 깊이)으로 바꾸고, 오프라인에서 못 받는
이미지는 버립니다. **본문은 공식 원문(영어)** 그대로입니다 — Steam 에 한국어판 공지가 없습니다.

각 패치가 언급한 퍽은 `perk_ids` 로 뽑아 둡니다. 앱은 이를 **한글 퍽 이름 칩**으로 보여주고, 누르면
그 자리에서 퍽 카드를 펼칩니다. 공식 노트는 라이선스 만료 이름(예: *Keep Them Waiting*)을 쓰므로
`former_names_en` 까지 대조해 우리 퍽과 이어 붙입니다.

### 살인마 · 애드온 갱신

```bash
python update_killers_from_wiki.py                 # 전체 살인마 수집
python update_killers_from_wiki.py "The_Trapper"    # 특정 살인마만 (개발/검증용)
```

같은 위키에서 살인마별 **개요·파워·애드온**의 영어 원문·아이콘을 받아 `killers.json`(44명) ·
`addons.json`(880개)과 `icons/killer_portrait/`·`icons/power/`·`icons/addon/` 를 갱신합니다.
퍽과 동일하게 **영어(`*_en`)와 아이콘만** 위키에서 받고, 한글 필드는 손으로 번역해 채우며
재실행 시 id 로 보존됩니다. 설계 근거는 [`docs/killers_addons_design.md`](docs/killers_addons_design.md) 참고.

퍽과 마찬가지로 **아직 안 나온 챕터의 살인마**는 `UPCOMING_KILLERS` 에 적어 두면 도감 타일·상세에
주황 `🔜 출시 예정` 배지가 붙고, 위키 패치노트의 라이브 출시일이 지나면 자동으로 사라집니다.
위키가 다음 패치 기준으로 미리 고쳐 둔 설명에 붙이는 안내 문구도 개요·파워·애드온에서 걷어냅니다.

앱 상단의 **📕 살인마 도감** 탭에서 살인마 그리드 → 상세(개요·파워·등급별 애드온)를 볼 수 있고,
**📜 패치노트** 탭에서는 패치별 공식 노트와 그 패치에서 바뀐 퍽을 바로 펼쳐 볼 수 있습니다.
서버는 `GET /killers`·`/addons` 로 데이터를 제공하며, 표시 언어 토글(한/영)도 함께 적용됩니다.

**한글 번역**(개요·파워·애드온 이름/설명)은 `ko_merge.py` 로 채웁니다 — 영어 원문을 청크로 나눠
번역한 뒤 병합하며, HTML 색강조(Highlight)·불릿을 보존하고 `_text`·`search_blob`(한/영 통합,
추후 도감 검색용)을 다시 굽습니다. 아직 번역이 없는 필드는 앱에서 영어로 자동 폴백됩니다.
(OpenAI/Anthropic API 로 자동 번역하려면 `translate_killers.py --model ...` 도 사용 가능.)

### 의미검색 벡터 다시 굽기 (퍽 데이터를 바꿨다면)

```bash
python build_embeddings.py            # 검색 프로파일 3종 전부
python build_embeddings.py multi      # 특정 프로파일만
```

'의미 기반 AI' 모드가 쓰는 **코퍼스 벡터를 미리 구워** `embeddings/` 에 둡니다 —
`index.json`(메타·퍽 id 순서·패시지 해시)과 프로파일별 `*.bin`(float32, 321×384, 약 482KB).
퍽 데이터가 그대로면 임베딩 결과도 항상 같으므로, 앱은 이 파일을 읽기만 하고 브라우저에서
321개를 다시 임베딩하지 않습니다. 모델(~113MB)은 **질의 한 줄을 임베딩할 때만** 필요해서
모드 진입 시에는 기다리지 않고 배경에서 로드됩니다.

프로파일은 검색 범위·표시 언어 조합 3종입니다 — `multi`(한+영, 기본) · `same-ko` · `same-en`.
`perks.json` 을 고쳤으면 다시 구우세요. 안 구워도 앱은 **패시지 해시로 달라진 퍽만 골라내
그 자리에서 다시 임베딩**하므로 틀린 결과가 나오지는 않습니다(출시일이 지나 `pending` 설명으로
갈아타는 퍽도 이 경로로 처리됩니다). 파일이 아예 없으면 예전처럼 전부 브라우저에서 임베딩합니다.

빌드 전용으로 `pip install onnxruntime tokenizers numpy` 가 필요하고, 모델은
`download_model.py` 가 받아 둔 것을 그대로 씁니다(앱 실행에는 셋 다 불필요).

---

## exe 빌드 (배포용)

배포본(파이썬 없이 도는 exe)을 만들려면 **`build.bat`** 더블클릭 (또는):

```bat
python -m PyInstaller --noconfirm --clean dbd.spec
```

- 처음 한 번은 빌드 도구를 설치합니다: `pip install pyinstaller pywebview`
- 결과: **`dist\DBD-Assistant\`** (one-folder). 이 폴더 **전체**를 zip 으로 묶어 배포합니다.
  진입점은 `app.py`(서버 스레드 + pywebview 네이티브 창)입니다.
- 번들에는 읽기 전용 자산(`index.html`, `perks.json`, `icons/`, `embeddings/`, `tags.json` …)과 `anthropic`/`openai` SDK 가 포함됩니다.
  의미기반 모델(~155MB)은 용량 때문에 번들하지 않고 **첫 사용 시 `%APPDATA%\dbd-assistant\` 로 1회 다운로드**합니다.
- 사용자가 만드는 데이터(API 키·즐겨찾기·사용자 태그·다운로드 모델)는 모두 `%APPDATA%\dbd-assistant\` 에 저장되므로,
  exe 폴더가 `Program Files` 처럼 쓰기 불가여도 정상 동작합니다.

> 자체 빌드라 코드 서명이 없어 SmartScreen 경고가 날 수 있습니다(추가 정보 → 실행).
> 정식 배포 시엔 코드 서명 인증서를 적용하면 경고가 사라집니다.

---

## 파일 구성

| 파일 | 역할 |
|------|------|
| `index.html` | 검색 앱 (UI + 세 가지 검색 모드 + 📕 살인마 도감 + ⚙️ API 키 설정) |
| `search.js` | 키워드 + 유의어 검색·랭킹 로직 |
| `synonyms.js` | DBD 한글 게임 용어 유의어 사전 (편집 가능) |
| `server.py` | 로컬 서버 — 정적 파일 + `/ask`(LLM 정밀 검색) + `/killers`·`/addons`(살인마 도감) + `/config`(키 입력/저장) + `/usage`(실시간 사용률) + `/events`(음성 검색 SSE) + `/voice/*` |
| `voice.py` | 음성 검색 — 전역 단축키(Win32 `RegisterHotKey`, ctypes) + 마이크 녹음(`sounddevice`) + OpenAI 음성 인식 + SSE 브로드캐스트 |
| `nightlight.py` | nightlight.gg 퍽 사용률 수집 (런타임 API + 빌드 시 slug↔id 매핑, 외부 의존성 없음) |
| `app.py` | exe/네이티브 창 진입점 — 서버 스레드 + pywebview (없으면 브라우저 폴백) |
| `paths.py` | 실행 경로 해석 — 번들 자산(읽기) vs 사용자 데이터(`%APPDATA%`, 쓰기) 분리 |
| `secrets_store.py` | API 키 저장소 — Windows DPAPI 암호화 (ctypes, 의존성 없음) |
| `perks.json` | 퍽 데이터 (서버가 `GET /perks` 로 프런트에 제공 · 빌드가 사용, 자동 생성 · `role` 포함) |
| `icons/` | 퍽 아이콘 321개 — `icons/killer/` 145 + `icons/survivor/` 176 (진영별 폴더, 오프라인용) |
| `killers.json` / `addons.json` | 살인마(43) · 애드온(860) 데이터 — `update_killers_from_wiki.py` 로 생성 · 서버가 `/killers`·`/addons` 로 제공 |
| `patchnotes.json` | 패치노트(Steam 공식 공지 15개) — `update_patchnotes_from_steam.py` 로 생성 · 서버가 `/patchnotes` 로 제공 |
| `update_en_from_wiki.py` | 퍽 영어 설명·아이콘 갱신 (deadbydaylight.wiki.gg) |
| `update_killers_from_wiki.py` | 살인마 개요·파워·애드온 갱신 (deadbydaylight.wiki.gg) → `killers.json`/`addons.json`/아이콘 |
| `update_patchnotes_from_steam.py` | 패치노트 수집 (Steam 공식 공지) → `patchnotes.json` |
| `ko_merge.py` | 살인마/애드온 한글 번역 청크 분할(split)·병합(apply) — 영어 원문을 나눠 번역 후 합침 |
| `translate_killers.py` | (선택) 살인마/애드온 영어 → 한글 자동 번역 (OpenAI/Anthropic API) |
| `build_data.py` | (레거시) 초기 퍽 부트스트랩 스크립트 |
| `download_model.py` | 의미기반 AI용 모델·라이브러리 1회 다운로드 (→ `%APPDATA%\dbd-assistant\`) |
| `dbd.spec` · `build.bat` | PyInstaller 빌드 스펙 + 빌드 스크립트 (exe 배포본 생성) |
| `run.bat` | 개발용 실행기 (SDK 자동 설치 + 서버 기동 + 브라우저 열기) |
| `%APPDATA%\dbd-assistant\` | 사용자 데이터 — `config.json`(키, 암호화)·`favorites.json`·`tags_user.json`·`voice.json`(음성 검색 입력 장치)·`models/`·`vendor/` |

---

## 라이선스

이 프로젝트는 **[PolyForm Noncommercial License 1.0.0](LICENSE)** 으로 배포됩니다.

- ✅ **허용** — 개인·학습·연구·취미, 그리고 비영리/교육/공공 기관에서의 사용·수정·재배포
- ❌ **금지** — 상업적 이용(영리 목적 사용, 판매, 유료 서비스 제공 등)

상업적 이용을 원하시면 별도 문의해 주세요. 전체 조건은 [LICENSE](LICENSE) 파일을 참고하세요.

> ⚠️ 본 라이선스는 **이 저장소의 코드**에 적용됩니다. 퍽 데이터·아이콘·명칭 등 *Dead by Daylight* 관련 자산의 권리는 Behaviour Interactive 에 있으며, 이 라이선스가 해당 자산에 대한 권리를 부여하지 않습니다.
