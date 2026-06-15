# -*- coding: utf-8 -*-
"""음성 검색 — 전역 단축키(STT) → OpenAI 음성 인식 → 프론트엔드로 검색어 전달.

게임이 포그라운드라 창을 전환하기 어려운 상황을 위해, OS 전역 단축키(기본
**Ctrl+Shift+Space**)를 눌러 마이크로 퍽 효과를 말하면 OpenAI 음성 인식으로
받아써 검색창에 넣고 현재 검색 모드로 검색을 실행한다.
단축키 한 번 = 녹음 시작, 다시 누르면 종료·인식(토글). 일정 시간(MAX_SECONDS)이
지나면 자동 종료한다. 게임 풀스크린에서도 알 수 있게 비프음으로 피드백한다.

- 전역 단축키: Win32 RegisterHotKey 를 ctypes 로 직접 호출(의존성 없음 — secrets_store
  의 DPAPI, nightlight 와 같은 방식). 별도 스레드에서 등록하고 그 스레드의 메시지
  루프(GetMessage)로 WM_HOTKEY 를 받는다(RegisterHotKey 는 등록한 스레드로만 메시지를 보냄).
- 마이크 녹음: sounddevice(RawInputStream, 16k/mono/int16) → stdlib wave 로 WAV.
  numpy 없이 raw 바이트만 다룬다(배포 번들에서 numpy 를 제외하므로).
- 음성 인식: OpenAI audio.transcriptions (키는 secrets_store 재사용 — OpenAI 키만 사용).
- 프론트엔드 통지: SSE 구독자 큐로 상태/결과를 브로드캐스트(server.py 의 /events).
  네이티브 창(pywebview)·브라우저 두 실행 형태 모두에서 동작한다.

이 모듈은 server 를 import 하지 않는다(순환 방지). server 가 이 모듈의
subscribe/unsubscribe/toggle/start/info 를 사용한다.

단축키를 바꾸려면 아래 HOTKEY_MODS / HOTKEY_VK / HOTKEY_LABEL 만 고치면 된다.
"""
import array
import io
import json
import math
import queue
import sys
import threading
import wave

import paths
import secrets_store

# ---- 녹음/인식 설정 ----
SAMPLE_RATE = 16000          # OpenAI 음성 인식 권장 — 16kHz mono 면 충분
MAX_SECONDS = 20             # 안전장치: 종료를 깜빡해도 이만큼 지나면 자동 종료·인식
MIN_SECONDS = 0.3            # 이보다 짧으면 오인식이라 보고 버린다
STT_MODEL = "gpt-4o-mini-transcribe"   # 저렴·정확. whisper-1 로 바꿔도 됨.
STT_LANGUAGE = "ko"          # 한국어 힌트 (오인식 감소)

# ---- 전역 단축키 (Win32 RegisterHotKey 용 상수) ----
WM_HOTKEY = 0x0312
MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_WIN, MOD_NOREPEAT = 0x1, 0x2, 0x4, 0x8, 0x4000
VK_SPACE = 0x20
HOTKEY_ID = 1
# 기본값: Ctrl+Shift+Space (DBD 기본 키와 충돌하지 않고, 전역 등록 시 OS 가 가로채
# 게임으로 전달하지 않는다). NOREPEAT 로 누르고 있을 때 반복 발화를 막는다.
HOTKEY_MODS = MOD_CONTROL | MOD_SHIFT | MOD_NOREPEAT
HOTKEY_VK = VK_SPACE
HOTKEY_LABEL = "Ctrl+Shift+Space"


def _log(msg):
    try:
        if sys.stderr:
            sys.stderr.write(msg + "\n")
    except Exception:  # noqa
        pass


# ---------------------------------------------------------------------------
# SSE 브로드캐스트 — 구독자(브라우저/창)별 큐에 이벤트를 넣는다.
# server.py 의 /events 핸들러가 subscribe() 로 큐를 받아 스트리밍한다.
# ---------------------------------------------------------------------------
_subscribers = set()
_subs_lock = threading.Lock()


def subscribe():
    """새 SSE 연결용 큐를 등록해 돌려준다."""
    q = queue.Queue(maxsize=64)
    with _subs_lock:
        _subscribers.add(q)
    return q


def unsubscribe(q):
    with _subs_lock:
        _subscribers.discard(q)


def broadcast(event):
    """모든 구독자에게 이벤트(dict)를 보낸다. 느린 구독자는 조용히 건너뛴다."""
    with _subs_lock:
        subs = list(_subscribers)
    for q in subs:
        try:
            q.put_nowait(event)
        except queue.Full:  # noqa
            pass


def _set_status(state):
    broadcast({"type": "status", "state": state})


# ---------------------------------------------------------------------------
# 소리 피드백 (Windows) — 게임 풀스크린에서도 상태를 귀로 알 수 있게.
# winsound.Beep 의 사각파 '띠딕' 대신, 사인파 + 부드러운 감쇠 엔벨로프로 합성한
# 짧은 차임을 메모리에서 재생한다(부드럽고 거슬리지 않음 · 외부 의존성 없음).
# 음정은 듣기 좋게: 상승=시작/성공, 하강=종료/오류.
# ---------------------------------------------------------------------------
_SR = 44100          # 재생 샘플레이트
_VOL = 0.26          # 음량(풀스케일 대비) — 작게


def _tone_wav(notes):
    """(freq_hz, ms) 음 목록을 사인파+엔벨로프로 합성한 WAV 바이트로(freq<=0 은 쉼표).
    각 음은 빠른 페이드인 + 종 같은 지수 감쇠 + 짧은 페이드아웃으로 클릭·거친 소리를 없앤다."""
    pcm = array.array("h")
    atk = max(1, int(_SR * 0.006))     # 6ms 페이드인(클릭 방지)
    rel = max(1, int(_SR * 0.012))     # 12ms 페이드아웃
    for freq, ms in notes:
        n = max(1, int(_SR * ms / 1000))
        if freq <= 0:
            pcm.extend([0] * n)
            continue
        w = 2.0 * math.pi * freq / _SR
        for i in range(n):
            env = math.exp(-2.2 * i / n)            # 종처럼 감쇠
            if i < atk:
                env *= i / atk
            elif i > n - rel:
                env *= (n - i) / rel
            pcm.append(int(math.sin(w * i) * env * _VOL * 32767))
    if sys.byteorder == "big":          # WAV 는 little-endian
        pcm.byteswap()
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wv:
        wv.setnchannels(1)
        wv.setsampwidth(2)
        wv.setframerate(_SR)
        wv.writeframes(pcm.tobytes())
    return buf.getvalue()


# 차임 정의 — 펜타토닉 계열의 듣기 좋은 음정(거슬리지 않게 짧고 작게). 임포트 시 1회 합성.
_CUE = {
    "start": _tone_wav([(784, 90), (1047, 150)]),                # 시작: G5→C6 부드러운 상승
    "stop":  _tone_wav([(1047, 80), (784, 130)]),                # 종료/변환: C6→G5 하강
    "done":  _tone_wav([(784, 80), (988, 80), (1319, 170)]),     # 성공: G5→B5→E6 작은 상승 아르페지오
    "error": _tone_wav([(523, 140), (392, 240)]),                # 오류: C5→G4 부드러운 하강(버저 아님)
}


def _beep(name):
    """차임 재생(Windows). name: 'start'|'stop'|'done'|'error'. 비차단(SND_ASYNC)."""
    if sys.platform != "win32":
        return
    data = _CUE.get(name)
    if not data:
        return

    def run():
        try:
            import winsound
            winsound.PlaySound(data, winsound.SND_MEMORY | winsound.SND_ASYNC)
        except Exception:  # noqa — 소리는 부가 기능이라 실패해도 무시
            pass

    threading.Thread(target=run, daemon=True).start()


# ---------------------------------------------------------------------------
# 녹음 상태 머신 — toggle() 한 번에 시작/종료. _rec_lock 으로 보호.
# ---------------------------------------------------------------------------
_rec_lock = threading.Lock()
_recording = False
_stream = None
_frames = []          # 녹음된 raw PCM 청크(bytes) 목록
_auto_timer = None

# OpenAI 클라이언트 캐시(키가 바뀌면 교체) — 서버 _client 와 독립(순환 import 방지).
_openai_client = None
_openai_key = None


# ---------------------------------------------------------------------------
# 선택한 입력 장치 영속화 — voice.json (사용자 데이터, 키 저장소와 분리된 독립 파일).
# config.json(DPAPI 암호화 키)과 섞지 않는다: 평문 장치 이름은 비밀이 아니고,
# favorites.json·tags_user.json 처럼 기능별로 파일·락을 따로 두어 경쟁/포맷 결합을 피한다.
# 형식: {"input_device": "<장치 이름>" | null}. null/없음 = 시스템 기본 장치 사용.
# ---------------------------------------------------------------------------
_VOICE_CFG_PATH = lambda: paths.data_path("voice.json")  # noqa: E731
_voice_cfg = threading.Lock()


def _load_selected_device():
    """voice.json 에서 저장된 입력 장치 이름을 읽는다. 없거나 깨졌으면 None
    (= 시스템 기본 장치). server._load_json 과 같은 방어적 패턴."""
    try:
        with open(_VOICE_CFG_PATH(), encoding="utf-8") as f:
            data = json.load(f)
        name = data.get("input_device") if isinstance(data, dict) else None
        return name if isinstance(name, str) and name else None
    except (FileNotFoundError, ValueError, OSError):  # noqa — 없음/깨짐 = 기본 장치
        return None


def _save_selected_device(name):
    """선택한 입력 장치 이름을 voice.json 에 저장한다. name 이 거짓값이면
    기본 장치로 되돌린다(null 저장). 전체를 다시 써 secrets_store._write_config 와 형식 통일."""
    name = (name or "").strip() or None
    with _voice_cfg:
        global _selected_device
        _selected_device = name
        try:
            with open(_VOICE_CFG_PATH(), "w", encoding="utf-8") as f:
                json.dump({"input_device": name}, f, ensure_ascii=False, indent=1)
        except OSError as e:  # noqa — 저장 실패해도 이번 세션 선택은 메모리에 유지
            _log(f"[voice] 입력 장치 저장 실패: {e}")


# 시작 시 1회 읽어 메모리에 보관(이후 _start_locked 가 device= 로 사용).
_selected_device = _load_selected_device()


def toggle():
    """단축키/마이크 버튼 공통 진입점. 녹음 중이 아니면 시작, 중이면 종료·인식."""
    with _rec_lock:
        if _recording:
            _stop_locked()
        else:
            _start_locked()


def _start_locked():
    """_rec_lock 을 잡은 상태에서 호출. 마이크 녹음을 시작한다."""
    global _recording, _stream, _frames, _auto_timer
    try:
        import sounddevice as sd
    except Exception:  # noqa
        broadcast({"type": "error", "message":
                   "마이크 라이브러리(sounddevice)가 없습니다. run.bat 으로 실행하거나 "
                   "'pip install sounddevice' 후 다시 시작하세요."})
        _beep("error")
        return
    # OpenAI 키가 없으면 헛고생하지 않게 녹음 전에 안내.
    if not secrets_store.get_key("openai"):
        broadcast({"type": "error", "message":
                   "OpenAI API 키가 없습니다. 우측 상단 ⚙️ 설정에서 OpenAI 키를 입력하세요. "
                   "(음성 인식은 OpenAI 키만 사용합니다)"})
        _beep("error")
        return

    _frames = []

    def cb(indata, frames_n, time_info, status):  # PortAudio 스레드에서 호출됨
        _frames.append(bytes(indata))

    dev_idx = resolve_device(_selected_device)   # 이름→인덱스 1회 해결(None=시스템 기본 입력)
    try:
        _stream = sd.RawInputStream(
            samplerate=SAMPLE_RATE, channels=1, dtype="int16",
            device=dev_idx, callback=cb)
        _stream.start()
    except Exception as e:  # noqa — 마이크 없음/권한 거부/저장된 장치가 사라짐 등
        _stream = None
        broadcast({"type": "error", "message": f"마이크를 열 수 없습니다: {e}"})
        _beep("error")
        return

    _recording = True
    _beep("start")
    _set_status("recording")
    _log(f"[voice] 녹음 시작 — input={_input_device_name(dev_idx)} sr={SAMPLE_RATE}")
    _auto_timer = threading.Timer(MAX_SECONDS, _auto_stop)
    _auto_timer.daemon = True
    _auto_timer.start()


def _auto_stop():
    with _rec_lock:
        if _recording:
            _stop_locked()


def _stop_locked():
    """_rec_lock 을 잡은 상태에서 호출. 녹음을 멈추고 변환은 별도 스레드로 넘긴다."""
    global _recording, _stream, _auto_timer
    if not _recording:
        return
    _recording = False
    if _auto_timer is not None:
        _auto_timer.cancel()
        _auto_timer = None
    stream = _stream
    _stream = None
    try:
        if stream is not None:
            stream.stop()
            stream.close()
    except Exception:  # noqa
        pass
    pcm = b"".join(_frames)
    _beep("stop")
    _set_status("transcribing")
    # 네트워크 호출(인식)은 락을 놓고 별도 스레드에서 — toggle 이 빨리 반환되게.
    threading.Thread(target=_transcribe_and_emit, args=(pcm,), daemon=True).start()


def _to_wav(pcm):
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)         # int16 = 2바이트
        w.setframerate(SAMPLE_RATE)
        w.writeframes(pcm)
    return buf.getvalue()


def _peak_pct(pcm):
    """int16 mono PCM 피크 진폭을 풀스케일(32767) 대비 %로. numpy 없이 stdlib array 만
    쓴다(배포 번들에서 numpy 제외 · audioop 은 3.13 에서 삭제돼 의존하지 않음).
    무음 캡처(잘못된/음소거된 입력 장치)면 0% 에 가깝게 나온다."""
    if len(pcm) & 1:              # 홀수 바이트(부분 샘플) 방어 — frombytes 가 ValueError
        pcm = pcm[:-1]
    a = array.array("h")          # signed 16-bit, 네이티브 바이트오더
    try:
        a.frombytes(pcm)
    except ValueError:
        return 0.0
    if sys.byteorder == "big":    # PCM 은 little-endian — 빅엔디안 호스트에서만 swap
        a.byteswap()
    peak = max((abs(x) for x in a), default=0)
    return round(peak / 32767 * 100, 1)


_AUTO_IDX = object()   # _input_device_name(idx) 기본값: 직접 해결하라는 표시


def _input_device_name(idx=_AUTO_IDX):
    """현재 녹음에 실제로 바인딩되는 입력 장치 이름(선택된 장치 또는 시스템 기본).
    무음의 원인(가상/잘못된 장치)을 로그·안내에서 바로 짚기 위함.
    idx 를 주면(녹음 시작 때 이미 해결한 값) 재열거 없이 그대로 쓴다."""
    try:
        import sounddevice as sd
        if idx is _AUTO_IDX:
            idx = resolve_device(_selected_device)
        if idx is None:
            idx = sd.default.device[0]
        return f"#{idx} {sd.query_devices(idx)['name']}"
    except Exception as e:  # noqa
        return f"<알 수 없음: {e}>"


# ---------------------------------------------------------------------------
# 입력 장치 열거/해결 — 이 머신에서 실측으로 확인한 사실:
#   RawInputStream(samplerate=16000, channels=1, dtype='int16') 는 MME / DirectSound
#   장치에서만 열린다(PortAudio 가 44100/48000 → 16000 으로 자동 리샘플링).
#   WASAPI 는 'Invalid sample rate'(-9997), WDM-KS 는 'Blocking API not supported'(-9999)
#   로 실패한다. 따라서 선택 가능한 입력 목록은 MME/DirectSound 로 제한하고,
#   이름이 잘리지 않는 DirectSound 를 우선한다(MME 는 이름을 31자로 잘라냄).
# ---------------------------------------------------------------------------
_HOSTAPI_RANK = {"Windows DirectSound": 0, "MME": 1}   # 둘 다 16k 열림; DirectSound 는 이름이 온전
_MME_TRUNC = 31   # MME 장치명 최대 길이(Windows) — 이 머신에서 실측 확인


def _norm(s):
    return (s or "").strip().lower()


def _same_device(a, b):
    """두 장치명이 같은 물리 장치인가. 동일하거나, 한쪽이 다른 쪽의 접두이고
    그 짧은 쪽이 MME 절단 경계(~31자)에 가까울 때만 True(짧은 일반명 오결합 방지)."""
    a, b = _norm(a), _norm(b)
    if a == b:
        return True
    short, lng = sorted((a, b), key=len)
    return bool(short) and lng.startswith(short) and len(short) >= _MME_TRUNC - 3


def list_input_devices():
    """UI 선택용 — 중복 제거된 입력 장치 목록.
    [{name, index, hostapi, channels, is_default}]. MME/DirectSound 만 포함(16k 로 열림)."""
    try:
        import sounddevice as sd
        devs = sd.query_devices()
        hostapis = sd.query_hostapis()
        default_in = sd.default.device[0]
    except Exception as e:  # noqa
        _log(f"[voice] 입력 장치 열거 실패: {e}")
        return []
    if not isinstance(default_in, int):
        default_in = -1

    cands = []
    for i, d in enumerate(devs):
        if d["max_input_channels"] <= 0:
            continue
        ha = hostapis[d["hostapi"]]["name"]
        if ha not in _HOSTAPI_RANK:   # WASAPI/WDM-KS 는 16k 블로킹 스트림이 안 열림 — 제외
            continue
        cands.append({"name": d["name"].strip(), "index": i, "hostapi": ha,
                      "channels": d["max_input_channels"], "rank": _HOSTAPI_RANK[ha],
                      "is_default": (i == default_in)})
    # DirectSound 먼저(온전한 이름이 대표명이 되게), 같은 순위면 긴 이름 우선
    cands.sort(key=lambda c: (c["rank"], -len(c["name"])))

    kept = []
    for c in cands:
        dup = next((k for k in kept if _same_device(k["name"], c["name"])), None)
        if dup is None:
            kept.append(c)
        else:
            if len(c["name"]) > len(dup["name"]):   # 더 긴(비절단) 이름으로 교체
                dup.update(name=c["name"], index=c["index"],
                           hostapi=c["hostapi"], channels=c["channels"])
            dup["is_default"] = dup["is_default"] or c["is_default"]

    out = [{"name": k["name"], "index": k["index"], "hostapi": k["hostapi"],
            "channels": k["channels"], "is_default": k["is_default"]} for k in kept]
    out.sort(key=lambda x: (not x["is_default"], x["name"]))
    return out


def resolve_device(name):
    """저장된 이름 → RawInputStream(device=...) 에 넘길 인덱스.
    인덱스는 재부팅/재연결에 불안정하므로 이름으로 찾는다. 못 찾으면 None(=시스템 기본값).
    여러개 매치면 16k 로 열리는 DirectSound → MME 순으로, 그 다음 낮은 인덱스를 고른다."""
    if not name:
        return None
    try:
        import sounddevice as sd
        devs = sd.query_devices()
        hostapis = sd.query_hostapis()
    except Exception as e:  # noqa
        _log(f"[voice] 장치 해결 실패({name!r}): {e}")
        return None

    cand = []   # (host-api rank, exact=0/prefix=1, index)
    for i, d in enumerate(devs):
        if d["max_input_channels"] <= 0:
            continue
        if not _same_device(d["name"], name):
            continue
        ha = hostapis[d["hostapi"]]["name"]
        exact = 0 if _norm(d["name"]) == _norm(name) else 1
        cand.append((_HOSTAPI_RANK.get(ha, 99), exact, i))
    if not cand:
        _log(f"[voice] 저장된 마이크 {name!r} 를 찾지 못해 시스템 기본 입력을 쓴다.")
        return None
    cand.sort()
    return cand[0][2]


def _transcribe(wav_bytes):
    global _openai_client, _openai_key
    key = secrets_store.get_key("openai")
    if not key:
        raise RuntimeError("OpenAI API 키가 없습니다.")
    if _openai_client is None or _openai_key != key:
        from openai import OpenAI   # 지연 import (미설치 시 위 핸들러에서 안내)
        _openai_client = OpenAI(api_key=key)
        _openai_key = key
    resp = _openai_client.audio.transcriptions.create(
        model=STT_MODEL,
        file=("speech.wav", wav_bytes, "audio/wav"),
        language=STT_LANGUAGE,
    )
    # 진단: 응답 타입/텍스트 — '.text 필드 오독'이 아니라 정말 빈 응답인지 구분.
    _log(f"[voice] stt resp type={type(resp).__name__} text={getattr(resp, 'text', '<<MISSING>>')!r}")
    return getattr(resp, "text", "") or ""


def _transcribe_and_emit(pcm):
    dur = len(pcm) / (SAMPLE_RATE * 2)   # int16 = 2바이트/샘플
    pct = _peak_pct(pcm)
    _log(f"[voice] 녹음 길이={dur:.2f}s 피크={pct}% bytes={len(pcm)} input={_input_device_name()}")
    if len(pcm) < int(SAMPLE_RATE * 2 * MIN_SECONDS):
        broadcast({"type": "error", "message":
                   f"녹음이 너무 짧습니다({dur:.1f}s). 단축키를 누른 뒤 또박또박 말하고 다시 눌러 종료하세요."})
        _beep("error")
        _set_status("idle")
        return
    # 사실상 무음 — 잘못된/음소거된 입력 장치(예: 가상 마이크). API 호출 없이 즉시 안내.
    if pct < 1.0:
        broadcast({"type": "error", "message":
                   f"마이크 입력이 거의 감지되지 않았습니다(볼륨 {pct}%). Windows '설정 > 시스템 > 소리 > 입력'에서 "
                   f"실제 마이크를 기본 장치로 고르고 음소거·볼륨을 확인하세요. 현재 장치: {_input_device_name()}"})
        _beep("error")
        _set_status("idle")
        return
    try:
        text = _transcribe(_to_wav(pcm)).strip()
    except ModuleNotFoundError:
        broadcast({"type": "error", "message":
                   "openai 패키지가 없습니다. 'pip install openai' 후 다시 실행하세요."})
        _beep("error")
        _set_status("idle")
        return
    except Exception as e:  # noqa — 네트워크/키/쿼터 등
        broadcast({"type": "error", "message": f"음성 인식 실패: {e}"})
        _beep("error")
        _set_status("idle")
        return

    if not text:
        broadcast({"type": "error", "message":
                   f"소리는 들어왔지만(볼륨 {pct}%) 음성을 알아듣지 못했습니다. "
                   f"더 또박또박 말하거나 마이크에 가까이 대고 다시 시도하세요."})
        _beep("error")
        _set_status("idle")
        return

    _beep("done")
    broadcast({"type": "transcript", "text": text})
    _set_status("idle")


# ---------------------------------------------------------------------------
# 전역 단축키 리스너 (Windows) — 등록한 스레드의 메시지 루프에서 WM_HOTKEY 수신.
# ---------------------------------------------------------------------------
def _hotkey_loop():
    import ctypes
    from ctypes import wintypes
    user32 = ctypes.windll.user32

    user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int,
                                      wintypes.UINT, wintypes.UINT]
    user32.RegisterHotKey.restype = wintypes.BOOL
    user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND,
                                   wintypes.UINT, wintypes.UINT]
    user32.GetMessageW.restype = ctypes.c_int

    if not user32.RegisterHotKey(None, HOTKEY_ID, HOTKEY_MODS, HOTKEY_VK):
        _log(f"[voice] 전역 단축키({HOTKEY_LABEL}) 등록 실패 — 다른 앱이 점유 중일 수 있습니다. "
             "음성 검색은 🎙️ 버튼으로는 계속 사용할 수 있습니다.")
        return
    _log(f"[voice] 음성 검색 단축키: {HOTKEY_LABEL} (눌러 녹음 시작 → 다시 눌러 종료·검색)")

    msg = wintypes.MSG()
    try:
        while True:
            ret = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
            if ret in (0, -1):   # 0=WM_QUIT, -1=오류
                break
            if msg.message == WM_HOTKEY and msg.wParam == HOTKEY_ID:
                try:
                    toggle()
                except Exception as e:  # noqa
                    _log(f"[voice] 토글 처리 오류: {e}")
    finally:
        user32.UnregisterHotKey(None, HOTKEY_ID)


_started = False
_start_lock = threading.Lock()


def start():
    """서버를 점유한 프로세스에서 1회 호출. 전역 단축키 리스너를 띄운다(Windows 전용)."""
    global _started
    with _start_lock:
        if _started:
            return
        _started = True
    if sys.platform != "win32":
        _log("[voice] 전역 단축키는 Windows 에서만 지원됩니다. 🎙️ 버튼으로는 사용 가능합니다.")
        return
    threading.Thread(target=_hotkey_loop, daemon=True, name="voice-hotkey").start()


def info():
    """프론트엔드 표시용 — 현재 단축키 · 선택된 입력 장치(없으면 '' = 기본 장치)."""
    with _voice_cfg:
        device = _selected_device or ""
    return {"hotkey": HOTKEY_LABEL, "platform": sys.platform, "input_device": device}


def devices():
    """프론트 입력 장치 선택 UI 용 — 선택 가능한 입력 장치 목록 + 현재 선택."""
    with _voice_cfg:
        cur = _selected_device or ""
    return {"devices": list_input_devices(), "current": cur}


def set_device(name):
    """입력 장치 선택을 저장(빈 문자열/None = 시스템 기본). 저장된 이름(또는 '')을 반환."""
    _save_selected_device(name)
    with _voice_cfg:
        return _selected_device or ""
