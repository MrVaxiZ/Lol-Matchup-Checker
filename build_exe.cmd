@echo off
rem Builds "dist\LoL Matchup Checker.exe" (one file you can give to anyone).
cd /d "%~dp0"
echo Installing build tools...
python -m pip install --upgrade pyinstaller || goto :error
python -m pip install -e . || goto :error
echo Building the exe (takes a few minutes)...
python -m PyInstaller --noconfirm --clean --distpath dist --workpath build packaging\LoLMatchupChecker.spec || goto :error
echo Checking the exe...
start /wait "" "dist\LoL Matchup Checker.exe" --selftest
type "dist\selftest.txt"
echo.
echo Done: dist\LoL Matchup Checker.exe
pause
exit /b 0
:error
echo Build failed, see the messages above.
pause
exit /b 1
