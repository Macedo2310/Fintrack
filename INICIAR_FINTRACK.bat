@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" goto dependencies
where py >nul 2>nul
if errorlevel 1 goto usepython
py -3 -m venv .venv
goto checkvenv
:usepython
python -m venv .venv
:checkvenv
if errorlevel 1 goto failed
:dependencies
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto failed
echo.
echo Abra http://127.0.0.1:8010 no navegador quando o servidor iniciar.
echo Para encerrar, pressione Ctrl+C nesta janela.
".venv\Scripts\python.exe" run.py
goto end
:failed
echo Nao foi possivel iniciar. Instale Python 3.12 ou superior e confira sua conexao.
pause
:end
endlocal
