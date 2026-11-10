/* VDPatch.exe: sets the Large Address Aware flag (4 GB of memory instead of 2 GB for the 32-bit game)
   in VD_BHIKKHUNI.exe next to it - the only change the mod makes to the exe file. Windows reads the
   flag before any DLL loads, so dinput8.dll cannot do it in memory; it offers to run this instead
   when a Steam update/verify removed the flag.
     VDPatch.exe              set the flag, show the result
     VDPatch.exe --wait PID   (used by dinput8.dll) wait for the game to close, set it, restart via Steam */
#include <windows.h>
#include <shellapi.h>
#include <stdio.h>
#include <stdlib.h>

#include "version.h"
#define TITLE MOD_NAME

static int set_laa(const char *exe) {                      /* 1 = set, 2 = was set, 0 = error */
    IMAGE_DOS_HEADER dos; DWORD sig, n; IMAGE_FILE_HEADER fh; HANDLE f = INVALID_HANDLE_VALUE; int i, r = 0;
    for (i = 0; i < 50 && f == INVALID_HANDLE_VALUE; i++) {  /* the closing game may hold it briefly */
        f = CreateFileA(exe, GENERIC_READ | GENERIC_WRITE, 0, 0, OPEN_EXISTING, 0, 0);
        if (f == INVALID_HANDLE_VALUE) { if (GetLastError() != ERROR_SHARING_VIOLATION) return 0; Sleep(100); }
    }
    if (f == INVALID_HANDLE_VALUE) return 0;
    if (ReadFile(f, &dos, sizeof dos, &n, 0) && n == sizeof dos && dos.e_magic == IMAGE_DOS_SIGNATURE &&
        SetFilePointer(f, dos.e_lfanew, 0, FILE_BEGIN) == (DWORD)dos.e_lfanew &&
        ReadFile(f, &sig, 4, &n, 0) && sig == IMAGE_NT_SIGNATURE &&
        ReadFile(f, &fh, sizeof fh, &n, 0) && n == sizeof fh && fh.Machine == IMAGE_FILE_MACHINE_I386) {
        if (fh.Characteristics & IMAGE_FILE_LARGE_ADDRESS_AWARE) r = 2;
        else {
            fh.Characteristics |= IMAGE_FILE_LARGE_ADDRESS_AWARE;
            SetFilePointer(f, dos.e_lfanew + 4, 0, FILE_BEGIN);
            r = WriteFile(f, &fh, sizeof fh, &n, 0) && n == sizeof fh;
        }
    }
    CloseHandle(f);
    return r;
}

int WINAPI WinMain(HINSTANCE inst, HINSTANCE prev, LPSTR cmdline, int show) {
    char exe[MAX_PATH], msg[MAX_PATH + 200], *p; int r, wait = __argc >= 3 && !strcmp(__argv[1], "--wait");
    GetModuleFileNameA(0, exe, MAX_PATH);
    p = strrchr(exe, '\\'); strcpy_s(p + 1, MAX_PATH - (p + 1 - exe), "VD_BHIKKHUNI.exe");
    if (wait) {
        HANDLE h = OpenProcess(SYNCHRONIZE, FALSE, strtoul(__argv[2], 0, 10));
        if (h) { WaitForSingleObject(h, 30000); CloseHandle(h); }
    }
    r = set_laa(exe);
    if (!r) {
        sprintf_s(msg, sizeof msg, "Could not set the flag in\n%s\n\nClose the game and run VDPatch.exe again.", exe);
        MessageBoxA(0, msg, TITLE, MB_OK | MB_ICONERROR);
        return 1;
    }
    if (wait) ShellExecuteA(0, "open", "steam://rungameid/550080", 0, 0, SW_SHOWNORMAL);
    else MessageBoxA(0, r == 1 ? "Large Address Aware is now set in VD_BHIKKHUNI.exe (4 GB of memory)."
                               : "Large Address Aware was already set in VD_BHIKKHUNI.exe.", TITLE, MB_OK | MB_ICONINFORMATION);
    return 0;
}
