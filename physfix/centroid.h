/* MSAA fix, C port of ../shaderfix.py: pixel-shader inputs 'linear' -> 'linear centroid'.
   With MSAA, edge pixels run the pixel shader at the pixel centre even outside the triangle, so
   'linear' inputs are extrapolated; overlay shaders (alpha = tex.a * vertex colour) then output
   alpha far outside 0..1, the FP16 scene doesn't clamp, and bloom turns it into flashing blobs.
   Shared by vdmod.c and test_centroid.c. */
#include <math.h>

static DWORD md5_k[64];
static const BYTE md5_s[64] = {7, 12, 17, 22, 7, 12, 17, 22, 7, 12, 17, 22, 7, 12, 17, 22,
                               5, 9, 14, 20, 5, 9, 14, 20, 5, 9, 14, 20, 5, 9, 14, 20,
                               4, 11, 16, 23, 4, 11, 16, 23, 4, 11, 16, 23, 4, 11, 16, 23,
                               6, 10, 15, 21, 6, 10, 15, 21, 6, 10, 15, 21, 6, 10, 15, 21};

static void md5_block(DWORD st[4], const BYTE *blk) {
    const DWORD *m = (const DWORD *)blk; DWORD a = st[0], b = st[1], c = st[2], d = st[3], f, t; int i, g;
    if (!md5_k[0]) for (i = 0; i < 64; i++) md5_k[i] = (DWORD)(fabs(sin(i + 1.0)) * 4294967296.0);
    for (i = 0; i < 64; i++) {
        if (i < 16) { f = (b & c) | (~b & d); g = i; }
        else if (i < 32) { f = (d & b) | (~d & c); g = (5 * i + 1) % 16; }
        else if (i < 48) { f = b ^ c ^ d; g = (3 * i + 5) % 16; }
        else { f = c ^ (b | ~d); g = (7 * i) % 16; }
        f += a + md5_k[i] + m[g];
        a = d; d = c; c = b;
        t = md5_s[i]; b += (f << t) | (f >> (32 - t));
    }
    st[0] += a; st[1] += b; st[2] += c; st[3] += d;
}

/* DXBC checksum: MD5 compression over blob[20..] with DXBC's own padding */
static void dxbc_checksum(const BYTE *blob, DWORD size, DWORD st[4]) {
    const BYTE *data = blob + 20; DWORD n = size - 20, bits = n * 8, full = n - n % 64, rest = n % 64, i;
    BYTE blk[64];
    st[0] = 0x67452301; st[1] = 0xefcdab89; st[2] = 0x98badcfe; st[3] = 0x10325476;
    for (i = 0; i < full; i += 64) md5_block(st, data + i);
    memset(blk, 0, 64);
    if (rest >= 56) {
        memcpy(blk, data + full, rest); blk[rest] = 0x80; md5_block(st, blk);
        memset(blk, 0, 64); *(DWORD *)blk = bits;
    } else {
        *(DWORD *)blk = bits; memcpy(blk + 4, data + full, rest); blk[4 + rest] = 0x80;
    }
    *(DWORD *)(blk + 60) = (bits >> 2) | 1;
    md5_block(st, blk);
}

/* Patch a DXBC pixel shader in place; returns the number of inputs changed (0 = left untouched:
   not a pixel shader, nothing linear, bad checksum or anything unexpected in the token stream). */
static int centroid_patch(BYTE *blob, DWORD len) {
    DWORD st[4], n, k, o, clen, p, tok, op, ln, *code = 0; int changed = 0;
    if (len < 32 || memcmp(blob, "DXBC", 4) || *(DWORD *)(blob + 24) > len || *(DWORD *)(blob + 24) < 32) return 0;
    len = *(DWORD *)(blob + 24);
    dxbc_checksum(blob, len, st);
    if (memcmp(st, blob + 4, 16)) return 0;
    n = *(DWORD *)(blob + 28);
    if (n > 64 || 32 + 4 * n > len) return 0;
    for (k = 0; k < n && !code; k++) {
        o = *(DWORD *)(blob + 32 + 4 * k);
        if (o > len - 8) return 0;
        clen = *(DWORD *)(blob + o + 4);
        if ((!memcmp(blob + o, "SHDR", 4) || !memcmp(blob + o, "SHEX", 4)) && clen <= len - o - 8 && clen >= 8 && !(clen & 3))
            code = (DWORD *)(blob + o + 8);
    }
    if (!code || code[0] >> 16 != 0) return 0;          /* program type 0 = pixel shader */
    clen /= 4;
    for (p = 2; p < clen; p += ln) {                     /* skip version + length tokens */
        tok = code[p]; op = tok & 0x7ff; ln = (tok >> 24) & 0x7f;
        if (op == 0x35) ln = p + 1 < clen ? code[p + 1] : 0;   /* customdata: length in the next dword */
        if (!ln || ln > clen - p) return 0;
        if (op == 0x62 && ((tok >> 11) & 0xf) == 2) changed++;  /* dcl_input_ps linear */
    }
    if (!changed) return 0;
    for (p = 2; p < clen; p += ln) {                     /* walk checked: now patch */
        tok = code[p]; op = tok & 0x7ff; ln = op == 0x35 ? code[p + 1] : (tok >> 24) & 0x7f;
        if (op == 0x62 && ((tok >> 11) & 0xf) == 2) code[p] = (tok & ~(0xfu << 11)) | (3u << 11);
    }
    dxbc_checksum(blob, len, (DWORD *)(blob + 4));
    return changed;
}
