@echo off
setlocal
REM ---------------------------------------------------------------------------
REM  Abrir_Worker.cmd <n> [fresh]   — abre el Chrome del worker <n> en modo CDP
REM
REM    n=1 -> puerto 9333, perfil pjud_cdp      (el veterano)
REM    n=2 -> puerto 9335, perfil pjud_cdp_w2
REM    n=3 -> puerto 9336, perfil pjud_cdp_w3
REM
REM  "fresh" renombra el perfil a un lado y empieza de cero. Un perfil que ya fue
REM  bloqueado DOS veces vale casi nada (rindio 121 -> 23 -> 2 causas el 22-07),
REM  asi que para una prueba limpia conviene 'fresh' + un calentamiento largo.
REM ---------------------------------------------------------------------------

set "N=%~1"
if "%N%"=="" set "N=1"
if "%N%"=="1" (set "PORT=9333" & set "PROFILE=%LOCALAPPDATA%\pjud_cdp")
if "%N%"=="2" (set "PORT=9335" & set "PROFILE=%LOCALAPPDATA%\pjud_cdp_w2")
if "%N%"=="3" (set "PORT=9336" & set "PROFILE=%LOCALAPPDATA%\pjud_cdp_w3")
if "%N%"=="4" (set "PORT=9337" & set "PROFILE=%LOCALAPPDATA%\pjud_cdp_w4")
if "%N%"=="5" (set "PORT=9338" & set "PROFILE=%LOCALAPPDATA%\pjud_cdp_w5")
if not defined PORT (
  echo  [ERROR] Worker "%N%" no valido. Usa 1..5.
  pause
  exit /b 1
)

set "CHROME=C:\Program Files\Google\Chrome\Application\chrome.exe"
if not exist "%CHROME%" set "CHROME=C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
if not exist "%CHROME%" (
  echo  [ERROR] No encuentro Google Chrome.
  pause
  exit /b 1
)

REM Sello dd-mm -> nombre del perfil viejo. Se calcula FUERA del bloque: dentro de
REM parentesis las variables se expanden al parsear, no al ejecutar.
for /f "tokens=1-3 delims=/-. " %%a in ("%DATE%") do set "STAMP=%%b%%a"
set "OLD=%PROFILE%.viejo-%STAMP%-%RANDOM%"
if /I "%~2"=="fresh" if exist "%PROFILE%" (
  echo  Renombrando perfil usado a: %OLD%
  move "%PROFILE%" "%OLD%" >nul 2>&1
  if errorlevel 1 echo  [AVISO] No pude renombrar. Cierra ESE Chrome primero y reintenta.
)

echo.
echo  Worker %N%  ·  puerto %PORT%  ·  perfil %PROFILE%
echo.
echo  CALENTAMIENTO (importante: el v3 puntua el COMPORTAMIENTO de la sesion,
echo  un perfil sin historia humana lo bloquean en la primera busqueda):
echo    1) Navega un rato por www.pjud.cl como una persona. Sin prisa.
echo    2) Entra a "Consulta Causas" desde pjud.cl (NO pegues la URL de la OJV).
echo    3) Pestana "Busqueda por Fecha": Competencia CIVIL, Corte C.A. de Santiago,
echo       Desde 01/01/2026  Hasta 31/01/2026.
echo    4) Haz 2 o 3 busquedas MANUALES, pasa un par de paginas con "Siguiente",
echo       y abre 2 o 3 causas a mano. Cierra cada modal.
echo    5) Dedicale 5 minutos de verdad. El perfil que sobrevivio las dos veces
echo       fue el que tenia el calentamiento largo.
echo    6) Deja la busqueda hecha y avisa a Claude: "worker %N% ready".
echo.

start "" "%CHROME%" --remote-debugging-port=%PORT% --user-data-dir="%PROFILE%" --no-first-run --no-default-browser-check --start-maximized "https://www.pjud.cl"

echo  Chrome abierto. Puedes cerrar esta ventana negra.
exit /b 0
