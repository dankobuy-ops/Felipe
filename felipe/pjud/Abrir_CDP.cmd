@echo off
setlocal
title PJUD - Abrir Chrome CDP (solo abre; Claude corre el scraper)

REM Abre SOLO Chrome con el puerto de depuracion (CDP). No corre el scraper:
REM tu haces el setup manual y Claude lanza cdp_scrape.py --max-causas 5.

set "PROFILE=%LOCALAPPDATA%\pjud_cdp"
set "PORT=9333"
set "URL=https://www.pjud.cl"

set "CHROME=C:\Program Files\Google\Chrome\Application\chrome.exe"
if not exist "%CHROME%" set "CHROME=C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
if not exist "%CHROME%" (
  echo  [ERROR] No encuentro Google Chrome.
  echo.
  pause
  exit /b 1
)

echo.
echo  Abriendo Chrome en modo CDP (puerto %PORT%, perfil pjud_cdp).
echo.
echo  EN ESA VENTANA DE CHROME:
echo    1) Pasa el CAPTCHA y entra a "Consulta Causas".
echo    2) Abre la pestana "Busqueda por Fecha".
echo    3) Competencia = CIVIL,  Corte = C.A. de Santiago,
echo       Fechas: Desde 01/01/2026  Hasta 31/01/2026.
echo    4) Espera la lista de Tribunales y haz UNA busqueda manual
echo       (confirma que SALEN resultados).
echo    5) Avisa a Claude "ready". (No cierres Chrome.)
echo.

start "" "%CHROME%" --remote-debugging-port=%PORT% --user-data-dir="%PROFILE%" --no-first-run --no-default-browser-check --start-maximized "%URL%"

echo  Chrome abierto. Puedes cerrar esta ventana negra (Chrome sigue).
exit /b 0
