/* Check for centroid.h: patch every DXBC blob of a shader file the way the DLL does and write the
   result, to compare byte for byte with shaderfix.py.   test_centroid.exe in.bin out.bin */
#include <windows.h>
#include <stdio.h>
#include <stdlib.h>
#include "centroid.h"

int main(int argc, char **argv) {
    FILE *f; long n, i; BYTE *d; int ps = 0, inputs = 0, c; DWORD size, st[4], badsum = 0;
    if (argc != 3 || fopen_s(&f, argv[1], "rb")) return 2;
    fseek(f, 0, SEEK_END); n = ftell(f); fseek(f, 0, SEEK_SET);
    d = malloc(n); fread(d, 1, n, f); fclose(f);
    for (i = 0; i + 32 <= n; i++) {
        if (memcmp(d + i, "DXBC", 4)) continue;
        size = *(DWORD *)(d + i + 24);
        if (size <= 32 || size >= 1 << 20 || i + size > (DWORD)n) continue;
        if ((c = centroid_patch(d + i, size))) { ps++; inputs += c; }
        dxbc_checksum(d + i, size, st);
        if (memcmp(st, d + i + 4, 16)) badsum++;
        i += size - 1;
    }
    printf("%s: %d pixel shaders, %d inputs -> centroid, %lu blobs with bad checksum\n", argv[1], ps, inputs, badsum);
    if (fopen_s(&f, argv[2], "wb")) return 2;
    fwrite(d, 1, n, f); fclose(f);
    return 0;
}
