@echo off
setlocal

set "ROOT=%~dp0"
set "VENV=%ROOT%.venv"

echo.
echo Checking Python...

where py >nul 2>nul
if %errorlevel%==0 (
  set "PYTHON_CMD=py -3.10"
) else (
  where python >nul 2>nul
  if %errorlevel%==0 (
    set "PYTHON_CMD=python"
  ) else (
    echo Python not found. Please install Python 3.10+ and try again.
    pause
    exit /b 1
  )
)

echo.
echo Creating Neo Studio venv...
%PYTHON_CMD% -m venv "%VENV%"
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
"%VENV%\Scripts\python.exe" -m pip install -r "%ROOT%neo_studio_requirements_core.txt"
if errorlevel 1 (
  echo Failed while installing core requirements.
  pause
  exit /b 1
)

echo.
echo Done.
echo Core environment ready at:
echo "%VENV%"
echo.
pause
endlocal