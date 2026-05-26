@echo off
call "C:\Program Files\Microsoft Visual Studio\2022\Professional\VC\Auxiliary\Build\vcvars64.bat"
if errorlevel 1 exit /b %errorlevel%
cl /nologo /EHsc /std:c++17 /utf-8 /Fe:"C:\Users\kangd\Desktop\OrobrosTest\x64\Debug\PipeSelfTest.exe" "C:\Users\kangd\Desktop\OrobrosTest\PipeSelfTest.cpp"
if errorlevel 1 exit /b %errorlevel%
"C:\Users\kangd\Desktop\OrobrosTest\x64\Debug\PipeSelfTest.exe"
exit /b %errorlevel%
