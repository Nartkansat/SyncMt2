@echo off
chcp 65001 > nul
title SyncMT2 Versiyonlama ve Release Yoneticisi
python "%~dp0release.py" %*
pause
