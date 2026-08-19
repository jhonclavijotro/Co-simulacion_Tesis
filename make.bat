@echo off
rem Script de compatibilidad para comandos make en Windows
powershell -ExecutionPolicy Bypass -File "%~dp0make.ps1" %*
