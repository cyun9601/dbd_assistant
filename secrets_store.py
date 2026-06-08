# -*- coding: utf-8 -*-
"""API 키 저장소.

키는 %APPDATA%\\dbd-assistant\\config.json 에 보관하되, Windows DPAPI
(CryptProtectData) 로 현재 사용자 계정에 묶어 암호화한다 — 다른 사용자/PC 로
파일을 복사해도 복호화되지 않는다. DPAPI 는 ctypes 로 crypt32.dll 을 직접 호출하므로
별도 의존성이 없다. (Windows 가 아니거나 DPAPI 실패 시 평문으로 저장하고 표시.)

조회 우선순위: UI 에 저장한 config → 환경변수(ANTHROPIC_API_KEY / OPENAI_API_KEY).
UI 에서 키를 저장하면 환경변수보다 우선 적용(override)되어 설정/수정이 항상 의미를 갖는다.
저장한 키가 없으면 환경변수를 그대로 사용하므로 기존 개발 환경도 그대로 동작한다.

GET /config 로는 절대 평문 키를 내보내지 않는다 (설정 여부 + 마스킹값만).
"""
import base64
import json
import os
import sys
import threading

import paths

PROVIDERS = ("anthropic", "openai")
ENV_VAR = {"anthropic": "ANTHROPIC_API_KEY", "openai": "OPENAI_API_KEY"}

_CONFIG_PATH = lambda: paths.data_path("config.json")  # noqa: E731
_lock = threading.Lock()

# ---------------------------------------------------------------------------
# DPAPI (Windows) — ctypes 로 직접 호출. 실패하면 (Windows 아님 등) 평문 폴백.
# ---------------------------------------------------------------------------
_IS_WIN = sys.platform == "win32"


def _dpapi(encrypt, data):
    """encrypt=True 면 CryptProtectData, False 면 CryptUnprotectData. bytes 반환."""
    import ctypes
    from ctypes import wintypes

    class _BLOB(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD),
                    ("pbData", ctypes.POINTER(ctypes.c_char))]

    buf = ctypes.create_string_buffer(bytes(data), len(data))  # 호출 동안 살아 있어야 함
    blob_in = _BLOB(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))
    blob_out = _BLOB()
    fn = (ctypes.windll.crypt32.CryptProtectData if encrypt
          else ctypes.windll.crypt32.CryptUnprotectData)
    # (pDataIn, szDesc, pEntropy, pvReserved, pPrompt, dwFlags, pDataOut)
    ok = fn(ctypes.byref(blob_in), u"dbd-assistant", None, None, None, 0,
            ctypes.byref(blob_out))
    if not ok:
        raise OSError("DPAPI 호출 실패")
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(blob_out.pbData)


def _encrypt(plaintext):
    """(enc_marker, stored_value) 반환. DPAPI 가능하면 암호화, 아니면 평문."""
    if _IS_WIN:
        try:
            blob = _dpapi(True, plaintext.encode("utf-8"))
            return "dpapi", base64.b64encode(blob).decode("ascii")
        except Exception:  # noqa — DPAPI 불가 시 평문 폴백
            pass
    return "plain", plaintext


def _decrypt(enc, value):
    """저장값을 평문으로. 복호화 실패 시 None."""
    if enc == "dpapi":
        if not _IS_WIN:
            return None
        try:
            return _dpapi(False, base64.b64decode(value)).decode("utf-8")
        except Exception:  # noqa
            return None
    return value  # plain


# ---------------------------------------------------------------------------
# config.json 읽기/쓰기
# ---------------------------------------------------------------------------
def _read_config():
    try:
        with open(_CONFIG_PATH(), encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (FileNotFoundError, ValueError, OSError):
        return {}


def _write_config(cfg):
    with open(_CONFIG_PATH(), "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=1)


def _stored_keys(cfg=None):
    """config 에 저장된 {provider: plaintext} (복호화). 깨진 항목은 건너뜀."""
    cfg = cfg if cfg is not None else _read_config()
    keys = cfg.get("keys", {}) if isinstance(cfg.get("keys"), dict) else {}
    out = {}
    for prov in PROVIDERS:
        ent = keys.get(prov)
        if isinstance(ent, dict) and ent.get("value"):
            pt = _decrypt(ent.get("enc", "plain"), ent["value"])
            if pt:
                out[prov] = pt
    return out


# ---------------------------------------------------------------------------
# 공개 API
# ---------------------------------------------------------------------------
def get_key(provider):
    """provider 의 유효 키. UI 저장키 우선(환경변수 override), 없으면 환경변수. 없으면 None."""
    with _lock:
        stored = _stored_keys().get(provider)
    return stored or os.environ.get(ENV_VAR[provider]) or None


def save_key(provider, plaintext):
    """키 저장(암호화). 빈 문자열이면 삭제와 동일하게 처리."""
    plaintext = (plaintext or "").strip()
    with _lock:
        cfg = _read_config()
        keys = cfg.get("keys") if isinstance(cfg.get("keys"), dict) else {}
        if plaintext:
            enc, value = _encrypt(plaintext)
            keys[provider] = {"enc": enc, "value": value}
        else:
            keys.pop(provider, None)
        cfg["keys"] = keys
        _write_config(cfg)


def clear_key(provider):
    with _lock:
        cfg = _read_config()
        keys = cfg.get("keys") if isinstance(cfg.get("keys"), dict) else {}
        keys.pop(provider, None)
        cfg["keys"] = keys
        _write_config(cfg)


def _mask(key):
    """마스킹: 앞 6자 + … + 뒤 4자. 짧으면 전부 가림."""
    if not key:
        return ""
    if len(key) <= 12:
        return key[:2] + "…"
    return f"{key[:6]}…{key[-4:]}"


def status():
    """UI 용 상태. 평문 키는 절대 포함하지 않는다.

    {provider: {set, source: 'config'|'env'|None, masked, dpapi, env_present}}
    - source: 현재 '활성' 키의 출처. 저장키가 있으면 'config'(환경변수보다 우선).
    - env_present: 환경변수에도 키가 있는지 (저장키를 지우면 환경변수로 되돌아감).
    - dpapi=True 면 그 저장 키가 암호화돼 있다는 뜻(평문 폴백이면 False).
    """
    with _lock:
        cfg = _read_config()
        stored = _stored_keys(cfg)
        cfg_keys = cfg.get("keys", {}) if isinstance(cfg.get("keys"), dict) else {}
    out = {}
    for prov in PROVIDERS:
        env = os.environ.get(ENV_VAR[prov])
        if prov in stored:
            src, key = "config", stored[prov]      # 저장키가 환경변수보다 우선
        elif env:
            src, key = "env", env
        else:
            src, key = None, None
        ent = cfg_keys.get(prov) if isinstance(cfg_keys.get(prov), dict) else {}
        out[prov] = {
            "set": bool(key),
            "source": src,
            "masked": _mask(key),
            "dpapi": ent.get("enc") == "dpapi",
            "env_present": bool(env),
        }
    return out
