@echo off
setlocal
cd /d "%~dp0"
title PJUD - Relleno de causas (Consulta Causas)

echo.
echo  ===============================================
echo    PJUD  -  Relleno de causas  (Consulta Causas)
echo  ===============================================
echo.
echo  Se abrira una ventana de Chrome. Entra a "Consulta Causas"
echo  (resuelve el CAPTCHA si aparece); despues el proceso sigue solo.
echo  Deja ESTA ventana y la de Chrome abiertas mientras trabaja.
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
REM  Un venv NO se puede compartir entre PCs (rutas absolutas). Lo creamos
REM  en una ruta LOCAL de este PC, no en la carpeta del repo (Drive).
REM  No hace falta descargar navegador: manejamos tu Google Chrome real.
set "VENV=%LOCALAPPDATA%\pjud_venv"
if exist "%VENV%\Scripts\python.exe" goto haveenv
echo  [preparando] Instalando dependencias. Solo la 1a vez; puede tardar
echo               unos minutos. Dejalo trabajar...
%PY% -m venv "%VENV%"
if errorlevel 1 goto fail
call "%VENV%\Scripts\activate.bat"
python -m pip install --upgrade pip >nul
pip install -r requirements.txt
if errorlevel 1 goto fail
goto envready
:haveenv
call "%VENV%\Scripts\activate.bat"
:envready

REM --- 3. Credenciales privadas (no estan en GitHub) ---------------
for %%F in (pjud_config.json client_secret.json token.json) do (
  if not exist "%%F" (
    echo.
    echo  [ERROR] Falta el archivo  %%F  en:
    echo          %cd%
    echo  Es privado (no se guarda en GitHub). Copialo desde el otro PC
    echo  o deja que Drive lo sincronice, y vuelve a ejecutar.
    echo.
    pause
    exit /b 1
  )
)

REM --- 4. Ejecutar el relleno de enero -----------------------------
echo.
echo  [listo] Iniciando el relleno (enero 2026, sin GPS).
echo.
python run.py --fill --year 2026 --month 1 --skip-geo
echo.
echo  --- Proceso terminado ---
pause
exit /b 0

:fail
echo.
echo  [ERROR] Fallo la preparacion. Revisa los mensajes de arriba.
echo.
pause
exit /b 1
