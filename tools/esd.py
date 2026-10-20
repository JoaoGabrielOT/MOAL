# SPDX-License-Identifier: GPL-2.0-or-later
"""Talk scripts (script/talk/*.talkesdbnd.dcx: a BND4 of .esd files) as a model that edits and
writes back. Ported from droogie's bbhost (https://github.com/droogie/bbhost, GPL-3.0-or-later,
engine/esd.cpp), which checked that parse then serialize gives the input bytes again for all 271
talk scripts of the 1.09 dump.

An .esd is a set of state machines (EzState, long format "fsSL"): state groups of states; a
state's entry, exit and while commands; its conditions, each an expression (bytecode), a
target state, pass commands and nested conditions. Offsets are relative to the data block at
0x6c, laid out section by section: header (0x48), groups (0x20), states (0x48), conditions
(0x38), commands (0x18), command args (0x10), condition-pointer lists (8), expression bytecode,
the script's name (UTF-16, 2-aligned).

Two things the game's own writer does are kept for byte-identical output: each group's states
are followed by a copy of its initial state (same id, own condition list, not counted in the
group), and each group's initial-state condition list is written twice, the second copy
unreferenced. Every element remembers the offset it was read from (its key) and is written back
in key order; added elements have no key and follow the originals of their section.
"""
import struct

BASE = 0x6c          # the data block: every offset counts from here
NEW = (1 << 63) - 1  # the key of an added element


class EsdError(ValueError):
    pass


class Expr:
    def __init__(self, code, key=NEW):
        self.code, self.key = bytes(code), key


class Run:
    """A contiguous list in its section (commands, args, condition pointers): indices into the
    matching pool. An empty run writes the offset it was read with."""
    def __init__(self, items, key=NEW, empty_off=-1):
        self.items, self.key, self.empty_off = list(items), key, empty_off


class Cmd:
    def __init__(self, bank, id, args):
        self.bank, self.id, self.args = bank, id, args


class Cond:
    def __init__(self, target=-1, eval=-1, pass_=-1, subs=-1, key=NEW):
        self.target, self.eval, self.pass_, self.subs, self.key = target, eval, pass_, subs, key


class State:
    def __init__(self, id, conds=-1, entry=-1, exit=-1, whiles=-1):
        self.id, self.conds, self.entry, self.exit, self.whiles = id, conds, entry, exit, whiles


class Group:
    def __init__(self, id, states=None, copy=-1, key=NEW):
        self.id, self.states, self.copy, self.key = id, list(states or []), copy, key


class Script:
    def __init__(self):
        self.head = self.dhead = self.dtail = self.name = b''
        self.empty_groups_off = -1
        self.exprs, self.runs, self.cmds, self.conds, self.states, self.groups = [], [], [], [], [], []
        self.dead = []  # condition-pointer runs nothing references

    # Builders for edits: each returns the new element's index.
    def expr(self, code):
        self.exprs.append(Expr(code))
        return len(self.exprs) - 1

    def run(self, items):
        self.runs.append(Run(items))
        return len(self.runs) - 1

    def cmd(self, bank, id, args):
        xs = [self.expr(a) for a in args]
        self.cmds.append(Cmd(bank, id, self.run(xs)))
        return len(self.cmds) - 1

    def cond(self, target, eval, pass_=-1, subs=-1):
        ev = self.expr(eval)
        p = pass_ if pass_ >= 0 else self.run([])
        sb = subs if subs >= 0 else self.run([])
        self.conds.append(Cond(target, ev, p, sb))
        return len(self.conds) - 1

    def state(self, id):
        c, e, x, w = self.run([]), self.run([]), self.run([]), self.run([])
        self.states.append(State(id, c, e, x, w))
        return len(self.states) - 1

    def group(self, id):
        return next((g for g in self.groups if g.id == id), None)

    def state_in(self, group, id):
        return next((st for st in group.states if self.states[st].id == id), -1)


class _Parser:
    def __init__(self, data, script):
        self.d, self.s = data, script
        self.expr_memo, self.arg_memo, self.cmd_memo, self.condrun_memo = {}, {}, {}, {}
        self.cond_memo, self.state_at = {}, {}
        self.depth = 0

    def i32(self, at):
        if at < 0 or at + 4 > len(self.d):
            raise EsdError('an offset outside the file')
        return struct.unpack_from('<i', self.d, at)[0]

    def q(self, rel):
        at = BASE + rel
        if rel < 0 or at + 8 > len(self.d):
            raise EsdError('an offset outside the file')
        return struct.unpack_from('<q', self.d, at)[0]

    def bytes(self, rel, n):
        at = BASE + rel
        if rel < 0 or n < 0 or at + n > len(self.d):
            raise EsdError('an offset outside the file')
        return self.d[at:at + n]

    def expr(self, off, n):
        if (off, n) not in self.expr_memo:
            self.s.exprs.append(Expr(self.bytes(off, n), off))
            self.expr_memo[(off, n)] = len(self.s.exprs) - 1
        return self.expr_memo[(off, n)]

    def argrun(self, off, n):
        if (off, n) not in self.arg_memo:
            run = Run([], off if n else NEW, off)
            for j in range(n):
                run.items.append(self.expr(self.q(off + 0x10 * j), self.q(off + 0x10 * j + 8)))
            self.s.runs.append(run)
            self.arg_memo[(off, n)] = len(self.s.runs) - 1
        return self.arg_memo[(off, n)]

    def cmdrun(self, off, n):
        if (off, n) not in self.cmd_memo:
            run = Run([], off if n else NEW, off)
            for j in range(n):
                c = off + 0x18 * j
                bank, id = self.i32(BASE + c), self.i32(BASE + c + 4)
                args = self.argrun(self.q(c + 8), self.q(c + 16))
                self.s.cmds.append(Cmd(bank, id, args))
                run.items.append(len(self.s.cmds) - 1)
            self.s.runs.append(run)
            self.cmd_memo[(off, n)] = len(self.s.runs) - 1
        return self.cmd_memo[(off, n)]

    def cond(self, off):
        if off in self.cond_memo:
            return self.cond_memo[off]
        self.depth += 1
        if self.depth > 64:
            raise EsdError('conditions nested too deeply')
        tgt, po, pc, so, sc, eo, el = (self.q(off + 8 * k) for k in range(7))
        idx = len(self.s.conds)
        self.s.conds.append(Cond())
        self.cond_memo[off] = idx
        target = -1
        if tgt >= 0:
            if tgt not in self.state_at:
                raise EsdError('a condition targets no state')
            target = self.state_at[tgt]
        ev = self.expr(eo, el)
        pass_ = self.cmdrun(po, pc)
        subs = self.condrun(so, sc)
        self.s.conds[idx] = Cond(target, ev, pass_, subs, off)
        self.depth -= 1
        return idx

    def condrun(self, off, n):
        if (off, n) not in self.condrun_memo:
            run = Run([], off if n else NEW, off)
            for j in range(n):
                run.items.append(self.cond(self.q(off + 8 * j)))
            self.s.runs.append(run)
            self.condrun_memo[(off, n)] = len(self.s.runs) - 1
        return self.condrun_memo[(off, n)]


def parse(data):
    data = bytes(data)
    if len(data) < BASE + 0x48 or data[:4] != b'fsSL':
        raise EsdError('not a long-format talk script')
    s = Script()
    p = _Parser(data, s)
    s.head, s.dhead, s.dtail = data[:BASE], data[BASE:BASE + 0x18], data[BASE + 0x38:BASE + 0x48]
    groups_off, ngroups, name_off, name_len = p.q(0x18), p.q(0x20), p.q(0x28), p.q(0x30)
    if not 0 <= ngroups <= 100000 or not 0 <= name_len <= 4096:
        raise EsdError('implausible counts')
    if ngroups == 0:
        s.empty_groups_off = groups_off
    s.name = p.bytes(name_off, 2 * name_len)
    raw, total = [], 0
    for g in range(ngroups):
        at = groups_off + 0x20 * g
        gid, goff, gn = p.q(at), p.q(at + 8), p.q(at + 16)
        if p.q(at + 24) != goff or not 1 <= gn <= 100000:
            raise EsdError('a state group that is not one array')
        raw.append((gid, goff, gn))
        for k in range(gn + 1):  # + the initial state's copy
            p.state_at[goff + 0x48 * k] = len(s.states)
            s.states.append(State(p.q(goff + 0x48 * k)))
        total += gn + 1
    if total != p.i32(0x30):
        raise EsdError('the state count does not match the groups')
    for gid, goff, gn in raw:
        group = Group(gid, [], -1, goff)
        for k in range(gn + 1):
            at = goff + 0x48 * k
            si = p.state_at[at]
            conds = p.condrun(p.q(at + 8), p.q(at + 16))
            entry = p.cmdrun(p.q(at + 24), p.q(at + 32))
            exit = p.cmdrun(p.q(at + 40), p.q(at + 48))
            whiles = p.cmdrun(p.q(at + 56), p.q(at + 64))
            st = s.states[si]
            st.conds, st.entry, st.exit, st.whiles = conds, entry, exit, whiles
            if k < gn:
                group.states.append(si)
            else:
                group.copy = si
        s.groups.append(group)
    # Condition-pointer slots no list accounts for: the game's writer repeats each group's
    # initial-state list. Kept as unreferenced lists, in place.
    co, con = p.i32(0x4c), p.i32(0x50)
    covered = set()
    for (off, n) in p.condrun_memo:
        covered.update(off + 8 * j for j in range(n))
    at = co
    while at < co + 8 * con:
        if at in covered:
            at += 8
            continue
        end = at
        while end < co + 8 * con and end not in covered:
            end += 8
        dead = Run([], at, at)
        for x in range(at, end, 8):
            dead.items.append(p.cond(p.q(x)))
        s.runs.append(dead)
        s.dead.append(len(s.runs) - 1)
        at = end
    return s


def serialize(script):
    import copy
    s = copy.deepcopy(script)
    groups = sorted(range(len(s.groups)), key=lambda k: s.groups[k].key)  # stable
    for g in groups:
        grp = s.groups[g]
        if grp.copy >= 0 or not grp.states:
            continue  # a new group gets the copy the game's files carry
        first = s.states[grp.states[0]]
        c = s.state(first.id)
        s.runs[s.states[c].conds].items = list(s.runs[first.conds].items)
        grp.copy = c
    states = []
    for g in groups:
        states += s.groups[g].states + [s.groups[g].copy]
    conds, seen = [], set()

    def walk(c):
        if c in seen:
            return
        seen.add(c)
        conds.append(c)
        for sc in s.runs[s.conds[c].subs].items:
            walk(sc)
    for st in states:
        for c in s.runs[s.states[st].conds].items:
            walk(c)
    conds.sort(key=lambda c: s.conds[c].key)

    def uniq(wanted):
        out, taken = [], set()
        for r in wanted:
            if r < 0 or not s.runs[r].items or r in taken:
                continue
            taken.add(r)
            out.append(r)
        out.sort(key=lambda r: s.runs[r].key)
        return out
    want = []
    for st in states:
        x = s.states[st]
        want += [x.entry, x.exit, x.whiles]
    want += [s.conds[c].pass_ for c in conds]
    cmdruns = uniq(want)
    cmds = [cm for r in cmdruns for cm in s.runs[r].items]
    argruns = uniq([s.cmds[cm].args for cm in cmds])
    want = [s.states[st].conds for st in states] + [s.conds[c].subs for c in conds] + list(s.dead)
    condruns = uniq(want)
    exprs, expr_seen = [], set()

    def add_expr(x):
        if x not in expr_seen:
            expr_seen.add(x)
            exprs.append(x)
    for r in argruns:
        for x in s.runs[r].items:
            add_expr(x)
    for c in conds:
        add_expr(s.conds[c].eval)
    exprs.sort(key=lambda x: s.exprs[x].key)

    state_pos, cond_pos, run_pos, expr_pos = {}, {}, {}, {}
    off = 0x48
    groups_off = off
    off += 0x20 * len(groups)
    for st in states:
        state_pos[st] = off
        off += 0x48
    for c in conds:
        cond_pos[c] = off
        off += 0x38
    nargs = nptrs = 0
    for r in cmdruns:
        run_pos[r] = off
        off += 0x18 * len(s.runs[r].items)
    for r in argruns:
        run_pos[r] = off
        off += 0x10 * len(s.runs[r].items)
        nargs += len(s.runs[r].items)
    condoffs = off
    for r in condruns:
        run_pos[r] = off
        off += 8 * len(s.runs[r].items)
        nptrs += len(s.runs[r].items)
    for x in exprs:
        expr_pos[x] = off
        off += len(s.exprs[x].code)
    name_block = off
    name_off = off + (off & 1)
    size = name_off + len(s.name)

    out = bytearray(BASE + size)

    def P(rel, v):
        struct.pack_into('<q', out, BASE + rel, v)

    def ref(r):
        run = s.runs[r]
        return (run.empty_off, 0) if not run.items else (run_pos[r], len(run.items))
    out[BASE:BASE + len(s.dhead)] = s.dhead
    P(0x18, s.empty_groups_off if not groups else groups_off)
    P(0x20, len(groups))
    P(0x28, name_off)
    P(0x30, len(s.name) // 2)
    out[BASE + 0x38:BASE + 0x38 + len(s.dtail)] = s.dtail
    for k, g in enumerate(groups):
        grp = s.groups[g]
        at, first = groups_off + 0x20 * k, state_pos[grp.states[0]]
        P(at, grp.id), P(at + 8, first), P(at + 16, len(grp.states)), P(at + 24, first)
    for st in states:
        x, at = s.states[st], state_pos[st]
        P(at, x.id)
        for k, lst in enumerate((x.conds, x.entry, x.exit, x.whiles)):
            ro, rn = ref(lst)
            P(at + 8 + 16 * k, ro), P(at + 16 + 16 * k, rn)
    for c in conds:
        x, at = s.conds[c], cond_pos[c]
        P(at, state_pos[x.target] if x.target >= 0 else -1)
        po, pn = ref(x.pass_)
        so, sn = ref(x.subs)
        P(at + 8, po), P(at + 16, pn), P(at + 24, so), P(at + 32, sn)
        P(at + 40, expr_pos[x.eval]), P(at + 48, len(s.exprs[x.eval].code))
    for r in cmdruns:
        at = run_pos[r]
        for cm in s.runs[r].items:
            x = s.cmds[cm]
            struct.pack_into('<ii', out, BASE + at, x.bank, x.id)
            ao, an = ref(x.args)
            P(at + 8, ao), P(at + 16, an)
            at += 0x18
    for r in argruns:
        at = run_pos[r]
        for x in s.runs[r].items:
            P(at, expr_pos[x]), P(at + 8, len(s.exprs[x].code))
            at += 0x10
    for r in condruns:
        at = run_pos[r]
        for c in s.runs[r].items:
            P(at, cond_pos[c])
            at += 8
    for x in exprs:
        out[BASE + expr_pos[x]:BASE + expr_pos[x] + len(s.exprs[x].code)] = s.exprs[x].code
    out[BASE + name_off:BASE + name_off + len(s.name)] = s.name
    h = bytearray(s.head)
    for at, v in ((0x14, size), (0x28, len(groups)), (0x30, len(states)), (0x38, len(conds)), (0x40, len(cmds)),
                  (0x48, nargs), (0x4c, condoffs), (0x50, nptrs), (0x54, name_block), (0x58, len(s.name) // 2),
                  (0x5c, size), (0x64, size)):
        struct.pack_into('<I', h, at, v & 0xffffffff)
    out[:BASE] = h
    return bytes(out)


# Expression bytecode, as the game's own conditions and arguments are written.
def lit(v):
    if -64 <= v <= 63:
        return bytes([0x40 + v])
    return b'\x82' + struct.pack('<i', v)


def call(fn, args):
    out = bytearray(lit(fn))
    for a in args:
        out += lit(a)
    out += bytes([0x84 + len(args), 0xa6])
    return bytes(out)


def done(code):
    return bytes(code) + b'\xa1'
