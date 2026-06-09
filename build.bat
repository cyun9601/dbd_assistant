@echo off
chcp 65001 >nul
REM DBD 어시스턴트 — exe 빌드 (one-folder, 네이티브 창)
REM 결과: dist\DBD-Assistant\  (이 폴더 전체를 zip 으로 배포)
cd /d "%~dp0"

echo [1/2] 빌드 의존성 확인...
python -c "import PyInstaller, webview, anthropic, openai" 2>nul
if errorlevel 1 (
  echo   설치 중: pyinstaller pywebview anthropic openai
  python -m pip install pyinstaller pywebview anthropic openai || (echo 의존성 설치 실패 & exit /b 1)
)

echo [2/2] PyInstaller 빌드 (one-folder)...
python -m PyInstaller --noconfirm --clean dbd.spec
if errorlevel 1 (
  echo.
  echo 빌드 실패.
  exit /b 1
)

echo.
echo ============================================================
echo  완료!  dist\DBD-Assistant\DBD-Assistant.exe
echo  배포  :  dist\DBD-Assistant 폴더 전체를 zip 으로 묶어 전달
echo  실행  :  exe 더블클릭 → 창이 뜨면 ⚙️ 설정에서 API 키 입력
echo ============================================================
