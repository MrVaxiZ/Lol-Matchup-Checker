@echo off
rem Publishes a new version: bumps the version, commits, tags and pushes.
rem GitHub then builds the exe and creates the release by itself.
cd /d "%~dp0"
python packaging\release.py %*
pause
