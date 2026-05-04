@echo off
setlocal

set "PYTHON_EXE=C:\Users\lakma\AppData\Local\Programs\Python\Python310\python.exe"
set "ROOT=F:\MyTools\00 Neo_Studio"
set "VENV=%ROOT%\.venv"

if not exist "%PYTHON_EXE%" (
  echo Python not found:
  echo %PYTHON_EXE%
  pause
  exit /b 1
)

if not exist "%ROOT%" (
  echo Root folder not found:
  echo %ROOT%
  pause
  exit /b 1
)

echo.
echo Creating Neo Studio venv...
"%PYTHON_EXE%" -m venv "%VENV%"
if errorlevel 1 (
  echo Failed to create venv.
  pause
  exit /b 1
)

echo.
echo Upgrading pip tooling...
"%VENV%\Scripts\python.exe" -m pip install --upgrade pip setuptools wheel
if errorlevel 1 (
  echo Failed while upgrading pip tooling.
  pause
  exit /b 1
)

echo.
echo Installing core requirements...
"%VENV%\Scripts\python.exe" -m pip install -r "%~dp0neo_studio_requirements_core.txt"
if errorlevel 1 (
  echo Failed while installing core requirements.
  pause
  exit /b 1
)

echo.
echo Done.
echo.
echo Core environment ready at:
 echo %VENV%
echo.
echo Optional extras can be installed later with:
 echo "%VENV%\Scripts\python.exe" -m pip install -r "%~dp0neo_studio_requirements_optional.txt"
echo.
pause
endlocal
