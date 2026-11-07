"""CRI .usm movies (CRI Mana, MPEG-1 video + ADX audio), e.g. the opening Resource/UI/Title/OP.usm.
  python -I usmtool.py info     in.usm
  python -I usmtool.py demux    in.usm out.m1v              video stream -> MPEG-1 elementary stream
  python -I usmtool.py mux      template.usm new.m1v out.usm
        new video in place of the template's (any size, same frame count); audio, timing, interleave kept
  python -I usmtool.py selftest in.usm                      demux + mux must give back the identical file
Layout: CRID (directory, 2048 bytes) | @SFV/@SFA headers | @SFV seek table | one @SFV chunk per picture
(coded order, I pictures carry the sequence + GOP headers) interleaved with @SFA audio chunks.
Every chunk is padded to a multiple of 32 bytes.
"""
import re, struct, sys

FMT = {0: 'B', 1: 'b', 2: 'H', 3: 'h', 4: 'I', 5: 'i', 6: 'Q', 7: 'q', 8: 'f', 0xa: 'I', 0xb: 'II'}


def chunks(d):
    """(offset, sig, type, payload) for every chunk."""
    i = 0
    while i + 8 <= len(d):
        size, = struct.unpack('>I', d[i + 4:i + 8])
        pad, = struct.unpack('>H', d[i + 10:i + 12])
        yield i, d[i:i + 4], d[i + 15] & 3, d[i + 8 + d[i + 9]:i + 8 + size - pad]
        i += 8 + size


def chunk(tpl_hdr, payload, total=None):
    """Chunk with the template's 32-byte header fields and this payload, zero padded."""
    pad = (total - 32 - len(payload)) if total else -(32 + len(payload)) % 32
    return (tpl_hdr[:4] + struct.pack('>I', 24 + len(payload) + pad) + tpl_hdr[8:9] + b'\x18' +
            struct.pack('>H', pad) + tpl_hdr[12:32] + payload + bytes(pad))


class Utf:
    """@UTF table in a chunk payload: read values, patch numbers in place, replace all rows."""
    def __init__(self, p):
        self.p = bytearray(p); t = 8
        (self.rows_off, self.str_off, self.data_off, name, ncol, self.rowlen,
         self.nrows) = struct.unpack('>HIIIHHI', p[t + 2:t + 24])
        self.name = self._s(name); self.cols = []; q = t + 24; roff = 0
        for _ in range(ncol):
            flag = p[q]; cname = self._s(struct.unpack('>I', p[q + 1:q + 5])[0]); q += 5
            fmt = '>' + FMT[flag & 0xf]; n = struct.calcsize(fmt)
            if flag & 0xf0 == 0x30: self.cols.append((cname, fmt, flag & 0xf, q, None)); q += n
            elif flag & 0xf0 == 0x50: self.cols.append((cname, fmt, flag & 0xf, None, roff)); roff += n
            else: self.cols.append((cname, fmt, flag & 0xf, None, None))

    def _s(self, o):
        a = 8 + self.str_off + o
        return bytes(self.p[a:self.p.index(0, a)]).decode('ascii', 'replace')

    def _at(self, col, row):
        _, fmt, typ, const, roff = col
        return const if const is not None else 8 + self.rows_off + row * self.rowlen + roff

    def rows(self):
        out = []
        for r in range(self.nrows):
            row = {}
            for col in self.cols:
                if col[3] is None and col[4] is None: row[col[0]] = None; continue
                v = struct.unpack_from(col[1], self.p, self._at(col, r))
                row[col[0]] = self._s(v[0]) if col[2] == 0xa else v[0] if len(v) == 1 else v
            out.append(row)
        return out

    def set(self, row, name, value):
        col = next(c for c in self.cols if c[0] == name)
        struct.pack_into(col[1], self.p, self._at(col, row), value)

    def replace_rows(self, rows):
        """New per-row values (numbers only); string and data pools follow the rows and move with them."""
        per_row = [c for c in self.cols if c[4] is not None]
        new = b''.join(b''.join(struct.pack(c[1], r[c[0]]) for c in per_row) for r in rows)
        a = 8 + self.rows_off; b = a + self.rowlen * self.nrows; delta = len(new) - (b - a)
        assert self.str_off >= self.rows_off + self.rowlen * self.nrows
        self.p[a:b] = new; self.nrows = len(rows); self.str_off += delta; self.data_off += delta
        struct.pack_into('>I', self.p, 4, struct.unpack_from('>I', self.p, 4)[0] + delta)
        struct.pack_into('>II', self.p, 8 + 4, self.str_off, self.data_off)
        struct.pack_into('>I', self.p, 8 + 20, self.nrows)


def demux(d):
    return b''.join(p for _, sig, typ, p in chunks(d) if sig == b'@SFV' and typ == 0)


def pictures(es):
    """Split an MPEG-1 stream into pictures; sequence/GOP headers go with the picture after them."""
    starts, pending, types = [], None, []
    for m in re.finditer(rb'\x00\x00\x01[\x00\xb3\xb8]', es):
        code = es[m.start() + 3]
        if code != 0:
            if pending is None: pending = m.start()
            continue
        starts.append(m.start() if pending is None else pending); pending = None
        types.append((es[m.start() + 5] >> 3) & 7)
    starts[0] = 0
    return [es[a:b] for a, b in zip(starts, starts[1:] + [len(es)])], types


def mux(tpl, es):
    pics, types = pictures(es)
    w = (es[4] << 4) | (es[5] >> 4); h = ((es[5] & 15) << 8) | es[6]
    src = list(chunks(tpl))
    nv = sum(1 for _, sig, typ, _ in src if sig == b'@SFV' and typ == 0)
    if nv != len(pics): sys.exit(f'frame count differs: template {nv}, new stream {len(pics)}')
    hdr = lambda o: tpl[o:o + 32]
    out, k, vid_chunk_at, arow = [], 0, [], None
    for o, sig, typ, p in src:
        if sig == b'@SFV' and typ == 0:
            vid_chunk_at.append(len(out)); out.append(chunk(hdr(o), pics[k])); k += 1
        elif sig == b'@SFV' and typ == 3:
            seek_i, seek_o = len(out), o; seek = Utf(p)
            seek.replace_rows([{'ofs_byte': 0, 'ofs_frmid': n, 'num_skip': 0, 'resv': 0}
                               for n, t in enumerate(types) if t == 1])
            out.append(chunk(hdr(o), bytes(seek.p)))
        elif sig == b'@SFV' and typ == 1: vhdr_i, vhdr_o, vhdr = len(out), o, Utf(p); out.append(None)
        elif sig == b'CRID': crid_i, crid_o, crid = len(out), o, Utf(p); out.append(None)
        else:
            if sig == b'@SFA' and typ == 1: arow = Utf(p).rows()[0]
            out.append(tpl[o:o + 8 + struct.unpack('>I', tpl[o + 4:o + 8])[0]])
    vrow = vhdr.rows()[0]
    ixsize = max(len(out[i]) for i in vid_chunk_at)
    for n, v in (('width', w), ('height', h), ('mat_width', w), ('mat_height', h), ('disp_width', w),
                 ('disp_height', h), ('ixsize', ixsize), ('metadata_size', len(out[seek_i]))):
        vhdr.set(0, n, v)
    out[vhdr_i] = chunk(hdr(vhdr_o), bytes(vhdr.p))
    out[crid_i] = chunk(hdr(crid_o), bytes(crid.p), total=2048)
    offs = [0]
    for c in out: offs.append(offs[-1] + len(c))
    seek.replace_rows([{'ofs_byte': offs[vid_chunk_at[n]], 'ofs_frmid': n, 'num_skip': 0, 'resv': 0}
                       for n, t in enumerate(types) if t == 1])
    out[seek_i] = chunk(hdr(seek_o), bytes(seek.p))
    # directory: whole file, video, audio sizes and rates
    secs = (arow['total_samples'] / arow['sampling_rate'] if arow else       # CRI times by the audio
            vrow['total_frames'] * vrow['framerate_d'] / vrow['framerate_n'])
    rows = crid.rows(); vbytes = len(es); abytes = rows[2]['filesize']
    old_min = rows[1]['minbuf']; vmin = max(len(p) for p in pics)
    crid.set(0, 'filesize', offs[-1]); crid.set(1, 'filesize', vbytes)
    crid.set(1, 'minbuf', vmin); crid.set(0, 'minbuf', rows[0]['minbuf'] - old_min + vmin)
    crid.set(1, 'avbps', int(vbytes * 8 / secs)); crid.set(0, 'avbps', int(vbytes * 8 / secs) + rows[2]['avbps'])
    out[crid_i] = chunk(hdr(crid_o), bytes(crid.p), total=2048)
    return b''.join(out)


def info(d):
    for _, sig, typ, p in chunks(d):
        if typ in (1, 3) and p[:4] == b'@UTF':
            u = Utf(p); r = u.rows()
            print(sig.decode(), u.name, r if len(r) < 4 else r[:3] + [f'... {len(r)} rows'])


if __name__ == '__main__':
    a = sys.argv[1:]
    if a[:1] == ['info']: info(open(a[1], 'rb').read())
    elif a[:1] == ['demux']: open(a[2], 'wb').write(demux(open(a[1], 'rb').read()))
    elif a[:1] == ['mux']: open(a[3], 'wb').write(mux(open(a[1], 'rb').read(), open(a[2], 'rb').read()))
    elif a[:1] == ['selftest']:
        d = open(a[1], 'rb').read(); r = mux(d, demux(d))
        diff = next((i for i in range(min(len(d), len(r))) if d[i] != r[i]), None) if r != d else None
        print('identical' if r == d else f'DIFFERENT: sizes {len(d)} {len(r)}, first difference at {diff}')
        sys.exit(r != d)
    else: print(__doc__)
