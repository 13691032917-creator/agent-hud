@echo off
REM Launch Agent HUD floating window
setlocal
set "SCRIPT_DIR=%~dp0"
if defined MIMO_PYTHON (
  start "" "%MIMO_PYTHON%" "%SCRIPT_DIR%start_hud.py"
  goto :eof
)
where python >nul 2>nul && (
  start "" python "%SCRIPT_DIR%start_hud.py"
  goto :eof
)
where py >nul 2>nul && (
  start "" py "%SCRIPT_DIR%start_hud.py"
  goto :eof
)
echo Python not found. Set MIMO_PYTHON or install Python 3.
pause
