@echo off
setlocal
cd /d "%~dp0scraper"
title PJUD - CDP (Chrome real, clicks reales)

set "PROFILE=%LOCALAPPDATA%\pjud_cdp"
set "PORT=9333"
set "URL=https://www.pjud.cl"

set "CHROME=C:\Program Files\Google\Chrome\Application\chrome.exe"
if not exist "%CHROME%" set "CHROME=C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
if not exist "%CHROME%" (
  echo  [ERROR] No encuentro Google Chrome. Instalalo y reintenta.
  echo.
  pause
  exit /b 1
)

REM --- Python + venv (reusa pjud_venv; drive tu Chrome real, sin descargar navegador) ---
set "PY="
where py     >nul 2>&1 && set "PY=py"
if not defined PY where python >nul 2>&1 && set "PY=python"
if not defined PY (
  echo  [ERROR] No encuentro Python. Instalalo desde https://www.python.org/downloads/
  echo         y marca "Add Python to PATH".
  echo.
  pause
  exit /b 1
)
set "VENV=%LOCALAPPDATA%\pjud_venv"
if exist "%VENV%\Scripts\python.exe" goto haveenv
echo  [preparando] Creando entorno e instalando Playwright (solo la 1a vez)...
%PY% -m venv "%VENV%"
if errorlevel 1 goto fail
call "%VENV%\Scripts\activate.bat"
pip install playwright
if errorlevel 1 goto fail
goto ready
:haveenv
call "%VENV%\Scripts\activate.bat"
python -c "import playwright" 2>nul || pip install playwright
:ready

echo.
echo  ===================================================
echo    PJUD  -  CDP  (Chrome real + clicks reales)
echo  ===================================================
echo.
echo  PASOS:
echo    1) Se abrira Chrome en www.pjud.cl (puerto CDP %PORT%).
echo    2) En esa ventana: pasa el CAPTCHA, entra a "Consulta Causas",
echo       abre "Busqueda por Fecha" y elige Competencia = CIVIL, la
echo       CORTE y las FECHAS (hasta que aparezca la lista de Tribunales).
echo    3) Haz UNA busqueda manual para confirmar que SALEN resultados.
echo    4) Vuelve a ESTA ventana y presiona una tecla para iniciar.
echo.

start "" "%CHROME%" --remote-debugging-port=%PORT% --user-data-dir="%PROFILE%" --no-first-run --no-default-browser-check --start-maximized "%URL%"

echo  (Cuando el formulario este listo y con resultados, presiona una tecla...)
pause >nul

echo.
echo  Iniciando scraper (clicks reales via CDP). Ritmo GENTIL: sera lento a proposito.
echo  Para una prueba corta puedes editar y usar:  python cdp_scrape.py --max-causas 5
echo.
python cdp_scrape.py --port %PORT%
echo.
echo  --- Proceso terminado ---  (JSON en tu carpeta Descargas: pjud_cdp_*.json)
pause
exit /b 0

:fail
echo.
echo  [ERROR] Fallo la preparacion. Revisa los mensajes de arriba.
echo.
pause
exit /b 1
