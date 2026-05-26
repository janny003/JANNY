#define UNICODE
#define _UNICODE
#include <windows.h>
#include <string>
#include <iostream>
#include <vector>
#include <filesystem>

static void CloseIf(HANDLE& h) {
    if (h && h != INVALID_HANDLE_VALUE) {
        CloseHandle(h);
        h = nullptr;
    }
}

static bool WriteLine(HANDLE h, const std::string& s) {
    std::string line = s + "\r\n";
    DWORD written = 0;
    return WriteFile(h, line.data(), static_cast<DWORD>(line.size()), &written, nullptr) && written == line.size();
}

int wmain() {
    SECURITY_ATTRIBUTES sa{};
    sa.nLength = sizeof(sa);
    sa.bInheritHandle = TRUE;

    HANDLE outRd = nullptr, outWr = nullptr, inRd = nullptr, inWr = nullptr;
    if (!CreatePipe(&outRd, &outWr, &sa, 0) || !SetHandleInformation(outRd, HANDLE_FLAG_INHERIT, 0)) {
        std::cerr << "Create stdout pipe failed\n";
        return 1;
    }
    if (!CreatePipe(&inRd, &inWr, &sa, 0) || !SetHandleInformation(inWr, HANDLE_FLAG_INHERIT, 0)) {
        std::cerr << "Create stdin pipe failed\n";
        return 1;
    }

    STARTUPINFOW si{};
    si.cb = sizeof(si);
    si.dwFlags = STARTF_USESTDHANDLES;
    si.hStdOutput = outWr;
    si.hStdError = outWr;
    si.hStdInput = inRd;

    PROCESS_INFORMATION pi{};
    wchar_t exePath[MAX_PATH] = {0};
    GetModuleFileNameW(nullptr, exePath, MAX_PATH);
    std::filesystem::path mockPath = std::filesystem::path(exePath).parent_path().parent_path().parent_path() / L"mock_ouroboros.py";
    std::wstring cmd = L"python \"" + mockPath.wstring() + L"\"";
    BOOL ok = CreateProcessW(nullptr, cmd.data(), nullptr, nullptr, TRUE, CREATE_NO_WINDOW, nullptr, nullptr, &si, &pi);
    CloseIf(outWr);
    CloseIf(inRd);
    if (!ok) {
        std::cerr << "CreateProcess failed: " << GetLastError() << "\n";
        CloseIf(outRd); CloseIf(inWr);
        return 1;
    }

    std::vector<std::string> answers = {"MFC pipe bridge", "question-answer roundtrip", "Desktop/OrobrosTest"};
    size_t answerIndex = 0;
    std::string transcript;
    char buf[512];
    DWORD read = 0;
    while (ReadFile(outRd, buf, sizeof(buf), &read, nullptr) && read > 0) {
        std::string chunk(buf, buf + read);
        transcript += chunk;
        std::cout << chunk;
        if (chunk.find("Question") != std::string::npos && answerIndex < answers.size()) {
            if (!WriteLine(inWr, answers[answerIndex++])) {
                std::cerr << "Write answer failed\n";
                break;
            }
        }
    }

    CloseIf(inWr);
    WaitForSingleObject(pi.hProcess, 5000);
    DWORD code = 0;
    GetExitCodeProcess(pi.hProcess, &code);
    CloseIf(pi.hThread); CloseIf(pi.hProcess); CloseIf(outRd);

    bool pass = code == 0
        && transcript.find("Question 1") != std::string::npos
        && transcript.find("received: MFC pipe bridge") != std::string::npos
        && transcript.find("Interview completed") != std::string::npos;
    std::cout << "\nSELFTEST " << (pass ? "PASS" : "FAIL") << "\n";
    return pass ? 0 : 2;
}
