@echo off
setlocal
cd /d "%~dp0"
title Enriquecedor de Patentes - JPL

echo.
echo  ================================================
echo    ENRIQUECEDOR DE PATENTES  (Juzgado Policia Local)
echo  ================================================
echo.
echo  Se abrira una ventana de navegador. La PRIMERA vez,
echo  resuelve el captcha de Cloudflare UNA sola vez: despues
echo  queda guardado y el proceso continua solo.
echo.

REM --- 1. Buscar Python ---------------------------------------------
set "PY="
where py     >nul 2>&1 && set "PY=py"
if not defined PY where python >nul 2>&1 && set "PY=python"
if not defined PY (
  echo  [ERROR] No encuentro Python en este PC.
  echo          Instalalo desde https://www.python.org/downloads/
  echo          y marca "Add Python to PATH" durante la instalacion.
  echo.
  pause
  exit /b 1
)

REM --- 2. Entorno aislado (per-PC, FUERA de la carpeta sincronizada) -
REM  Un venv NO se puede compartir entre PCs: tiene rutas absolutas del
REM  usuario/Python de la maquina que lo creo. Por eso lo creamos en una ruta
REM  LOCAL de este PC (%LOCALAPPDATA%), no en la carpeta del repo (que se
REM  sincroniza con Drive). Asi cada PC tiene el suyo y nunca chocan.
set "VENV=%LOCALAPPDATA%\jpl_patentes_venv"
if exist "%VENV%\Scripts\python.exe" goto haveenv
echo  [preparando] Instalando dependencias. Solo la 1a vez; puede tardar
echo               unos minutos. Dejalo trabajar...
%PY% -m venv "%VENV%"
if errorlevel 1 goto fail
call "%VENV%\Scripts\activate.bat"
python -m pip install --upgrade pip >nul
pip install -r requirements.txt
if errorlevel 1 goto fail
REM No browser download needed: we drive your real Google Chrome (the only thing
REM that gets past patentechile's Cloudflare check).
goto envready
:haveenv
call "%VENV%\Scripts\activate.bat"
:envready

REM --- 3. Credenciales de Google -----------------------------------
if not exist "jpl_config.json"    set "MISS=jpl_config.json"
if not exist "jpl_config.json"    goto miss
if not exist "client_secret.json" set "MISS=client_secret.json"
if not exist "client_secret.json" goto miss
if not exist "token.json" (
  echo  [aviso] No hay sesion de Google guardada en este PC.
  echo          Abro el navegador para iniciar sesion una sola vez...
  python run.py --setup
  if errorlevel 1 goto fail
)

REM --- 4. Ejecutar el enriquecedor ---------------------------------
echo.
echo  [listo] Iniciando. Deja ESTA ventana abierta mientras trabaja.
echo          - Enriquece las patentes pendientes y sigue vigilando.
echo          - Cierra la ventana cuando termines o para detenerlo.
echo.
python patente_watcher.py
echo.
echo  --- Proceso terminado ---
pause
exit /b 0

:miss
echo.
echo  [ERROR] Falta el archivo  %MISS%  en esta carpeta:
echo          %cd%
echo.
echo  Es un archivo privado (no se guarda en GitHub). Copialo desde
echo  tu otro PC, de la misma carpeta  felipe\scraper , y vuelve a
echo  ejecutar este acceso.
echo.
pause
exit /b 1

:fail
echo.
echo  [ERROR] Fallo la preparacion. Revisa los mensajes de arriba.
echo.
pause
exit /b 1
