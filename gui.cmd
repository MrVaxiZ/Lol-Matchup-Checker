@echo off
rem Opens the LoL Matchup Checker window. Excel files are saved in this folder.
cd /d "%~dp0"
where pythonw >nul 2>nul && (start "" pythonw -m lol_matchup_checker.gui) || (python -m lol_matchup_checker.gui)
