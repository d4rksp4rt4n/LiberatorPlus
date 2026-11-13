/* dinput8.dll proxy for VD_BHIKKHUNI.exe (Steam, 32-bit): the mod's exe fixes, applied in memory at
   every game start, each switched on/off in vdmod.ini (next to this DLL). The exe on disk stays
   original except for the Large Address Aware flag, which Windows reads before any DLL is loaded:
   Set4GB.bat sets it; this DLL says so when a Steam update/verify removed it.
   Every edit first checks the original bytes; on a mismatch (other game version) that fix is
   skipped. Results of the last start: vdmod.log.   Build: build.bat (MSVC x86). */
#include <windows.h>
#include <stdio.h>
#include <stdarg.h>
#include <stdlib.h>
#include <dxgi.h>
#include <d3d11.h>
#include "zoom.h"
#include "centroid.h"
#include "version.h"

#define VA(x) (base + ((x) - 0x400000))
static BYTE *base;

/* Steam branches: addresses that differ between the builds (all others are the same in both).
   Picked by the exe's link time stamp; an unknown build uses the public addresses, and the byte
   checks below then skip whatever does not match. */
typedef struct {
    const char *name; DWORD stamp;
    DWORD fps_words, dlc_site, phys_jmp, phys_step, ad_mgr, vsync_mgr, res_site;
} Build;
static const Build builds[] = {
    {"public v1.05", 0x59ee8bb1, 0x8eac90, 0x6d886c, 0x8914bb, 0x8914d0, 0xc3fec4, 0xc3fe90, 0x86959b},
    {"beta v1.06",   0x5a260c26, 0x8eac70, 0x6d888c, 0x89123b, 0x891250, 0xc3fed0, 0xc3feb0, 0x86932b},
};
static const Build *bld = &builds[0];
static char dir[MAX_PATH], ini[MAX_PATH], logbuf[4096];

static int opt(const char *key, int def) { return GetPrivateProfileIntA("VDMod", key, def, ini); }

static void say(const char *fmt, ...) {
    size_t n = strlen(logbuf); va_list a;
    va_start(a, fmt); vsnprintf(logbuf + n, sizeof logbuf - n, fmt, a); va_end(a);
}

static void save_log(void) {
    char path[MAX_PATH]; FILE *f;
    sprintf_s(path, MAX_PATH, "%svdmod.log", dir);
    if (!fopen_s(&f, path, "w")) { fputs(logbuf, f); fclose(f); }
}

static void put(BYTE *p, const void *src, int n) {
    DWORD old;
    VirtualProtect(p, n, PAGE_EXECUTE_READWRITE, &old);
    memcpy(p, src, n);
    VirtualProtect(p, n, old, &old);
    FlushInstructionCache(GetCurrentProcess(), p, n);
}

static int is(DWORD va, const char *bytes, int n) { return !memcmp(VA(va), bytes, n); }

static void call_at(DWORD va, void *fn, int len) {        /* call fn + nop padding over len bytes */
    BYTE b[16];
    b[0] = 0xe8; *(int *)(b + 1) = (int)((BYTE *)fn - (VA(va) + 5));
    memset(b + 5, 0x90, len - 5);
    put(VA(va), b, len);
}

static BYTE *call_target(DWORD va) { BYTE *p = VA(va); return p[0] == 0xe8 ? p + 5 + *(int *)(p + 1) : 0; }

/* ---- GalleryHDFit: the gallery sizes the picture from the texture; 2x/3x/4x CGs (height k*544)
   would show zoomed in -> divide the sprite width/height by k. Other pictures are untouched. ---- */
__declspec(naked) static void cg_scale(void) {             /* eax = value, edx = texture */
    __asm {
        push ecx
        push edx
        push eax
        movzx eax, word ptr [edx + 12h]
        cmp eax, 544
        jbe keep
        xor edx, edx
        mov ecx, 544
        div ecx
        test edx, edx
        jnz keep
        mov ecx, eax
        pop eax
        xor edx, edx
        div ecx
        pop edx
        pop ecx
        ret
    keep:
        pop eax
        pop edx
        pop ecx
        ret
    }
}
__declspec(naked) static void cg_w(void) {
    __asm { movzx eax, word ptr [edx + 10h]
            call cg_scale
            mov ecx, dword ptr [ebx + 0D80h]
            ret }
}
__declspec(naked) static void cg_h(void) {
    __asm { movzx eax, word ptr [edx + 12h]
            call cg_scale
            mov ecx, dword ptr [ebx + 0D80h]
            ret }
}

static int fix_gallery_fit(int on) {
    if (!is(0x5c3aef, "\x0f\xb7\x42\x10\x8b\x8b\x80\x0d\x00\x00", 10) ||
        !is(0x5c3b19, "\x0f\xb7\x42\x12\x8b\x8b\x80\x0d\x00\x00", 10)) return 0;
    if (on) { call_at(0x5c3aef, cg_w, 10); call_at(0x5c3b19, cg_h, 10); }
    return 1;
}

/* ---- GalleryZoom: opens pictures fit-to-screen, zooms to 1:1, pans the whole picture ---- */
static int fix_gallery_zoom(int on) {
    BYTE *p = VA(ZOOM_VA); int i;
    for (i = 0; i < ZOOM_SIZE; i++) if (zoom_mask[i] && p[i] != zoom_old[i]) return 0;
    if (on) put(p, zoom_new, ZOOM_SIZE);
    return 1;
}

/* ---- MipFix: material samplers had MaxLOD 0 unless the material's mip mode == 1 ---- */
static int fix_mip(int mode) {
    if (!is(0x86307c, "\x75\x17", 2) || !is(0x863087, "\xc7\x45\xf4\x00\x00\x00\x00", 7)) return 0;
    if (mode == 1 || mode == 2) put(VA(0x86307c), "\x90\x90", 2);          /* modes 2+ reach MaxLOD=max */
    if (mode == 1 || mode == 3) put(VA(0x863087), "\xc7\x45\xf4\xff\xff\x7f\x7f", 7);  /* mode 0 */
    return 1;
}

/* ---- Anisotropy: trilinear material samplers -> anisotropic (point-filtered ones untouched) ---- */
static int aniso_level;
__declspec(naked) static void aniso_stub(void) {
    __asm {
        mov dword ptr [ebp - 30h], 1          ; replaced instruction (AddressW = WRAP)
        cmp dword ptr [ebp - 3Ch], 15h        ; filter == MIN_MAG_MIP_LINEAR ?
        jne done
        mov dword ptr [ebp - 3Ch], 55h        ; ANISOTROPIC
        push eax
        mov eax, aniso_level
        mov dword ptr [ebp - 28h], eax        ; MaxAnisotropy
        pop eax
    done:
        ret
    }
}

static int fix_aniso(int level) {
    if (!is(0x86304c, "\xc7\x45\xd0\x01\x00\x00\x00", 7)) return 0;
    if (level) { aniso_level = level; call_at(0x86304c, aniso_stub, 7); }
    return 1;
}

/* ---- SkipIntro: logo list = [intro video, HPG, Meteorise, CRIWARE] (CLogoManager) ---- */
static void *next_entry;
__declspec(naked) static void intro_stub(void) {           /* replaces SetState(6) = start playback */
    __asm {
        mov dword ptr [ecx + 1C8h], 7FFFh     ; index past the end ...
        call dword ptr [next_entry]           ; ... NextEntry takes the normal end path (title)
        ret 4
    }
}

/* Opening movie (Title/OP.usm): the title scene's mode 3. Entered from mode 2 when the title starts
   (0x76cbc9) and from the idle timer (0x76de45, attract loop). Only the first path is skipped: it sets
   a flag, and the OP's "movie starting" state then takes the game's own failed-movie path (fade out,
   stop, menu) instead of waiting for the movie. */
static BYTE op_skip;
__declspec(naked) static void op_from_title(void) {
    __asm {
        mov dword ptr [esi + 2ACh], 3         ; replaced instruction: mode 3 = OP
        mov op_skip, 1
        ret
    }
}
__declspec(naked) static void op_status(void) {             /* edi = title scene */
    __asm {
        mov eax, dword ptr [edi + 14h]        ; replaced instructions: movie status
        mov eax, dword ptr [eax + 4]
        cmp op_skip, 0
        je done
        mov op_skip, 0
        mov eax, 3                            ; not 1/2 (starting) or 4 (playing) -> failed-movie path
    done:
        ret
    }
}

static int fix_intro(int mode) {
    if (call_target(0x705e1b) != VA(0x7059b0) || call_target(0x705e38) != VA(0x7059b0) ||
        !is(0x706587, "\x7c\x29", 2) || !is(0x76cbc9, "\xc7\x86\xac\x02\x00\x00\x03\x00\x00\x00", 10) ||
        !is(0x76cd8e, "\x8b\x47\x14\x8b\x40\x04", 6)) return 0;
    if (mode == 1) put(VA(0x706587), "\x90\x90", 2);       /* NextEntry: stop after the intro video */
    if (mode >= 2) { next_entry = VA(0x706570); call_at(0x705e1b, intro_stub, 5); call_at(0x705e38, intro_stub, 5); }
    if (mode == 3) { call_at(0x76cbc9, op_from_title, 10); call_at(0x76cd8e, op_status, 6); }
    return 1;
}

/* ---- FrameRate: limiter fps hard-coded 60; game logic steps 480/fps ticks per frame ---- */
static int fix_fps(int f) {
    int i; WORD w; float t;
    if (!is(0x85af9a, "\xc7\x45\xfc\x3c\x00\x00\x00", 7)) return 0;
    for (i = 0; i < 4; i++) if (*(WORD *)VA(bld->fps_words + 4 * i) != 60 / (i + 1) ||
                                *(float *)VA(0x8eac80 + 4 * i) != (i + 1) / 60.0f) return 0;
    if (f == 60) return 1;
    put(VA(0x85af9d), &f, 4);
    for (i = 0; i < 4; i++) {
        w = (WORD)(f / (i + 1)); t = (i + 1) / (float)f;
        put(VA(bld->fps_words + 4 * i), &w, 2);            /* fps per in-game setting (1/1, 1/2, ...) */
        put(VA(0x8eac80 + 4 * i), &t, 4);                  /* frame time per setting */
    }
    return 1;
}

/* ---- FastDlcCheck: while the DLC worker is busy, set the renderer's 'unlimited fps' flag (+0x1c6) ---- */
__declspec(naked) static void dlc_stub(void) {             /* eax = render manager */
    __asm {
        mov ecx, dword ptr [eax + 2D0h]       ; replaced instruction: DLC worker
        push edx
        xor edx, edx
        cmp dword ptr [ecx], 3
        sete dl
        or dl, byte ptr [ecx + 8]             ; busy = (state == 3) | flag
        mov byte ptr [eax + 1C6h], dl
        pop edx
        ret
    }
}

static int fix_dlc(int on) {
    if (!is(bld->dlc_site, "\x8b\x88\xd0\x02\x00\x00", 6)) return 0;
    if (on) call_at(bld->dlc_site, dlc_stub, 6);
    return 1;
}

/* PreciseLimiter: 'setae al' picks Sleep(1) (~15.6 ms without timeBeginPeriod) -> always Sleep(0).
   ForceVSyncOff: fullscreen mode is 60 Hz, so vsync would cap there -> sync interval 0. */
static int toggle(DWORD va, const char *orig, const char *repl, int n, int on) {
    if (!is(va, orig, n)) return 0;
    if (on) put(VA(va), repl, n);
    return 1;
}

/* ---- PhysicsRate: frame-rate independent hair/bust physics ----
   The "Articulated Dynamics" solver (position based) steps once per frame with the real frame time.
   Its behaviour depends on the step size and was tuned at the Vita's 30 fps, so at 60+ the bust swings
   far too much. Per node keep a committed state on a fixed 1/PhysicsRate grid. Every frame: restore it
   and step once by the time elapsed since it (smooth, current pose); when a full interval has elapsed
   that step becomes the new committed state. */
#define MAXN 512                       /* manager pool: 0x200 nodes of 0x98 bytes at mgr+0x18 */
#define NODE_SZ 0x98
#define PART_SZ 0xf0                   /* particle; dynamic part = +0x70..+0xaf and +0xe8 */
#define ANC_SZ 0x68                    /* collider item (prev pose + per-substep poses) */
#define PART_DYN 0x40

typedef void(__fastcall *StepFn)(BYTE *node, void *edx);
static StepFn step_orig;
static float interval;                 /* 1 / PhysicsRate */
static double qpf;

typedef struct {
    BYTE *parts, *anc; int np, na;
    int valid; float acc; LONGLONG last;
    BYTE *buf; int cap;
} NodeState;
static NodeState st[MAXN];

static void save(NodeState *s) {
    BYTE *b = s->buf; int i;
    for (i = 0; i < s->np; i++, b += PART_DYN + 4) {
        memcpy(b, s->parts + i * PART_SZ + 0x70, PART_DYN);
        memcpy(b + PART_DYN, s->parts + i * PART_SZ + 0xe8, 4);
    }
    memcpy(b, s->anc, s->na * ANC_SZ);
}

static void restore(NodeState *s) {
    BYTE *b = s->buf; int i;
    for (i = 0; i < s->np; i++, b += PART_DYN + 4) {
        memcpy(s->parts + i * PART_SZ + 0x70, b, PART_DYN);
        memcpy(s->parts + i * PART_SZ + 0xe8, b + PART_DYN, 4);
    }
    memcpy(s->anc, b, s->na * ANC_SZ);
}

static void __fastcall step_hook(BYTE *node, void *edx) {
    BYTE *mgr = *(BYTE **)VA(bld->ad_mgr);
    BYTE *sync = *(BYTE **)VA(bld->vsync_mgr);
    INT_PTR rel = node - mgr - 0x18;
    NodeState *s; LARGE_INTEGER now; float D, Dc, *scale, orig; int need;
    if (!mgr || !sync || rel < 0 || rel % NODE_SZ || rel / NODE_SZ >= MAXN) { step_orig(node, edx); return; }
    s = &st[rel / NODE_SZ];
    D = *(float *)(sync + 0x14);                          /* frame time (CVSyncManager) */
    QueryPerformanceCounter(&now);

    if (s->parts != *(BYTE **)(node + 0x18) || s->np != *(int *)(node + 0x68) ||
        s->anc != *(BYTE **)(node + 0x28) || s->na != *(int *)(node + 0x30) ||
        node[0x93] || D <= 0 || (now.QuadPart - s->last) / qpf > 0.1) {
        s->valid = 0;                                     /* new/reset/reused node or a pause */
        s->parts = *(BYTE **)(node + 0x18); s->np = *(int *)(node + 0x68);
        s->anc = *(BYTE **)(node + 0x28); s->na = *(int *)(node + 0x30);
    }
    s->last = now.QuadPart;
    need = s->np * (PART_DYN + 4) + s->na * ANC_SZ;
    if (need > s->cap) {
        BYTE *nb = (BYTE *)HeapAlloc(GetProcessHeap(), 0, need);
        if (!nb) { s->valid = 0; step_orig(node, edx); return; }
        if (s->buf) HeapFree(GetProcessHeap(), 0, s->buf);
        s->buf = nb; s->cap = need; s->valid = 0;
    }
    if (!s->valid || D >= interval) {                     /* plain step, it is the committed state */
        step_orig(node, edx);
        save(s); s->valid = 1; s->acc = 0;
        return;
    }
    s->acc += D;
    restore(s);                                           /* step from the committed state ... */
    Dc = D < 1.0f / 15 ? D : 1.0f / 15;                   /* the game clamps the frame time */
    scale = (float *)(node + 0x84); orig = *scale;
    *scale = orig * (s->acc < 1.0f / 15 ? s->acc : 1.0f / 15) / Dc;   /* ... by the elapsed time */
    step_orig(node, edx);
    *scale = orig;
    if (s->acc >= 0.95f * interval) { save(s); s->acc = 0; }
}

static int fix_physics(int rate) {
    static const BYTE prolog[] = {0x55, 0x8b, 0xec, 0x83, 0xe4, 0xf8, 0x83, 0xec, 0x54};
    BYTE *jmp = VA(bld->phys_jmp);                        /* node job: pop ebp; jmp step */
    LARGE_INTEGER f; int rel;
    if (jmp[0] != 0xe9 || jmp + 5 + *(int *)(jmp + 1) != VA(bld->phys_step) ||
        memcmp(VA(bld->phys_step), prolog, sizeof prolog)) return 0;
    if (!rate) return 1;
    QueryPerformanceFrequency(&f); qpf = (double)f.QuadPart;
    interval = 1.0f / rate;
    step_orig = (StepFn)VA(bld->phys_step);
    rel = (int)((BYTE *)step_hook - (jmp + 5));
    put(jmp + 1, &rel, 4);
    return 1;
}

/* ---- Large Address Aware check: runs on the game's main thread just before its own code ---- */
static BYTE *entry, entry_saved[5];

static void laa_check(void) {
    IMAGE_NT_HEADERS *nt = (IMAGE_NT_HEADERS *)(base + ((IMAGE_DOS_HEADER *)base)->e_lfanew);
    if (nt->FileHeader.Characteristics & IMAGE_FILE_LARGE_ADDRESS_AWARE) { say("LargeAddressAware: set in the exe\n"); return; }
    say("LargeAddressAware: MISSING in the exe (run Set4GB.bat)\n");
    MessageBoxA(0,
        "VD_BHIKKHUNI.exe is missing the Large Address Aware flag (4 GB of memory instead of 2 GB), "
        "probably because Steam updated or verified the game. Without it the HD textures can make "
        "the game run out of memory.\n\n"
        "To set it: close the game, double-click Set4GB.bat in the game's DeploymentRoot folder, "
        "then start the game again.\n\n"
        "OK = play without it this time. (LargeAddressAware=0 in vdmod.ini turns this check off.)",
        MOD_NAME, MB_OK | MB_ICONWARNING | MB_TOPMOST | MB_SETFOREGROUND);
}

static void before_game(void) {
    put(entry, entry_saved, 5);
    laa_check();
    save_log();
}

__declspec(naked) static void entry_hook(void) {
    __asm {
        call before_game
        jmp dword ptr [entry]
    }
}

/* ---- shadow map size: the game reads ShadowWidth/ShadowHeight from MeigeAppWin.cfg (no section, so no
   GetPrivateProfile); Steam verify puts back the shipped 512. Rewrites those two lines when they differ. ---- */
static void fix_shadow(int res) {
    char path[MAX_PATH], in[8192], out[8400], *l, *e, *o = out; DWORD n = 0; HANDLE f; int w = 0, h = 0, cw = 0, ch = 0;
    sprintf_s(path, MAX_PATH, "%sMeigeAppWin.cfg", dir);
    f = CreateFileA(path, GENERIC_READ, FILE_SHARE_READ, 0, OPEN_EXISTING, 0, 0);
    if (f == INVALID_HANDLE_VALUE) { say("ShadowResolution=%d: SKIPPED - MeigeAppWin.cfg not found\n", res); return; }
    ReadFile(f, in, sizeof in - 1, &n, 0); CloseHandle(f); in[n] = 0;
    for (l = in; *l; l = e) {
        e = strchr(l, '\n'); e = e ? e + 1 : l + strlen(l);
        if (!strncmp(l, "ShadowWidth=", 12)) { w = 1; cw = atoi(l + 12); o += sprintf_s(o, 40, "ShadowWidth=%d\r\n", res); }
        else if (!strncmp(l, "ShadowHeight=", 13)) { h = 1; ch = atoi(l + 13); o += sprintf_s(o, 40, "ShadowHeight=%d\r\n", res); }
        else { memcpy(o, l, e - l); o += e - l; }
    }
    if (cw == res && ch == res) { say("ShadowResolution=%d: on (MeigeAppWin.cfg already %dx%d)\n", res, res, res); return; }
    if (!w) o += sprintf_s(o, 40, "ShadowWidth=%d\r\n", res);   /* missing = exe default 1024 */
    if (!h) o += sprintf_s(o, 40, "ShadowHeight=%d\r\n", res);
    f = CreateFileA(path, GENERIC_WRITE, 0, 0, CREATE_ALWAYS, 0, 0);
    if (f == INVALID_HANDLE_VALUE || !WriteFile(f, out, (DWORD)(o - out), &n, 0))
        say("ShadowResolution=%d: SKIPPED - could not write MeigeAppWin.cfg (error %lu)\n", res, GetLastError());
    else say("ShadowResolution=%d: on (MeigeAppWin.cfg was %dx%d, rewritten)\n", res, w ? cw : 1024, h ? ch : 1024);
    if (f != INVALID_HANDLE_VALUE) CloseHandle(f);
}

/* ---- MSAA fix: every pixel shader the game creates (from its shader caches or compiled at run time)
   goes through ID3D11Device::CreatePixelShader; the hook passes a centroid-patched copy instead. The
   device comes from the exe's D3D11CreateDevice import, hooked in its import table. ---- */
typedef HRESULT(STDMETHODCALLTYPE *CreatePS)(void *, const void *, SIZE_T, void *, void **);
typedef HRESULT(WINAPI *CreateDev)(void *, int, HMODULE, UINT, const void *, UINT, UINT, void **, void *, void **);
static CreatePS ps_orig;
static CreateDev dev_orig;
static volatile LONG ps_patched;

static volatile LONG ps_failed, cc_calls, cc_failed;
static int msaa_on;

static HRESULT STDMETHODCALLTYPE ps_hook(void *dev, const void *code, SIZE_T len, void *link, void **ps) {
    BYTE *copy = msaa_on && code && len >= 32 && len < 1 << 22 ? malloc(len) : 0; HRESULT r;
    if (copy) {
        memcpy(copy, code, len);
        if (centroid_patch(copy, (DWORD)len) && SUCCEEDED(r = ps_orig(dev, copy, len, link, ps))) {
            InterlockedIncrement(&ps_patched); free(copy); return r;
        }
        free(copy);                                  /* not patchable, or refused: the original shader */
    }
    r = ps_orig(dev, code, len, link, ps);
    if (FAILED(r) && InterlockedIncrement(&ps_failed) <= 10) { say("Shaders: CreatePixelShader FAILED %08lx (%lu bytes)\n", r, (DWORD)len); save_log(); }
    return r;
}

/* the game also compiles some shaders at run time (D3DCompile): failures are logged with the
   compiler's message, as a missing shader leaves meshes drawn depth-only (black holes) */
typedef HRESULT(WINAPI *Compile)(const void *, SIZE_T, const char *, const void *, void *, const char *, const char *,
                                 UINT, UINT, void **, void **);
static Compile cc_orig;

static HRESULT WINAPI cc_hook(const void *src, SIZE_T n, const char *name, const void *defs, void *inc, const char *entry,
                              const char *target, UINT f1, UINT f2, void **code, void **err) {
    void *e = 0; HRESULT r = cc_orig(src, n, name, defs, inc, entry, target, f1, f2, code, err ? err : &e);
    InterlockedIncrement(&cc_calls);
    if (FAILED(r) && InterlockedIncrement(&cc_failed) <= 10) {
        void *b = err ? *err : e;
        const char *msg = b ? (const char *)((void *(STDMETHODCALLTYPE *)(void *))(*(void ***)b)[3])(b) : "";
        say("Shaders: D3DCompile FAILED %08lx %s %s: %.300s\n", r, target ? target : "", name ? name : "", msg);
        save_log();
    }
    if (e) ((ULONG(STDMETHODCALLTYPE *)(void *))(*(void ***)e)[2])(e);
    return r;
}

static DWORD *iat_slot(IMAGE_NT_HEADERS *nt, const char *dll, const char *func) {
    IMAGE_DATA_DIRECTORY *dd = &nt->OptionalHeader.DataDirectory[IMAGE_DIRECTORY_ENTRY_IMPORT];
    IMAGE_IMPORT_DESCRIPTOR *d = (IMAGE_IMPORT_DESCRIPTOR *)(base + dd->VirtualAddress);
    for (; dd->VirtualAddress && d->Name; d++) {
        IMAGE_THUNK_DATA32 *names = (IMAGE_THUNK_DATA32 *)(base + d->OriginalFirstThunk);
        DWORD i;
        if (_stricmp((char *)base + d->Name, dll) || !d->OriginalFirstThunk) continue;
        for (i = 0; names[i].u1.AddressOfData; i++)
            if (!(names[i].u1.Ordinal & IMAGE_ORDINAL_FLAG32) &&
                !strcmp(((IMAGE_IMPORT_BY_NAME *)(base + names[i].u1.AddressOfData))->Name, func))
                return (DWORD *)(base + d->FirstThunk) + i;
    }
    return 0;
}

/* ---- BlackWallFix: some stages have invisible depth-only meshes (drawn with no pixel shader into
   the scene) placed exactly on walls. Whichever rasterizes a hair closer wins, so parts of those
   walls fail the depth test and stay black, changing with the camera (vanilla bug). Such draws get
   a rasterizer state with a small depth bias: the real wall always wins, and the invisible mesh
   still hides what is really behind it. Shadow-map draws (no colour target) are left alone. ---- */
typedef void(STDMETHODCALLTYPE *PSSet)(void *, void *, void *const *, UINT);
typedef void(STDMETHODCALLTYPE *OMSet)(void *, UINT, void *const *, void *);
typedef void(STDMETHODCALLTYPE *OMSetUAV)(void *, UINT, void *const *, void *, UINT, UINT, void *const *, const UINT *);
typedef void(STDMETHODCALLTYPE *RSSet)(void *, void *);
typedef void(STDMETHODCALLTYPE *ClearSt)(void *);
typedef HRESULT(STDMETHODCALLTYPE *CreateRS)(void *, const D3D11_RASTERIZER_DESC *, void **);
static PSSet pss_orig;
static OMSet oms_orig;
static OMSetUAV omu_orig;
static RSSet rss_orig;
static ClearSt cls_orig;
static void *g_dev, *cur_ps, *cur_rs, *set_rs;   /* set_rs: the state really set (cur_rs or its biased copy) */
static int cur_rt, wall_on;
static volatile LONG wall_sets, n_rss, n_om, n_pss;
static struct { void *orig, *biased; } rs_cache[64];
static int rs_n;

static void *biased_rs(void *rs) {
    D3D11_RASTERIZER_DESC d = {D3D11_FILL_SOLID, D3D11_CULL_BACK, FALSE, 0, 0.f, 0.f, TRUE, FALSE, FALSE, FALSE};
    void *out = 0; int i;
    for (i = 0; i < rs_n; i++) if (rs_cache[i].orig == rs) return rs_cache[i].biased;
    if (rs_n == 64) return 0;
    if (rs) ((void(STDMETHODCALLTYPE *)(void *, D3D11_RASTERIZER_DESC *))(*(void ***)rs)[7])(rs, &d);  /* GetDesc */
    d.DepthBias += 64;                        /* D24: 64 / 2^24 - the fights seen were ~4 units */
    d.SlopeScaledDepthBias += 1.0f;
    if (FAILED(((CreateRS)(*(void ***)g_dev)[22])(g_dev, &d, &out))) out = 0;
    if (rs) ((ULONG(STDMETHODCALLTYPE *)(void *))(*(void ***)rs)[1])(rs);   /* keep it alive: no address reuse */
    rs_cache[rs_n].orig = rs; rs_cache[rs_n++].biased = out;
    return out;
}

/* The draw methods can't be hooked (the runtime rewrites those entries of the context's private
   method table), so the bias follows the state instead: whenever no pixel shader and a colour
   target are bound, the biased copy of the game's rasterizer state is the one set. */
static void wall_apply(void *c) {
    void *want = cur_rs, *b;
    if (!cur_ps && cur_rt && (b = biased_rs(cur_rs))) want = b;
    if (want != set_rs) { rss_orig(c, want); if (want != cur_rs) wall_sets++; set_rs = want; }
}
static void STDMETHODCALLTYPE cls_hook(void *c) { cls_orig(c); cur_ps = cur_rs = set_rs = 0; cur_rt = 0; }
static void STDMETHODCALLTYPE pss_hook(void *c, void *ps, void *const *ci, UINT n) { n_pss++; pss_orig(c, ps, ci, n); cur_ps = ps; wall_apply(c); }
static void STDMETHODCALLTYPE rss_hook(void *c, void *rs) { n_rss++; cur_rs = rs; set_rs = (void *)-1; wall_apply(c); }
static void STDMETHODCALLTYPE oms_hook(void *c, UINT n, void *const *rt, void *ds) { n_om++; oms_orig(c, n, rt, ds); cur_rt = n && rt && rt[0]; wall_apply(c); }
static void STDMETHODCALLTYPE omu_hook(void *c, UINT n, void *const *rt, void *ds, UINT a, UINT b, void *const *u, const UINT *ic) {
    omu_orig(c, n, rt, ds, a, b, u, ic);
    if (n != D3D11_KEEP_RENDER_TARGETS_AND_DEPTH_STENCIL) { cur_rt = n && rt && rt[0]; wall_apply(c); }
}

static void hook_slot(void **vt, int i, void *hook, void **orig) {
    if (vt[i] != hook) { *orig = vt[i]; put((BYTE *)&vt[i], &hook, 4); }
}

static HRESULT WINAPI dev_hook(void *ad, int type, HMODULE sw, UINT fl, const void *lv, UINT n, UINT sdk,
                               void **dev, void *got, void **ctx) {
    HRESULT r = dev_orig(ad, type, sw, fl, lv, n, sdk, dev, got, ctx);
    if (SUCCEEDED(r) && dev && *dev) {
        void **vt = *(void ***)*dev;
        g_dev = *dev;
        hook_slot(vt, 15, (void *)ps_hook, (void **)&ps_orig);                /* CreatePixelShader */
        if (wall_on && ctx && *ctx) {
            void **cv = *(void ***)*ctx;                                     /* ID3D11DeviceContext */
            hook_slot(cv, 9, (void *)pss_hook, (void **)&pss_orig);           /* PSSetShader */
            hook_slot(cv, 33, (void *)oms_hook, (void **)&oms_orig);          /* OMSetRenderTargets */
            hook_slot(cv, 34, (void *)omu_hook, (void **)&omu_orig);          /* ...AndUnorderedAccessViews */
            hook_slot(cv, 43, (void *)rss_hook, (void **)&rss_orig);          /* RSSetState */
            hook_slot(cv, 110, (void *)cls_hook, (void **)&cls_orig);         /* ClearState */
        }
        say("D3D11 device hooked%s\n", wall_on && ctx && *ctx ? " (BlackWallFix active)" : ""); save_log();
    }
    return r;
}

static int fix_msaa(int on, IMAGE_NT_HEADERS *nt) {     /* the hooks also do the shader logging */
    DWORD *dev = iat_slot(nt, "d3d11.dll", "D3D11CreateDevice"), *cc = iat_slot(nt, "D3DCOMPILER_47.dll", "D3DCompile");
    void *h;
    msaa_on = on;
    if (cc) { cc_orig = (Compile)*cc; h = (void *)cc_hook; put((BYTE *)cc, &h, 4); }
    if (!dev) return 0;
    dev_orig = (CreateDev)*dev; h = (void *)dev_hook; put((BYTE *)dev, &h, 4);
    return 1;
}

/* ---- resolution list: the options/startup code (0x8694c0) filters a built-in table (640x360 ..
   3840x2160) by the desktop size from GetSystemMetrics: window = smaller than the desktop, borderless
   = the desktop, fullscreen = up to the desktop (+ the desktop size itself when not in the table).
   Between the borderless and the fullscreen list the stub raises that size for the fullscreen list
   only, so DSR modes become choosable in exclusive fullscreen. ---- */
static int res_w, res_h;

__declspec(naked) static void res_stub(void) {
    __asm {
        xor eax, eax                       /* the 6 replaced bytes */
        mov word ptr [ebx + 16h], ax
        cmp edi, res_w                     /* edi/esi = desktop w/h, [ebp-0Ch] = saved w */
        jge w_ok
        mov edi, res_w
    w_ok:
        cmp esi, res_h
        jge h_ok
        mov esi, res_h
    h_ok:
        mov dword ptr [ebp - 0Ch], edi
        ret
    }
}

/* Applying a size (0x859800, both builds): in fullscreen/borderless the swap chain buffers were
   resized to the desktop size whatever was chosen, and the display mode was never changed, so a
   fullscreen 3840x2160 stayed a 1920x1080 picture. For fullscreen (mode 2) the stub resizes the
   buffers to the chosen size and switches the display mode to it (IDXGISwapChain::ResizeTarget),
   which is where DSR/VSR takes over. Window and borderless keep the original behaviour. */
static DWORD *wnd_pp;                      /* the game's window object pointer (global) */
static int fs_logged;

static void __cdecl fs_target(BYTE *dev) {
    void *sc = *(void **)(dev + 0x7c);     /* IDXGISwapChain */
    DXGI_MODE_DESC m = {0};
    HRESULT hr;
    m.Width = *(UINT *)(dev + 0x1c8); m.Height = *(UINT *)(dev + 0x1cc);
    hr =((HRESULT(STDMETHODCALLTYPE *)(void *, const DXGI_MODE_DESC *))(*(void ***)sc)[14])(sc, &m);
    if (fs_logged++ < 4) { say("MaxResolution: fullscreen %ux%u, display mode switch %s (%08lx)\n", m.Width, m.Height, SUCCEEDED(hr) ? "ok" : "FAILED", hr); save_log(); }
}

__declspec(naked) static void fs_stub(void) {
    __asm {
        mov eax, wnd_pp
        mov eax, dword ptr [eax]
        cmp byte ptr [esi + 1C1h], 2       /* fullscreen? */
        jne orig
        mov edi, dword ptr [esi + 1C8h]    /* the chosen size, not the desktop's */
        mov ebx, dword ptr [esi + 1CCh]
        test esi, esi                      /* ZF = 0: always take the resize path */
        ret
    orig:
        mov edi, dword ptr [eax + 28h]     /* the 15 replaced bytes */
        mov ebx, dword ptr [eax + 2Ch]
        cmp byte ptr [ebp - 1], 0
        ret
    }
}

/* replaces "call [ecx+34h] (IDXGISwapChain::ResizeBuffers, args pushed); test eax, eax" at 0x859a18:
   the mode switch must come after it, as ResizeBuffers is what adds ALLOW_MODE_SWITCH to the chain */
static DWORD rb_ret;

__declspec(naked) static void rb_stub(void) {
    __asm {
        pop rb_ret
        call dword ptr [ecx + 34h]
        push eax
        cmp byte ptr [esi + 1C1h], 2
        jne done
        pushad
        push esi
        call fs_target
        add esp, 4
        popad
    done:
        pop eax
        test eax, eax
        push rb_ret
        ret
    }
}

/* Texture creation job 0x862770 (worker thread, queued at 0x8626c1) passes the texture header
   [job+78h] to 0x862790, which reads it unchecked. Rarely the header is already cleared when the job
   runs (game race, seen once entering a stage/cutscene: AV at 0x8627c7). Rewritten in place (same
   24 bytes incl. padding, same address in both builds) to skip the job then. Always on. */
static int fix_tex_guard(void) {
    static const char orig[] = "\x55\x8b\xec\x8b\x4d\x08\xff\x71\x74\xff\x71\x78\xe8\x0f\x00\x00\x00"
                               "\xb0\x01\x5d\xc3\xcc\xcc\xcc";
    static const char repl[] = "\x8b\x4c\x24\x04"          /* mov ecx, [esp+4]  (job)      */
                               "\x83\x79\x78\x00"          /* cmp dword [ecx+78h], 0       */
                               "\x74\x0b"                  /* je  done                     */
                               "\xff\x71\x74\xff\x71\x78"  /* push [ecx+74h]; push [ecx+78h] */
                               "\xe8\x0b\x00\x00\x00"      /* call 0x862790 (thiscall)     */
                               "\xb0\x01\xc3";             /* done: mov al, 1; ret         */
    return toggle(0x862770, orig, repl, 24, 1);
}

/* Options menu (0x730910): the saved Screen Size index of each display mode (window, borderless,
   fullscreen) picks a label from that mode's list without a range check. A size saved while
   MaxResolution was higher (or on another desktop) points past a now shorter list and the menu
   crashes; right after the lists are built (0x7309ce) the indexes are clamped to them. Always on. */
static void __cdecl clamp_res(BYTE *menu) {
    int k;
    for (k = 0; k < 3; k++) {
        int n = *(short *)(menu + 0x2e + 2 * k), *idx = (int *)(menu + 0x4df0 + 4 * k);
        if (*idx >= n) *idx = n > 0 ? n - 1 : 0;
        if (*idx < 0) *idx = 0;
    }
}

__declspec(naked) static void clamp_stub(void) {
    __asm {
        pushad
        push ebx
        call clamp_res
        add esp, 4
        popad
        mov eax, dword ptr [ebp - 30Ch]    /* the 6 replaced bytes */
        ret
    }
}

static int fix_res_clamp(void) {
    if (!is(0x7309c6, "\x8d\x4b\x1c\xe8", 4) || !is(0x7309ce, "\x8b\x85\xf4\xfc\xff\xff", 6)) return 0;
    call_at(0x7309ce, clamp_stub, 6);
    return 1;
}

static int fix_resolution(const char *s) {
    if (sscanf_s(s, "%dx%d", &res_w, &res_h) != 2 || res_w < 640 || res_h < 360 || res_w > 8192 || res_h > 8192) return -1;
    if (!is(bld->res_site, "\x33\xc0\x66\x89\x43\x16", 6) || !is(0x8599a8, "\x80\x7d\xff\x00\xa1", 5) ||
        !is(0x8599b1, "\x8b\x78\x28\x8b\x58\x2c\x0f\x84", 8) || !is(0x859a17, "\x50\xff\x51\x34\x85\xc0\x74", 7)) return 0;
    wnd_pp = *(DWORD **)VA(0x8599ad);
    call_at(bld->res_site, res_stub, 6);
    call_at(0x8599a8, fs_stub, 15);
    call_at(0x859a18, rb_stub, 5);
    return 1;
}

/* ---- startup ---- */
static void report(const char *key, int val, int ok) {
    say("%s=%d: %s\n", key, val, !ok ? "SKIPPED - unexpected exe bytes (other game version?)" : val ? "on" : "off");
}

static void install(HMODULE self) {
    IMAGE_NT_HEADERS *nt; char *p; int v, ok, i;
    base = (BYTE *)GetModuleHandleA(0);
    GetModuleFileNameA(self, dir, MAX_PATH);
    p = strrchr(dir, '\\'); p[1] = 0;
    sprintf_s(ini, MAX_PATH, "%svdmod.ini", dir);
    say(MOD_NAME " " MOD_VER_STR " (dinput8.dll), options from %s\n", ini);
    nt = (IMAGE_NT_HEADERS *)(base + ((IMAGE_DOS_HEADER *)base)->e_lfanew);
    for (i = 0; i < sizeof builds / sizeof *builds; i++)
        if (nt->FileHeader.TimeDateStamp == builds[i].stamp) bld = &builds[i];
    say("Game exe: %s\n", bld->stamp == nt->FileHeader.TimeDateStamp ? bld->name : "UNKNOWN build (trying public addresses)");

    v = opt("GalleryHDFit", 1);   report("GalleryHDFit", v, fix_gallery_fit(v));
    v = opt("GalleryZoom", 1);    report("GalleryZoom", v, fix_gallery_zoom(v));
    v = opt("MipFix", 1);         ok = v >= 0 && v <= 3;
    if (ok) report("MipFix", v, fix_mip(v)); else say("MipFix=%d: SKIPPED - must be 0..3\n", v);
    v = opt("Anisotropy", 16);    ok = v >= 0 && v <= 16;
    if (ok) report("Anisotropy", v, fix_aniso(v)); else say("Anisotropy=%d: SKIPPED - must be 0..16\n", v);
    v = opt("SkipIntro", 2);      ok = v >= 0 && v <= 3;
    if (ok) report("SkipIntro", v, fix_intro(v)); else say("SkipIntro=%d: SKIPPED - must be 0..3\n", v);
    v = opt("FastDlcCheck", 1);   report("FastDlcCheck", v, fix_dlc(v));
    v = opt("FrameRate", 60);     ok = v == 60 || v == 80 || v == 96 || v == 120 || v == 160 || v == 240;
    if (ok) say("FrameRate=%d: %s\n", v, fix_fps(v) ? "on" : "SKIPPED - unexpected exe bytes (other game version?)");
    else say("FrameRate=%d: SKIPPED - must be 60, 80, 96, 120, 160 or 240\n", v);
    v = opt("PreciseLimiter", 1); report("PreciseLimiter", v, toggle(0x855d9c, "\x0f\x93\xc0", "\x0f\x1f\x00", 3, v));
    v = opt("ForceVSyncOff", 1);  report("ForceVSyncOff", v, toggle(0x85afaf, "\x0f\x95\xc3", "\x31\xdb\x90", 3, v));
    v = opt("PhysicsRate", 30);   ok = v >= 0 && v <= 1000;
    if (ok) report("PhysicsRate", v, fix_physics(v)); else say("PhysicsRate=%d: SKIPPED - must be 0..1000\n", v);
    /* dressing room (CCommunicationRoom) exit: state 0xe -> 0xf opens the "Server Connect" check
       (0.33..2 s) and 0x10 uploads the CommunicationRoomRanking leaderboard score; -> 0xc leaves at
       once, the same path the game takes when the check fails (offline) */
    v = opt("SkipRoomRanking", 1); report("SkipRoomRanking", v, toggle(0x5d9779, "\x6a\x0f\x8b\xca\xe8", "\x6a\x0c\x8b\xca\xe8", 5, v));
    {
        char s[32];
        GetPrivateProfileStringA("VDMod", "MaxResolution", "0", s, sizeof s, ini);
        if (s[0] == '0' && (!s[1] || s[1] == ' ' || s[1] == '\t' || s[1] == ';')) say("MaxResolution=0: off\n");
        else if ((v = fix_resolution(s)) < 0) say("MaxResolution=%s: SKIPPED - must be WIDTHxHEIGHT (e.g. 3840x2160) or 0\n", s);
        else say("MaxResolution=%dx%d: %s\n", res_w, res_h, v ? "on" : "SKIPPED - unexpected exe bytes (other game version?)");
        say("Screen Size menu index check: %s\n", fix_res_clamp() ? "on" : "SKIPPED - unexpected exe bytes");
    }
    say("Texture job guard: %s\n", fix_tex_guard() ? "on" : "SKIPPED - unexpected exe bytes");
    wall_on = opt("BlackWallFix", 1); say("BlackWallFix=%d: %s\n", wall_on, wall_on ? "on" : "off");
    v = opt("MSAAFix", 1);        report("MSAAFix", v, fix_msaa(v, nt));
    v = opt("ShadowResolution", 0);
    if (!v) say("ShadowResolution: off (MeigeAppWin.cfg left as it is)\n");
    else if (v >= 512 && v <= 8192 && !(v & (v - 1))) fix_shadow(v);
    else say("ShadowResolution=%d: SKIPPED - must be 0, 512, 1024, 2048, 4096 or 8192\n", v);

    if (opt("LargeAddressAware", 1)) {                    /* checked from the exe entry point, outside */
        BYTE j[5] = {0xe9};                               /* the loader lock (MessageBox, CreateProcess) */
        entry = base + nt->OptionalHeader.AddressOfEntryPoint;
        memcpy(entry_saved, entry, 5);
        *(int *)(j + 1) = (int)((BYTE *)entry_hook - (entry + 5));
        put(entry, j, 5);
    } else { say("LargeAddressAware: check off\n"); save_log(); }
}

typedef HRESULT(WINAPI *DI8Create)(HINSTANCE, DWORD, REFIID, LPVOID *, LPUNKNOWN);

HRESULT WINAPI DirectInput8Create(HINSTANCE h, DWORD v, REFIID r, LPVOID *o, LPUNKNOWN u) {
    static DI8Create real;
    if (!real) {
        char path[MAX_PATH];
        GetSystemDirectoryA(path, MAX_PATH); strcat_s(path, MAX_PATH, "\\dinput8.dll");
        real = (DI8Create)GetProcAddress(LoadLibraryA(path), "DirectInput8Create");
        if (!real) return E_FAIL;
    }
    return real(h, v, r, o, u);
}

BOOL WINAPI DllMain(HINSTANCE self, DWORD reason, LPVOID res) {
    if (reason == DLL_PROCESS_ATTACH) { DisableThreadLibraryCalls(self); install(self); }
    if (reason == DLL_PROCESS_DETACH && ps_orig) {
        say("Shaders: %ld pixel shaders patched (MSAAFix), %ld creations failed; D3DCompile %ld calls, %ld failed\n",
            ps_patched, ps_failed, cc_calls, cc_failed);
        if (wall_on) say("BlackWallFix: bias set %ld times, %d rasterizer states (calls: RSSetState %ld, OMSetRenderTargets %ld, PSSetShader %ld)\n", wall_sets, rs_n, n_rss, n_om, n_pss);
        save_log();
    }
    return TRUE;
}
