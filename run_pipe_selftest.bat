@echo off
setlocal
set "ROOT=C:\Users\yjs\Desktop\JAN\OrobrosTest"
call "C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars64.bat"
if errorlevel 1 exit /b %errorlevel%
cl /nologo /EHsc /std:c++17 /utf-8 /Fe:"%ROOT%\x64\Debug\PipeSelfTest.exe" "%ROOT%\PipeSelfTest.cpp"
if errorlevel 1 exit /b %errorlevel%
"%ROOT%\x64\Debug\PipeSelfTest.exe"
exit /b %errorlevel%
