# -*- coding: utf-8 -*-
"""
DBD 어시스턴트 — 네이티브 창 런처 (exe 진입점).

로컬 서버를 백그라운드 스레드로 띄우고 pywebview 로 앱 창을 연다.
창을 닫으면 프로세스가 끝나고 데몬 스레드(서버)도 함께 내려간다.
WebView2(또는 pywebview)를 못 쓰면 기본 브라우저로 폴백한다.

개발 중에는 `python app.py` 로 실행. 배포 exe 의 진입점도 이 파일.
"""
import sys
import threading
import time
import urllib.request

import os

import server
from paths import bundle_path
from version import __version__ as APP_VERSION


def _log(msg):
    # PyInstaller --windowed 빌드에선 stderr 가 None 일 수 있으므로 방어.
    try:
        if sys.stderr:
            sys.stderr.write(msg + "\n")
    except Exception:  # noqa
        pass


def _start_server():
    """서버를 점유·구동. 이미 떠 있으면(포트 사용 중) False, 새로 띄웠으면 True."""
    srv = server.create_server()
    if srv is None:
        return False   # 다른 인스턴스가 이미 실행 중 — 그 창만 띄운다
    threading.Thread(target=server.serve, args=(srv,), daemon=True).start()
    return True


def _wait_until_up(timeout=10.0):
    """서버가 응답할 때까지 잠깐 대기 (빈 화면으로 뜨는 것 방지)."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            urllib.request.urlopen(server.URL, timeout=0.5)
            return True
        except Exception:  # noqa
            time.sleep(0.15)
    return False


def main():
    started = _start_server()
    _log("서버 시작됨" if started else "이미 실행 중인 서버에 연결")
    _wait_until_up()

    try:
        import webview
        webview.create_window(
            f"DBD 어시스턴트 v{APP_VERSION}", server.URL,
            width=1024, height=840, min_size=(440, 580),
        )
        # 창 아이콘: 번들/레포의 assets/icon.ico (없으면 exe 아이콘으로 폴백).
        icon_path = bundle_path("assets", "icon.ico")
        start_kwargs = {"icon": icon_path} if os.path.isfile(icon_path) else {}
        webview.start(**start_kwargs)   # 창이 닫힐 때까지 블로킹 → 닫으면 프로세스 종료
    except Exception as e:  # noqa — WebView2/pywebview 불가 시 브라우저 폴백
        import webbrowser
        _log(f"네이티브 창을 열 수 없어 브라우저로 엽니다: {e}")
        webbrowser.open(server.URL)
        try:
            threading.Event().wait()   # 데몬 서버 스레드가 살아 있도록 메인 유지
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
