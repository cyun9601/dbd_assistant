@echo off
chcp 65001 >nul
REM DBD Assistant launcher
REM Starts the local server and opens the browser (keyword / semantic / precise-AI modes).
cd /d "%~dp0"

REM Ensure SDKs needed for "precise AI" mode (install if missing)
python -c "import anthropic" 2>nul
if errorlevel 1 (
  echo [setup] Installing anthropic ...
  python -m pip install --quiet anthropic
)
python -c "import openai" 2>nul
if errorlevel 1 (
  echo [setup] Installing openai ...
  python -m pip install --quiet openai
)

REM Semantic-AI model: downloaded automatically on first use of that mode (in the browser).
REM To pre-download now instead, run:  python download_model.py

if "%ANTHROPIC_API_KEY%"=="" if "%OPENAI_API_KEY%"=="" (
  echo [info] No API key in environment. That's fine — enter your key in the web UI's
  echo        gear icon settings. ANTHROPIC_API_KEY / OPENAI_API_KEY are used as a
  echo        fallback when no key is saved in the UI ^(a UI-saved key overrides env^).
  echo        Only "precise AI" mode needs a key. This .bat NEVER changes env variables.
)

echo Opening DBD Assistant at http://localhost:8777 ...
start "" http://localhost:8777/index.html
python server.py
