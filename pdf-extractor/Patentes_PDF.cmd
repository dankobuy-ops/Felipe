@echo off
setlocal
cd /d "C:\Claude\pdf-extractor"
echo ============================================================
echo   Extractor de PATENTES desde PDF escaneados (JPL)
echo   Lee la patente con OCR y cruza Rol / Tribunal / RUT del
echo   demandado desde los datos del scraper. Escribe la planilla.
echo ============================================================
echo.

rem  Uso:
rem   - Doble clic: procesa la carpeta  inbox\  (copia ahi tus PDFs)
rem   - O arrastra una CARPETA de PDFs sobre este .cmd

if "%~1"=="" (
  echo Procesando carpeta por defecto:  inbox\
  echo  ^(copia tus PDFs en  C:\Claude\pdf-extractor\inbox\  y vuelve a ejecutar^)
  echo.
  python run_extract.py "inbox"
) else (
  echo Procesando carpeta:  %~1
  echo.
  python run_extract.py "%~1"
)
if errorlevel 1 goto :err

echo.
echo Subiendo patentes nuevas a la planilla de Google...
python sheet.py
if errorlevel 1 goto :err

echo.
echo LISTO. Tambien se guardo un CSV en  out\patentes_extraidas.csv
echo.
pause
exit /b 0

:err
echo.
echo *** Ocurrio un ERROR. Revisa los mensajes de arriba. ***
echo.
pause
exit /b 1
