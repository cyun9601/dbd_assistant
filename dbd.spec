# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 빌드 스펙 — DBD 어시스턴트 (one-folder, 네이티브 창).

빌드:  python -m PyInstaller --noconfirm --clean dbd.spec   (또는 build.bat)
결과:  dist/DBD-Assistant/DBD-Assistant.exe  (+ _internal/ 폴더)
배포:  dist/DBD-Assistant 폴더 전체를 zip 으로 묶어 전달.

- 진입점은 app.py (서버 스레드 + pywebview 창).
- 읽기 전용 자산(index.html, perks.json, icons/ …)만 번들. 의미기반 모델(~155MB)은
  런타임에 %APPDATA%\\dbd-assistant 로 1회 다운로드하므로 번들에 넣지 않는다.
- anthropic/openai SDK 와 pywebview(+pythonnet/clr_loader) 의 서브모듈·데이터·바이너리를
  collect_all 로 모두 수집한다.
"""
from PyInstaller.utils.hooks import collect_all, collect_submodules

datas, binaries, hiddenimports = [], [], []

# GUI 백엔드(webview + pythonnet/clr_loader)와 음성 검색용 sounddevice(번들 PortAudio
# DLL · cffi 백엔드)는 동적 임포트·네이티브 DLL·데이터가 많아 일괄 수집한다.
for pkg in ("webview", "clr_loader", "pythonnet", "sounddevice"):
    try:
        d, b, h = collect_all(pkg)
        datas += d
        binaries += b
        hiddenimports += h
    except Exception:
        pass

# SDK 는 collect_all 로 쓸면 환경에 깔린 무거운 선택적 의존성(torch/scipy/pandas …)까지
# 끌려온다. 서브모듈만 hiddenimports 로 보장하고, 실제 사용하는 의존성은 임포트 분석에 맡긴다.
for pkg in ("anthropic", "openai"):
    try:
        hiddenimports += collect_submodules(pkg)
    except Exception:
        hiddenimports.append(pkg)

# 지연/동적 임포트라 정적 분석이 놓칠 수 있는 것들 보강
hiddenimports += [
    "webview.platforms.edgechromium",   # Windows 기본 백엔드 (WebView2)
    "webview.platforms.winforms",
    "clr",                              # pythonnet 진입 모듈
    "_cffi_backend",                    # sounddevice → cffi 네이티브 백엔드
]

# 앱이 쓰지 않는 무거운 과학/그래픽 패키지 — 환경에 깔려 있어도 번들에서 제외(용량 급감).
EXCLUDES = [
    "torch", "torchvision", "torchaudio",
    "numpy", "scipy", "pandas", "matplotlib", "pyarrow",
    "numba", "llvmlite", "sympy",
    "sklearn", "scikit-learn", "cv2", "tensorflow", "transformers",
    "PIL", "Pillow", "IPython", "jupyter", "notebook", "tkinter",
]

# 읽기 전용 번들 자산 (모델/vendor 는 런타임 다운로드 → 제외)
datas += [
    ("index.html", "."),
    ("perks.json", "."),
    ("search.js", "."),
    ("synonyms.js", "."),
    ("tags.json", "."),
    ("icons", "icons"),
    ("assets/icon.ico", "assets"),   # 창 아이콘(런타임에 webview 가 사용)
]

a = Analysis(
    ["app.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=EXCLUDES,
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="DBD-Assistant",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,               # UPX 압축은 백신 오탐을 늘릴 수 있어 사용 안 함
    console=False,           # 네이티브 창이므로 콘솔 숨김
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="assets/icon.ico",  # exe 아이콘 (작업표시줄·탐색기)
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="DBD-Assistant",
)
