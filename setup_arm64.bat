@echo off
REM ============================================================
REM   Install native ARM64 Python and benchmark it against the
REM   current x64 (emulated) Python.
REM
REM   Double-click this file. Do NOT run it from an agent shell:
REM   installers launched from a sandboxed shell can land in an
REM   overlay that the real system never sees.
REM
REM   Keep this file pure ASCII. Batch files with non-ASCII text
REM   break under the OEM codepage.
REM ============================================================
setlocal
cd /d "%~dp0"

echo.
echo === Current Python (x64, emulated) ===
python benchmark_arch.py
if errorlevel 1 goto :fail
echo.

set "ARM_PY=%LOCALAPPDATA%\Programs\Python\Python314-arm64\python.exe"
if exist "%ARM_PY%" goto :haveit

echo === Native ARM64 Python not found. Installing. ===
echo.
echo Downloading the official python.org ARM64 installer...
set "INST=%TEMP%\python-3.14-arm64.exe"
curl -L -o "%INST%" https://www.python.org/ftp/python/3.14.4/python-3.14.4-arm64.exe
if errorlevel 1 (
  echo.
  echo Download failed. Check the version number at
  echo   https://www.python.org/downloads/windows/
  echo and look for the "Windows installer (ARM64)" link.
  goto :fail
)

echo Installing for the current user only, no PATH changes,
echo so your existing Python setup is left untouched...
"%INST%" /passive InstallAllUsers=0 PrependPath=0 Include_launcher=0 ^
    TargetDir="%LOCALAPPDATA%\Programs\Python\Python314-arm64"
if errorlevel 1 goto :fail

:haveit
echo.
echo === Installing packages into the ARM64 Python ===
"%ARM_PY%" -m pip install --upgrade pip --quiet
"%ARM_PY%" -m pip install numpy scipy scikit-learn astropy matplotlib emcee certifi --quiet
if errorlevel 1 goto :fail

echo.
echo === Native ARM64 Python ===
"%ARM_PY%" benchmark_arch.py
echo.
echo ============================================================
echo Compare the two tables above, line by line.
echo.
echo If ARM64 is meaningfully faster, run the pipeline with it:
echo   "%ARM_PY%" run_pipeline.py
echo   "%ARM_PY%" run_joint.py
echo ============================================================
goto :done

:fail
echo.
echo Something went wrong. See the messages above.

:done
echo.
pause
