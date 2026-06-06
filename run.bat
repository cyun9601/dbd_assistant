@echo off
chcp 65001 >nul
REM DBD Killer Perk Finder launcher
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

REM Inform if the local semantic-AI model is not downloaded yet (optional, for offline use)
if not exist "models\Xenova\multilingual-e5-small\onnx\model_quantized.onnx" (
  echo [info] Semantic-AI model not found locally. Run 'python download_model.py' once
  echo        to enable fully offline semantic search. ^(keyword / precise-AI unaffected^)
)

if "%ANTHROPIC_API_KEY%"=="" if "%OPENAI_API_KEY%"=="" (
  echo [info] Neither ANTHROPIC_API_KEY nor OPENAI_API_KEY is set. Only "precise AI" mode is affected.
  echo        See the API key setup section in README.md for how to set a key.
  echo        This .bat NEVER changes your environment variables.
)

echo Opening DBD Perk Finder at http://localhost:8777 ...
start "" http://localhost:8777/index.html
python server.py
