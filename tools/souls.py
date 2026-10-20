import ctypes
import json
import os
import struct
import zlib

_OODLE = None


def _oodle():
    """OodleLZ_Decompress do oo2core_6_win64.dll (so para DCX KRAK; o DARK SOULS III usa DFLT/zlib).
    Windows: defina OODLE_DLL com o caminho do oo2core_6_win64.dll (pasta Game do jogo).
    Linux: defina LINOODLE com o caminho do liblinoodle.so (github.com/McSimp/linoodle)."""
    global _OODLE
    if _OODLE is None:
        if os.name == "nt":
            lib = ctypes.WinDLL(os.environ.get("OODLE_DLL", "oo2core_6_win64.dll"))
        else:
            so = os.environ.get("LINOODLE", "liblinoodle.so")
            cwd = os.getcwd()
            os.chdir(os.path.dirname(os.path.abspath(so)) if os.path.exists(so) else cwd)
            lib = ctypes.CDLL(os.path.abspath(so) if os.path.exists(so) else so)
            os.chdir(cwd)
        f = lib.OodleLZ_Decompress
        f.restype = ctypes.c_size_t
        f.argtypes = [ctypes.c_char_p, ctypes.c_size_t, ctypes.c_char_p, ctypes.c_size_t] + \
            [ctypes.c_int64] * 3 + [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p,
                                    ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_int64]
        _OODLE = f
    return _OODLE


def dcx_decompress(data: bytes) -> bytes:
    assert data[:4] == b"DCX\0"
    usize, csize = struct.unpack(">II", data[0x1C:0x24])
    fmt = data[0x28:0x2C]
    payload = data[0x4C:0x4C + csize]
    if fmt == b"DFLT":
        return zlib.decompress(payload)
    if fmt == b"KRAK":
        dst = ctypes.create_string_buffer(usize + 64)
        r = _oodle()(payload, len(payload), dst, usize, 1, 0, 0, None, 0, None, None, None, 0, 3)
        assert r == usize, f"Oodle falhou ({r} != {usize})"
        return dst.raw[:usize]
    raise ValueError(fmt)


def bnd4_unpack(data: bytes):
    assert data[:4] == b"BND4"
    big_endian = data[9] == 1 if False else False
    file_count = struct.unpack_from("<i", data, 0x0C)[0]
    unicode = data[0x30] == 1
    raw = data[0x31]
    rev = (raw & 1) and not (raw & 0x80)
    fmt = raw if rev else int(f"{raw:08b}"[::-1], 2)
    entry_size = struct.unpack_from("<q", data, 0x20)[0]
    files = []
    off = 0x40
    for i in range(file_count):
        e = data[off:off + entry_size]
        flags = e[0]
        csize = struct.unpack_from("<q", e, 8)[0]
        pos = 0x10
        usize = csize
        if fmt & 0x20:  # compressed size present
            usize = struct.unpack_from("<q", e, 0x10)[0]
            pos = 0x18
        doff = struct.unpack_from("<I", e, pos)[0]
        pos += 4
        fid = None
        if fmt & 0x02:
            fid = struct.unpack_from("<i", e, pos)[0]
            pos += 4
        name = None
        if fmt & 0x04 or fmt & 0x08:
            noff = struct.unpack_from("<I", e, pos)[0]
            if unicode:
                end = noff
                while data[end:end + 2] != b"\0\0":
                    end += 2
                name = data[noff:end].decode("utf-16-le")
            else:
                end = data.index(b"\0", noff)
                name = data[noff:end].decode("shift-jis")
        files.append({"id": fid, "name": name, "data": data[doff:doff + csize], "flags": flags})
        off += entry_size
    return files


# ---------------- ESD -----------------

class ESD:
    pass


def parse_esd(b: bytes):
    assert b[:4] == b"fsSL", b[:4]
    hdr = struct.unpack_from("<4s" + "i" * 20, b, 0)
    (magic, one, dsc, dsc2, h54, data_size, six, h48, one2, sgsize, sgcount, ssize, scount,
     csz, ccount, cmdsz, cmdcount, argsz, argcount, condoffoff, condoffcount) = hdr
    ds = 0x6C
    q = lambda off: struct.unpack_from("<q", b, ds + off)[0]
    # data header
    p = ds + 0x18
    sgs_off, sg_count, name_off, name_len = struct.unpack_from("<qqqq", b, p)
    esd = {"groups": {}, "dsc": dsc}
    p = ds + sgs_off
    groups = []
    for i in range(sg_count):
        gid, st_off, st_cnt, st_off2 = struct.unpack_from("<qqqq", b, p)
        p += 32
        groups.append((gid, st_off, st_cnt))

    def read_cmds(off, cnt):
        res = []
        for i in range(cnt):
            bank, cid, aoff, acnt = struct.unpack_from("<iiqq", b, ds + off + i * 0x18)
            args = []
            for j in range(acnt):
                ao, asz = struct.unpack_from("<qq", b, ds + aoff + j * 16)
                args.append(b[ds + ao:ds + ao + asz])
            res.append((bank, cid, args))
        return res

    cond_cache = {}

    def read_cond(off, state_ids):
        if off in cond_cache:
            return cond_cache[off]
        st_off, pc_off, pc_cnt, co_off, co_cnt, ev_off, ev_len = struct.unpack_from("<7q", b, ds + off)
        c = {"off": off}
        cond_cache[off] = c
        c["target"] = state_ids.get(st_off) if st_off != -1 else None
        c["pass"] = read_cmds(pc_off, pc_cnt)
        subs = [struct.unpack_from("<q", b, ds + co_off + 8 * k)[0] for k in range(co_cnt)]
        c["subs"] = [read_cond(s, state_ids) for s in subs]
        c["eval"] = b[ds + ev_off:ds + ev_off + ev_len]
        return c

    for gid, st_off, st_cnt in groups:
        state_ids = {}
        for k in range(st_cnt):
            so = st_off + k * 0x48
            sid = struct.unpack_from("<q", b, ds + so)[0]
            state_ids[so] = sid
        states = {}
        for k in range(st_cnt):
            so = st_off + k * 0x48
            sid, co_off, co_cnt, en_off, en_cnt, ex_off, ex_cnt, wh_off, wh_cnt = struct.unpack_from("<9q", b, ds + so)
            conds = [read_cond(struct.unpack_from("<q", b, ds + co_off + 8 * m)[0], state_ids) for m in range(co_cnt)]
            states[sid] = {
                "conds": conds,
                "entry": read_cmds(en_off, en_cnt),
                "exit": read_cmds(ex_off, ex_cnt),
                "while": read_cmds(wh_off, wh_cnt),
                "offset": so,
            }
        esd["groups"][gid] = states
    return esd


# ------------- names ---------------
# Nomes das funcoes (opcional, so para os dumps legiveis): ESDLang/dist/ESDScriptingDocumentation_Talk.json
_doc_path = os.environ.get("ESDLANG_TALK_JSON", os.path.join(os.path.dirname(os.path.abspath(__file__)), "ESDScriptingDocumentation_Talk.json"))
_doc = json.load(open(_doc_path, encoding="utf-8")) if os.path.exists(_doc_path) else {"commands": [], "functions": []}
CMD_NAMES = {}
FUNC_NAMES = {}
for c in _doc["commands"]:
    g = c.get("games") or c.get("games_used") or []
    if "bb" in g or (c["bank"], c["id"]) not in CMD_NAMES:
        CMD_NAMES[(c["bank"], c["id"])] = c.get("name", f"C{c['bank']}_{c['id']}")
for f in _doc["functions"]:
    g = f.get("games") or f.get("games_used") or []
    if "bb" in g or f["id"] not in FUNC_NAMES:
        FUNC_NAMES[f["id"]] = f.get("name", f"F{f['id']}")


def group_name(gid):
    # talk groups: 0x7fffffff - x  => t{xxx}_x{n}?
    return f"x{0x7fffffff - gid}" if gid > 0x70000000 else f"g{gid}"


def disasm_expr(e: bytes):
    out = []
    regs = [""] * 8
    i = 0
    while i < len(e):
        c = e[i]
        if c <= 0x7F:
            out.append(str(c - 64)); i += 1
        elif c == 0x80:
            out.append(repr(struct.unpack_from("<f", e, i + 1)[0])); i += 5
        elif c == 0x81:
            out.append(repr(struct.unpack_from("<d", e, i + 1)[0])); i += 9
        elif c == 0x82:
            out.append(str(struct.unpack_from("<i", e, i + 1)[0])); i += 5
        elif 0x84 <= c <= 0x8A:
            n = c - 0x84
            args = [out.pop() for _ in range(n)][::-1]
            fid = out.pop()
            try:
                name = FUNC_NAMES.get(int(fid), f"F{fid}")
            except ValueError:
                name = f"F[{fid}]"
            out.append(f"{name}({', '.join(args)})"); i += 1
        elif c == 0x8D:
            out.append(f"-({out.pop()})"); i += 1
        elif 0x8C <= c <= 0x99:
            ops = {0x8C: "+", 0x8E: "-", 0x8F: "*", 0x90: "/", 0x91: "<=", 0x92: ">=", 0x93: "<", 0x94: ">", 0x95: "==", 0x96: "!=", 0x98: "and", 0x99: "or"}
            r = out.pop(); l = out.pop()
            out.append(f"({l} {ops.get(c, hex(c))} {r})"); i += 1
        elif c == 0xA1:
            i += 1
        elif c == 0xA5:
            end = i + 1
            while e[end:end + 2] != b"\0\0":
                end += 2
            out.append(repr(e[i + 1:end].decode("utf-16-le"))); i = end + 2
        elif c == 0xA6:
            i += 1
        elif 0xA7 <= c <= 0xAE:
            regs[c - 0xA7] = out[-1]; i += 1
        elif 0xAF <= c <= 0xB6:
            out.append(regs[c - 0xAF]); i += 1
        elif c == 0xB7:
            i += 1
        elif c == 0xB8:
            out.append(f"ARG[{out.pop()}]"); i += 1
        elif c == 0xB9:
            out.append("CALL_RESULT"); i += 1
        elif c == 0xBA:
            out.append("ONGOING"); i += 1
        else:
            out.append(f"<{c:02x}>"); i += 1
    return " ".join(out)


def fmt_cmd(cmd):
    bank, cid, args = cmd
    a = ", ".join(disasm_expr(x) for x in args)
    if bank == 6:
        return f"CALL {group_name(cid)}({a})"
    return f"{CMD_NAMES.get((bank, cid), f'C{bank}_{cid}')}({a})"


def dump_esd(esd):
    lines = []
    for gid in sorted(esd["groups"]):
        states = esd["groups"][gid]
        lines.append(f"=== group {gid} ({group_name(gid)}) states={len(states)}")
        for sid in sorted(states):
            st = states[sid]
            lines.append(f"  state {sid}:")
            for kind in ("entry", "exit", "while"):
                for c in st[kind]:
                    lines.append(f"    {kind}: {fmt_cmd(c)}")

            def dc(c, ind):
                lines.append(f"{' ' * ind}if {disasm_expr(c['eval'])} -> {c['target']}")
                for pc in c["pass"]:
                    lines.append(f"{' ' * (ind + 4)}pass: {fmt_cmd(pc)}")
                for s in c["subs"]:
                    dc(s, ind + 4)
            for c in st["conds"]:
                dc(c, 4)
    return "\n".join(lines)


def parse_fmg(b: bytes):
    import struct as S
    groups, strings = S.unpack_from("<ii", b, 0x0C)
    so = S.unpack_from("<q", b, 0x18)[0]
    out = {}
    p = 0x28
    for g in range(groups):
        idx, first, last, _ = S.unpack_from("<iiii", b, p)
        p += 16
        for j in range(last - first + 1):
            o = S.unpack_from("<q", b, so + (idx + j) * 8)[0]
            if o:
                e = o
                while b[e:e + 2] != b"\0\0":
                    e += 2
                out[first + j] = b[o:e].decode("utf-16-le")
            else:
                out[first + j] = None
    return out
