@echo off
setlocal
title PJUD - Abrir Chrome (SIN puerto de depuracion)

REM Abre UNA ventana de Chrome (en www.google.cl) con el perfil PJUD, que
REM lleva el boton "Iniciar scraping". NO navega a PJUD: tu abres el sitio
REM y pasas la entrada/CAPTCHA. El scraping ocurre IN-PAGE y descarga un JSON.
REM Sin puerto de depuracion, sin Python.

set "PROFILE=%LOCALAPPDATA%\pjud_chrome"
set "SEED=%~dp0inpage"

REM --- Instala/actualiza el boton "Iniciar scraping" en el perfil PJUD ---
if not exist "%PROFILE%\Default" mkdir "%PROFILE%\Default"
if exist "%SEED%\Bookmarks" copy /Y "%SEED%\Bookmarks" "%PROFILE%\Default\Bookmarks" >nul
if not exist "%PROFILE%\Default\Preferences" if exist "%SEED%\Preferences" copy /Y "%SEED%\Preferences" "%PROFILE%\Default\Preferences" >nul
if exist "%PROFILE%\Default\Bookmarks.bak" del /Q "%PROFILE%\Default\Bookmarks.bak" >nul 2>&1

set "CHROME=C:\Program Files\Google\Chrome\Application\chrome.exe"
if not exist "%CHROME%" set "CHROME=C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
if not exist "%CHROME%" (
  echo [ERROR] No encuentro Google Chrome. Instalalo y reintenta.
  echo.
  pause
  exit /b 1
)

echo.
echo  =====================================================
echo    PJUD  -  Abrir Chrome  (SIN puerto de depuracion)
echo  =====================================================
echo.
echo  Mes configurado actualmente: ENERO 2026.
echo.
echo  PASOS (TU configuras la busqueda; el scraper solo recorre los Tribunales):
echo    1) Entra a "Consulta Unificada" y pasa la entrada / CAPTCHA. Lo haces tu.
echo    2) Abre la pestana "Busqueda por Fecha".
echo    3) Elige Competencia = CIVIL, la CORTE, y escribe las FECHAS (Desde / Hasta).
echo       Espera a que aparezca la lista de Tribunales.
echo    4) Pulsa el boton  "Iniciar scraping"  en la barra de marcadores.
echo       (Recorre los Tribunales de esa corte y descarga un archivo JSON.)
echo.
echo  (Si no ves la barra de marcadores, pulsa Ctrl+Shift+B.)
echo.

start "" "%CHROME%" --user-data-dir="%PROFILE%" --no-first-run --no-default-browser-check --restore-last-session=false "https://www.google.cl"

echo  Chrome abierto. Puedes cerrar esta ventana.
exit /b 0
