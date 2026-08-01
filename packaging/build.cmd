@echo off
rem ---------------------------------------------------------------------------
rem  Build the standalone. Everything lands in dist\ and build\, both ignored.
rem
rem      packaging\build.cmd            one file, a window     (~82 MB)
rem      set STEP2HTML_ONEDIR=1         a folder               (~306 MB)
rem      set STEP2HTML_CONSOLE=1        a console build, for checking
rem
rem  Needs PyInstaller in the Python it runs with, and that Python must be the
rem  one with OCP in it - the build takes OCP from wherever it is imported.
rem
rem      python -m pip install pyinstaller
rem
rem  Set STEP2HTML_PYTHON to a full path to choose the interpreter.
rem ---------------------------------------------------------------------------
setlocal
if not defined STEP2HTML_PYTHON set STEP2HTML_PYTHON=python
set HERE=%~dp0

"%STEP2HTML_PYTHON%" -m PyInstaller --noconfirm ^
    --distpath "%HERE%..\dist" --workpath "%HERE%..\build" ^
    "%HERE%step2html.spec"

if errorlevel 1 (
  echo.
  echo The build failed. The lines above say why.
  echo The interpreter used was: %STEP2HTML_PYTHON%
  pause
) else (
  echo.
  echo Built into dist\. Check it with:
  echo     dist\step2html.exe --selftest ^<some.step^>
)
endlocal
