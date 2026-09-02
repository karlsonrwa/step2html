@echo off
rem ---------------------------------------------------------------------------
rem  Start the step2html window.
rem
rem  On a machine with several Pythons, "python" need not be the one with OCP
rem  in it, and a window that cannot start says so in a console that closes
rem  in the same instant. This runs a Python you choose, from the project
rem  folder so the package is found, and - the part that matters - it keeps
rem  the console open when something goes wrong, so the reason can be read.
rem
rem  Set STEP2HTML_PYTHON to a full path to pick the interpreter, e.g.
rem      set STEP2HTML_PYTHON=C:\Python312\python.exe
rem  Otherwise "python" from PATH is used.
rem ---------------------------------------------------------------------------
setlocal
if not defined STEP2HTML_PYTHON set STEP2HTML_PYTHON=python

pushd "%~dp0"
"%STEP2HTML_PYTHON%" -m step2html.gui %*
if errorlevel 1 (
  echo.
  echo step2html stopped with an error. The lines above say why.
  echo The interpreter used was: %STEP2HTML_PYTHON%
  pause
)
popd
endlocal
