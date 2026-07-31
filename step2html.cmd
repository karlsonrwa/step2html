@echo off
rem ---------------------------------------------------------------------------
rem  Start the step2html window.
rem
rem  Double-clicking gui.py hands it to whichever Python the .py association
rem  picks, and on a machine with several that need not be the one with OCP in
rem  it. This runs a Python you choose, and - the part that matters - it keeps
rem  the console open when something goes wrong, so the reason can be read.
rem
rem  Set STEP2HTML_PYTHON to a full path to pick the interpreter, e.g.
rem      set STEP2HTML_PYTHON=C:\Python312\python.exe
rem  Otherwise "python" from PATH is used.
rem ---------------------------------------------------------------------------
setlocal
if not defined STEP2HTML_PYTHON set STEP2HTML_PYTHON=python

"%STEP2HTML_PYTHON%" "%~dp0gui.py" %*
if errorlevel 1 (
  echo.
  echo step2html stopped with an error. The lines above say why.
  echo The interpreter used was: %STEP2HTML_PYTHON%
  pause
)
endlocal
