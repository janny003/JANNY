#include "framework.h"
#include "OrobrosTest.h"
#include "OrobrosTestDlg.h"
#include <afxdlgs.h>
#include <vector>
#include <algorithm>
#include <fstream>
#include <cwctype>

#ifdef _DEBUG
#define new DEBUG_NEW
#endif

BEGIN_MESSAGE_MAP(COrobrosTestDlg, CDialogEx)
    ON_BN_CLICKED(IDC_BUTTON_START, &COrobrosTestDlg::OnBnClickedStart)
    ON_BN_CLICKED(IDC_BUTTON_SEND, &COrobrosTestDlg::OnBnClickedSend)
    ON_BN_CLICKED(IDC_BUTTON_STOP, &COrobrosTestDlg::OnBnClickedStop)
    ON_BN_CLICKED(IDC_BUTTON_LOAD_LOG, &COrobrosTestDlg::OnBnClickedLoadLog)
    ON_MESSAGE(WM_PIPE_OUTPUT, &COrobrosTestDlg::OnPipeOutput)
    ON_MESSAGE(WM_PROCESS_EXITED, &COrobrosTestDlg::OnProcessExited)
END_MESSAGE_MAP()

COrobrosTestDlg::COrobrosTestDlg(CWnd* pParent) : CDialogEx(IDD_OROBROSTEST_DIALOG, pParent) {}

void COrobrosTestDlg::DoDataExchange(CDataExchange* pDX)
{
    CDialogEx::DoDataExchange(pDX);
    DDX_Control(pDX, IDC_EDIT_COMMAND, m_commandEdit);
    DDX_Control(pDX, IDC_EDIT_CONTEXT, m_contextEdit);
    DDX_Control(pDX, IDC_EDIT_TRANSCRIPT, m_transcriptEdit);
    DDX_Control(pDX, IDC_EDIT_ANSWER, m_answerEdit);
    DDX_Control(pDX, IDC_BUTTON_START, m_startButton);
    DDX_Control(pDX, IDC_BUTTON_SEND, m_sendButton);
    DDX_Control(pDX, IDC_BUTTON_STOP, m_stopButton);
}

BOOL COrobrosTestDlg::OnInitDialog()
{
    CDialogEx::OnInitDialog();
    SetWindowText(L"OrobrosTest - Maintenance Report Runner");
    m_commandEdit.SetWindowText(L"\"C:\\Users\\yjs\\AppData\\Local\\hermes\\hermes-agent\\venv\\Scripts\\python.exe\" \"C:\\Users\\yjs\\Desktop\\JAN\\Policy\\OrobrosTest\\tools\\generate_maintenance_report.py\" --project-root \"C:\\Users\\yjs\\Desktop\\JAN\\Policy\\OrobrosTest\" --log-root \"C:\\Users\\yjs\\Desktop\\JAN\\LOG\" --out-doc \"C:\\Users\\yjs\\Desktop\\JAN\\Policy\\Data\\JAN_maintenance_report.docx\"");
    m_contextEdit.SetWindowText(L"우선점검: 시스템제어기조립체; 해결: (해결 시 조치항목 입력)");
    SetDlgItemTextW(IDC_BUTTON_LOAD_LOG, L"로그 읽기");
    m_sendButton.EnableWindow(FALSE);
    m_stopButton.EnableWindow(FALSE);
    AppendText(L"[Ready] Start를 누르면 전체 시험 로그를 읽어 이상탐지/원인분류/장기위험 예측 후 정비 Word 보고서를 생성합니다.\r\n");
    return TRUE;
}

CString COrobrosTestDlg::QuoteArg(const CString& s)
{
    CString out = L"\"";
    for (int i = 0; i < s.GetLength(); ++i) {
        if (s[i] == L'\"') out += L"\\\"";
        else out += s[i];
    }
    out += L"\"";
    return out;
}

CString COrobrosTestDlg::FormatWin32Error(DWORD error)
{
    LPWSTR buffer = nullptr;
    DWORD chars = FormatMessageW(
        FORMAT_MESSAGE_ALLOCATE_BUFFER | FORMAT_MESSAGE_FROM_SYSTEM | FORMAT_MESSAGE_IGNORE_INSERTS,
        nullptr,
        error,
        MAKELANGID(LANG_NEUTRAL, SUBLANG_DEFAULT),
        reinterpret_cast<LPWSTR>(&buffer),
        0,
        nullptr);

    CString message;
    if (chars && buffer) {
        message.Format(L"GetLastError=%lu (%s)", error, buffer);
        LocalFree(buffer);
    }
    else {
        message.Format(L"GetLastError=%lu", error);
    }
    message.Trim();
    return message;
}

CString COrobrosTestDlg::BuildCommandLine() const
{
    CString cmd, ctx;
    const_cast<CEdit&>(m_commandEdit).GetWindowText(cmd);
    const_cast<CEdit&>(m_contextEdit).GetWindowText(ctx);
    cmd.Trim();
    ctx.Trim();
    if (!ctx.IsEmpty()) {
        cmd += L" --operator-feedback ";
        cmd += QuoteArg(ctx);
    }
    return cmd;
}

CString COrobrosTestDlg::UpdateFocusLogArg(const CString& command, const CString& logPath)
{
    CString cmd = command;
    CString key = L"--focus-log";

    int pos = cmd.Find(key);
    while (pos >= 0) {
        int end = pos + key.GetLength();
        while (end < cmd.GetLength() && iswspace(cmd[end])) ++end;
        if (end < cmd.GetLength() && cmd[end] == L'\"') {
            ++end;
            while (end < cmd.GetLength() && cmd[end] != L'\"') ++end;
            if (end < cmd.GetLength()) ++end;
        }
        else {
            while (end < cmd.GetLength() && !iswspace(cmd[end])) ++end;
        }
        cmd.Delete(pos, end - pos);
        cmd.Trim();
        pos = cmd.Find(key);
    }

    if (!logPath.IsEmpty()) {
        cmd += L" --focus-log ";
        cmd += QuoteArg(logPath);
    }
    return cmd;
}

CString COrobrosTestDlg::LoadLogPreview(const CString& logPath, size_t maxBytes)
{
    std::ifstream in(CT2A(logPath, CP_UTF8), std::ios::binary);
    if (!in.is_open()) {
        return L"";
    }

    std::string raw;
    raw.resize(maxBytes);
    in.read(raw.data(), static_cast<std::streamsize>(maxBytes));
    raw.resize(static_cast<size_t>(in.gcount()));

    CString preview;
    if (!raw.empty()) {
        preview = Utf8ToWide(raw.data(), static_cast<int>(raw.size()));
        preview.Replace(L"\r", L"");
    }
    return preview;
}

void COrobrosTestDlg::AppendText(const CString& text)
{
    int len = m_transcriptEdit.GetWindowTextLength();
    m_transcriptEdit.SetSel(len, len);
    m_transcriptEdit.ReplaceSel(text);
}

CString COrobrosTestDlg::Utf8ToWide(const char* data, int len)
{
    if (len <= 0) return L"";
    int needed = MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS, data, len, nullptr, 0);
    UINT cp = CP_UTF8;
    DWORD flags = MB_ERR_INVALID_CHARS;
    if (needed <= 0) {
        cp = CP_ACP;
        flags = 0;
        needed = MultiByteToWideChar(cp, flags, data, len, nullptr, 0);
    }
    CString out;
    wchar_t* buf = out.GetBuffer(needed + 1);
    int written = MultiByteToWideChar(cp, flags, data, len, buf, needed);
    buf[written] = 0;
    out.ReleaseBuffer(written);
    return out;
}

bool COrobrosTestDlg::StartProcess(const CString& commandLine)
{
    // Ouroboros is a Python/Rich-based CLI.  When it is launched from a
    // Windows GUI process, Python may default stderr/stdout to the system ANSI
    // code page (CP949 on this machine). Rich prints Unicode spinner glyphs
    // such as U+280B while generating the Codex interview question, and CP949
    // cannot encode them. Force the child Python process to use UTF-8 so the
    // stdout/stderr pipes receive valid UTF-8 instead of crashing before the
    // first question is displayed.
    SetEnvironmentVariableW(L"PYTHONUTF8", L"1");
    SetEnvironmentVariableW(L"PYTHONIOENCODING", L"utf-8");
    SetEnvironmentVariableW(L"NO_COLOR", L"1");
    SetEnvironmentVariableW(L"TERM", L"dumb");

    SECURITY_ATTRIBUTES sa{};
    sa.nLength = sizeof(SECURITY_ATTRIBUTES);
    sa.bInheritHandle = TRUE;

    if (!CreatePipe(&m_childStdOutRd, &m_childStdOutWr, &sa, 0)) {
        DWORD err = GetLastError();
        AppendText(L"[ERROR] stdout pipe 생성 실패: " + FormatWin32Error(err) + L"\r\n");
        CloseProcessHandles();
        SetLastError(err);
        return false;
    }
    if (!SetHandleInformation(m_childStdOutRd, HANDLE_FLAG_INHERIT, 0)) {
        DWORD err = GetLastError();
        AppendText(L"[ERROR] stdout pipe inherit 설정 실패: " + FormatWin32Error(err) + L"\r\n");
        CloseProcessHandles();
        SetLastError(err);
        return false;
    }
    if (!CreatePipe(&m_childStdInRd, &m_childStdInWr, &sa, 0)) {
        DWORD err = GetLastError();
        AppendText(L"[ERROR] stdin pipe 생성 실패: " + FormatWin32Error(err) + L"\r\n");
        CloseProcessHandles();
        SetLastError(err);
        return false;
    }
    if (!SetHandleInformation(m_childStdInWr, HANDLE_FLAG_INHERIT, 0)) {
        DWORD err = GetLastError();
        AppendText(L"[ERROR] stdin pipe inherit 설정 실패: " + FormatWin32Error(err) + L"\r\n");
        CloseProcessHandles();
        SetLastError(err);
        return false;
    }

    STARTUPINFO si{};
    si.cb = sizeof(si);
    si.hStdError = m_childStdOutWr;
    si.hStdOutput = m_childStdOutWr;
    si.hStdInput = m_childStdInRd;
    si.dwFlags |= STARTF_USESTDHANDLES;

    CString mutableCmd = commandLine;
    BOOL ok = CreateProcessW(
        nullptr,
        mutableCmd.GetBuffer(),
        nullptr,
        nullptr,
        TRUE,
        CREATE_NO_WINDOW,
        nullptr,
        nullptr,
        &si,
        &m_pi);
    mutableCmd.ReleaseBuffer();

    CloseHandle(m_childStdOutWr); m_childStdOutWr = nullptr;
    CloseHandle(m_childStdInRd);  m_childStdInRd = nullptr;

    if (!ok) {
        DWORD err = GetLastError();
        CloseProcessHandles();
        SetLastError(err);
        return false;
    }

    m_running = true;
    m_readerThread = std::thread(&COrobrosTestDlg::ReaderLoop, this);
    return true;
}

void COrobrosTestDlg::ReaderLoop()
{
    char buffer[4096];
    DWORD read = 0;
    while (m_running && m_childStdOutRd) {
        BOOL ok = ReadFile(m_childStdOutRd, buffer, sizeof(buffer), &read, nullptr);
        if (!ok || read == 0) break;
        CString chunk = Utf8ToWide(buffer, static_cast<int>(read));
        PostMessage(WM_PIPE_OUTPUT, 0, reinterpret_cast<LPARAM>(new CString(chunk)));
    }
    PostMessage(WM_PROCESS_EXITED, 0, 0);
}

bool COrobrosTestDlg::WriteAnswer(const CString& answer)
{
    if (!m_running || !m_childStdInWr) return false;
    CString line = answer + L"\r\n";
    int bytesNeeded = WideCharToMultiByte(CP_UTF8, 0, line, line.GetLength(), nullptr, 0, nullptr, nullptr);
    std::vector<char> bytes(bytesNeeded);
    WideCharToMultiByte(CP_UTF8, 0, line, line.GetLength(), bytes.data(), bytesNeeded, nullptr, nullptr);
    DWORD written = 0;
    return WriteFile(m_childStdInWr, bytes.data(), static_cast<DWORD>(bytes.size()), &written, nullptr) && written == bytes.size();
}

void COrobrosTestDlg::MaybeShowQuestionDialog(const CString& chunk)
{
    CString currentCommand;
    m_commandEdit.GetWindowText(currentCommand);
    currentCommand.MakeLower();
    if (currentCommand.Find(L"ouroboros") < 0) {
        return;
    }

    CString trimmed = chunk;
    trimmed.Trim();
    if (trimmed.IsEmpty()) return;

    bool looksLikeQuestion =
        trimmed.Find(L"?") >= 0 ||
        trimmed.Find(L"질문") >= 0 ||
        trimmed.Find(L"Question") >= 0 ||
        trimmed.Find(L"Q:") >= 0;
    if (!looksLikeQuestion) return;
    if (trimmed == m_lastQuestionPopup) return;
    m_lastQuestionPopup = trimmed;

    CString prompt = trimmed;
    prompt += L"\r\n\r\n예를 누르면 '예', 아니요를 누르면 '아니요'가 Ouroboros stdin pipe로 전송됩니다.";

    int selected = MessageBox(prompt, L"Ouroboros 질문 - 답변 선택", MB_YESNO | MB_ICONQUESTION | MB_DEFBUTTON1);
    CString answer = (selected == IDYES) ? L"예" : L"아니요";

    AppendText(L"\r\n[DIALOG ANSWER] " + answer + L"\r\n");
    if (!WriteAnswer(answer)) {
        AppendText(L"[ERROR] Dialog 답변을 stdin pipe로 전송하지 못했습니다.\r\n");
        MessageBox(L"Dialog 답변을 stdin pipe로 전송하지 못했습니다.", L"전송 실패", MB_ICONERROR);
    }
}

bool COrobrosTestDlg::SaveCsvPostprocess(const CString& fullOutput, CString& savedPath, CString& error)
{
    CString text = fullOutput;
    int start = text.Find(L"CSV_START");
    if (start < 0) {
        error = L"CSV_START 마커를 찾지 못했습니다.";
        return false;
    }

    int end = text.Find(L"CSV_END", start);
    if (end < 0) {
        error = L"CSV_END 마커를 찾지 못했습니다.";
        return false;
    }

    CString csv = text.Mid(start + 9, end - (start + 9));
    csv.Replace(L"\r\n", L"\n");
    csv.Replace(L"\r", L"\n");
    csv.Trim();
    if (csv.IsEmpty()) {
        error = L"CSV 본문이 비어 있습니다.";
        return false;
    }

    savedPath = L"C:\\Users\\yjs\\Desktop\\JAN\\Policy\\Data\\latest_features.csv";

    int bytesNeeded = WideCharToMultiByte(CP_UTF8, 0, csv, csv.GetLength(), nullptr, 0, nullptr, nullptr);
    if (bytesNeeded <= 0) {
        error = L"CSV 인코딩(UTF-8) 변환 실패";
        return false;
    }

    std::vector<char> bytes(static_cast<size_t>(bytesNeeded));
    WideCharToMultiByte(CP_UTF8, 0, csv, csv.GetLength(), bytes.data(), bytesNeeded, nullptr, nullptr);

    HANDLE hFile = CreateFileW(savedPath, GENERIC_WRITE, FILE_SHARE_READ, nullptr, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, nullptr);
    if (hFile == INVALID_HANDLE_VALUE) {
        error = L"CSV 파일 생성 실패: " + FormatWin32Error(GetLastError());
        return false;
    }

    DWORD written = 0;
    BOOL ok = WriteFile(hFile, bytes.data(), static_cast<DWORD>(bytes.size()), &written, nullptr);
    CloseHandle(hFile);

    if (!ok || written != bytes.size()) {
        error = L"CSV 파일 쓰기 실패";
        return false;
    }

    return true;
}

LRESULT COrobrosTestDlg::OnPipeOutput(WPARAM, LPARAM lParam)
{
    std::unique_ptr<CString> text(reinterpret_cast<CString*>(lParam));
    AppendText(*text);
    m_capturedOutput += *text;
    MaybeShowQuestionDialog(*text);
    return 0;
}

LRESULT COrobrosTestDlg::OnProcessExited(WPARAM, LPARAM)
{
    DWORD exitCode = 0;
    bool haveExitCode = false;
    if (m_pi.hProcess) {
        WaitForSingleObject(m_pi.hProcess, 2000);
        haveExitCode = GetExitCodeProcess(m_pi.hProcess, &exitCode);
        if (haveExitCode && exitCode == STILL_ACTIVE) {
            haveExitCode = false;
        }
    }

    m_running = false;
    m_startButton.EnableWindow(TRUE);
    m_sendButton.EnableWindow(FALSE);
    m_stopButton.EnableWindow(FALSE);

    if (m_readerThread.joinable() && m_readerThread.get_id() != std::this_thread::get_id()) {
        m_readerThread.join();
    }

    if (m_childStdInWr) { CloseHandle(m_childStdInWr); m_childStdInWr = nullptr; }
    if (m_childStdOutRd) { CloseHandle(m_childStdOutRd); m_childStdOutRd = nullptr; }
    if (m_pi.hThread) { CloseHandle(m_pi.hThread); m_pi.hThread = nullptr; }
    if (m_pi.hProcess) { CloseHandle(m_pi.hProcess); m_pi.hProcess = nullptr; }

    CString msg;
    if (haveExitCode) {
        msg.Format(L"\r\n[Process exited or pipe closed] exit code=%lu\r\n", exitCode);
    }
    else {
        msg = L"\r\n[Process exited or pipe closed]\r\n";
    }
    AppendText(msg);

    if (m_capturedOutput.Find(L"CSV_START") >= 0 && m_capturedOutput.Find(L"CSV_END") >= 0) {
        CString savedPath;
        CString saveError;
        if (SaveCsvPostprocess(m_capturedOutput, savedPath, saveError)) {
            AppendText(L"[CSV SAVED] " + savedPath + L"\r\n");
        }
        else {
            AppendText(L"[CSV SAVE SKIPPED] " + saveError + L"\r\n");
        }
    }

    AppendText(L"[INFO] Send 버튼은 실행 중인 child process에만 활성화됩니다. Start 직후 꺼졌다면 transcript의 오류/종료 메시지를 확인하세요.\r\n");
    return 0;
}

void COrobrosTestDlg::OnBnClickedStart()
{
    if (m_running) return;
    CString cmd = BuildCommandLine();
    m_capturedOutput.Empty();
    AppendText(L"\r\n[START] ");
    AppendText(cmd + L"\r\n");
    if (!StartProcess(cmd)) {
        DWORD err = GetLastError();
        CString msg;
        msg.Format(L"프로세스 실행 실패. %s\r\n", FormatWin32Error(err).GetString());
        AppendText(msg);
        MessageBox(msg, L"실행 실패", MB_ICONERROR);
        return;
    }
    m_startButton.EnableWindow(FALSE);
    m_sendButton.EnableWindow(TRUE);
    m_stopButton.EnableWindow(TRUE);
}

void COrobrosTestDlg::OnBnClickedSend()
{
    CString answer;
    m_answerEdit.GetWindowText(answer);
    answer.Trim();
    if (answer.IsEmpty()) return;
    AppendText(L"\r\n[USER] " + answer + L"\r\n");
    if (!WriteAnswer(answer)) {
        MessageBox(L"stdin pipe로 답변 전송 실패", L"전송 실패", MB_ICONERROR);
    }
    m_answerEdit.SetWindowText(L"");
}

void COrobrosTestDlg::OnBnClickedStop()
{
    StopProcess();
}

void COrobrosTestDlg::OnBnClickedLoadLog()
{
    CFileDialog dlg(
        TRUE,
        L"txt",
        nullptr,
        OFN_FILEMUSTEXIST | OFN_PATHMUSTEXIST,
        L"Log Files (*.txt;*.TXT)|*.txt;*.TXT|All Files (*.*)|*.*||",
        this);

    dlg.m_ofn.lpstrInitialDir = L"C:\\Users\\yjs\\Desktop\\JAN\\LOG";

    if (dlg.DoModal() != IDOK) {
        return;
    }

    m_selectedLogPath = dlg.GetPathName();

    CString command;
    m_commandEdit.GetWindowText(command);
    command = UpdateFocusLogArg(command, m_selectedLogPath);
    m_commandEdit.SetWindowText(command);

    AppendText(L"\r\n[LOG SELECTED] " + m_selectedLogPath + L"\r\n");

    CString preview = LoadLogPreview(m_selectedLogPath);
    if (preview.IsEmpty()) {
        AppendText(L"[WARN] 로그 미리보기를 읽지 못했습니다. 파일 경로만 반영했습니다.\r\n");
    }
    else {
        if (preview.GetLength() > 400) {
            preview = preview.Left(400) + L"...";
        }
        AppendText(L"[LOG PREVIEW]\r\n" + preview + L"\r\n");
    }
}

void COrobrosTestDlg::StopProcess()
{
    if (m_pi.hProcess) TerminateProcess(m_pi.hProcess, 1);
    m_running = false;
    if (m_childStdOutRd) { CloseHandle(m_childStdOutRd); m_childStdOutRd = nullptr; }
    if (m_readerThread.joinable()) m_readerThread.join();
    CloseProcessHandles();
}

void COrobrosTestDlg::CloseProcessHandles()
{
    if (m_childStdInWr) { CloseHandle(m_childStdInWr); m_childStdInWr = nullptr; }
    if (m_childStdInRd) { CloseHandle(m_childStdInRd); m_childStdInRd = nullptr; }
    if (m_childStdOutWr) { CloseHandle(m_childStdOutWr); m_childStdOutWr = nullptr; }
    if (m_childStdOutRd) { CloseHandle(m_childStdOutRd); m_childStdOutRd = nullptr; }
    if (m_pi.hThread) { CloseHandle(m_pi.hThread); m_pi.hThread = nullptr; }
    if (m_pi.hProcess) { CloseHandle(m_pi.hProcess); m_pi.hProcess = nullptr; }
}
