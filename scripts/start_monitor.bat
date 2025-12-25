@echo off
set "ROOT=%~dp0.."
pushd "%ROOT%"
python "%ROOT%\main.py"
popd
