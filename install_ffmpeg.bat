@echo off

powershell .\install_winget.ps1

net.exe session 1>NUL 2>NUL && (
    goto gotAdmin
) || (
    goto UACPrompt
)
        
:UACPrompt  
    echo Set UAC = CreateObject^("Shell.Application"^) > "%temp%\getadmin.vbs" 
    echo UAC.ShellExecute "%~s0", "", "", "runas", 1 >> "%temp%\getadmin.vbs" 
    "%temp%\getadmin.vbs" 
    exit /B

:gotAdmin  
    if exist "%temp%\getadmin.vbs" ( del "%temp%\getadmin.vbs" )


winget install ffmpeg

PAUSE