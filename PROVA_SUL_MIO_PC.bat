@echo off
chcp 65001 >nul
setlocal
title Prova canali S4Me sul mio PC
echo.
echo  Prova dei canali S4Me con il tuo indirizzo italiano
echo  ----------------------------------------------------
echo.

rem 1) Python
where python >nul 2>nul
if errorlevel 1 (
  echo Python non trovato: provo a installarlo con winget...
  winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements
  echo.
  echo Python e stato installato. CHIUDI questa finestra e rilancia di nuovo il file.
  pause
  exit /b 0
)

rem 2) Scarica il progetto
set "CARTELLA=%USERPROFILE%\S4me-prova"
if not exist "%CARTELLA%" mkdir "%CARTELLA%"
echo Scarico il progetto da GitHub...
powershell -NoProfile -Command "Invoke-WebRequest -UseBasicParsing 'https://github.com/aandroide/S4me-gen/archive/refs/heads/master.zip' -OutFile '%CARTELLA%\progetto.zip'"
if errorlevel 1 (
  echo Download non riuscito. Controlla la connessione e riprova.
  pause
  exit /b 1
)
powershell -NoProfile -Command "Expand-Archive -Force '%CARTELLA%\progetto.zip' '%CARTELLA%'"
set "PROGETTO=%CARTELLA%\S4me-gen-master"

rem 3) Prova
cd /d "%PROGETTO%"
echo.
echo Provo tutti i canali (ci vuole un po', lascia aperta la finestra)...
echo.
python prova_locale.py tutti

rem 4) Risultati
echo.
if exist "%PROGETTO%\prove_locali.zip" (
  copy /Y "%PROGETTO%\prove_locali.zip" "%USERPROFILE%\Desktop\prove_locali.zip" >nul
  echo Fatto. Ho messo prove_locali.zip sul Desktop: mandalo a Claude.
) else (
  echo Qualcosa e andato storto: non trovo prove_locali.zip.
)
echo.
pause
endlocal
