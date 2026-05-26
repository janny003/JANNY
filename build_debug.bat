@echo off
call "C:\Program Files\Microsoft Visual Studio\2022\Professional\VC\Auxiliary\Build\vcvars64.bat"
if errorlevel 1 exit /b %errorlevel%
msbuild "C:\Users\kangd\Desktop\OrobrosTest\OrobrosTest.sln" /p:Configuration=Debug /p:Platform=x64 /m
exit /b %errorlevel%
