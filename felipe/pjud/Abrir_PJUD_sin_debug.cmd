@echo off
setlocal
title PJUD - Abrir Chrome (SIN puerto de depuracion)

REM Opens Chrome normally (NO --remote-debugging-port) with the PJUD profile, which
REM carries the "Iniciar scraping" button. The button does the whole scrape IN-PAGE
REM (JavaScript in your own session) and downloads the results as a JSON file.
REM No debug port, no Python driving the browser.

set "PROFILE=%LOCALAPPDATA%\pjud_chrome"
set "SEED=%~dp0inpage"
set "URL=https://oficinajudicialvirtual.pjud.cl/home/index.php"

REM --- Instala/actualiza el boton "Iniciar scraping" en el perfil PJUD ---
REM (el boton vive en el perfil local, no en el repo; aqui se copia desde inpage\)
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
echo  PASOS:
echo    1) Entra a "Consulta Unificada" y pasa la entrada hasta el formulario.
echo    2) Abre la pestana "Busqueda por Fecha".
echo    3) Pulsa el boton  "Iniciar scraping"  en la barra de marcadores.
echo       (El scraping ocurre dentro de la pagina y descarga un archivo JSON.)
echo.
echo  (Si no ves la barra de marcadores, pulsa Ctrl+Shift+B.)
echo.

start "" "%CHROME%" --user-data-dir="%PROFILE%" --no-first-run --no-default-browser-check --restore-last-session=false "%URL%"

echo  Chrome abierto. Puedes cerrar esta ventana.
exit /b 0
