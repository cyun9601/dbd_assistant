# -*- coding: utf-8 -*-
"""실행 경로 해석 — 개발 실행(파이썬)과 exe 패키지(PyInstaller)를 모두 지원.

두 종류의 경로를 구분한다:
- 번들 자산(읽기 전용): index.html, perks.json, icons/, tags.json … exe 안에 포함.
- 사용자 데이터(쓰기 가능): API 키·즐겨찾기·사용자 태그·다운로드 모델.

개발 모드에서는 둘 다 레포 폴더라서 기존 동작이 그대로 유지된다.
exe(frozen)에서는 사용자 데이터를 %APPDATA%\\dbd-assistant 로 옮긴다 — 번들 폴더가
임시폴더이거나 Program Files 처럼 쓰기 불가일 수 있기 때문.
"""
import os
import sys

# PyInstaller 등으로 묶이면 sys.frozen 이 True.
FROZEN = bool(getattr(sys, "frozen", False))

# 이 파일이 있는 폴더 = 개발 모드의 레포 루트.
_REPO = os.path.dirname(os.path.abspath(__file__))

# 앱 식별자 (APPDATA 하위 폴더명)
APP_DIR_NAME = "dbd-assistant"


def bundle_dir():
    """읽기 전용 번들 자산의 루트.

    frozen: PyInstaller 가 자산을 풀어 두는 곳(sys._MEIPASS). one-file 은 임시폴더,
            one-folder 는 _internal 폴더. 어느 쪽이든 자산은 여기서 읽는다.
    dev   : 레포 폴더.
    """
    if FROZEN:
        return getattr(sys, "_MEIPASS", None) or os.path.dirname(sys.executable)
    return _REPO


def data_dir():
    """쓰기 가능한 사용자 데이터 루트. 없으면 만든다.

    frozen: %APPDATA%\\dbd-assistant (APPDATA 없으면 홈 디렉터리 하위).
    dev   : 레포 폴더 (favorites.json 등을 지금처럼 레포에 두어 기존 동작 유지).
    """
    if FROZEN:
        base = os.environ.get("APPDATA") or os.environ.get("LOCALAPPDATA") \
            or os.path.expanduser("~")
        d = os.path.join(base, APP_DIR_NAME)
    else:
        d = _REPO
    os.makedirs(d, exist_ok=True)
    return d


def bundle_path(*parts):
    """번들 자산의 절대 경로."""
    return os.path.join(bundle_dir(), *parts)


def data_path(*parts):
    """사용자 데이터의 절대 경로 (상위 폴더는 data_dir() 가 보장)."""
    return os.path.join(data_dir(), *parts)
