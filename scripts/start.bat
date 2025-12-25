@echo off
set "ROOT=%~dp0.."
pushd "%ROOT%"
python "%ROOT%\tools\pz_check_versions.py" --steamcmd "C:\steam_server\bin\steamcmd\steamcmd.exe"
popd
