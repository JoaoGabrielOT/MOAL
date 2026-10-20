"""
Simulador simples de EzState para testar o menu das lanternas sem o jogo.
Avalia o bytecode, executa os eventos (registra os comandos) e segue as transicoes, com
CALL de sub-maquinas. As funcoes do jogo sao respondidas por um ambiente de teste.
"""
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from souls import parse_esd, bnd4_unpack, dcx_decompress, fmt_cmd  # noqa: E402

ONGOING = object()


class Env:
    def __init__(self, flags=None):
        self.flags = dict(flags or {})
        self.talk_result = 0
        self.menu_open = set()      # menus abertos (CheckSpecificPersonMenuIsOpen)
        self.log = []
        self.talk_list = []
        self.dialog_open = False
        self.regs = [None] * 8
        self.status = {}

    def func(self, fid, args):
        if fid == 15:
            return self.flags.get(args[0], 0)
        if fid == 23:
            return self.talk_result
        if fid == 59:
            return 1 if args[0] in self.menu_open else 0
        if fid == 53:
            return 1 if 'talk' in self.menu_open else 0
        if fid == 21:
            return 1 if self.dialog_open else 0
        if fid == 22:
            return 1
        if fid == 29:
            return self.status.get(args[0], 0)
        if fid in (1, 33, 52):
            return 0
        raise KeyError(f'funcao {fid}')

    def command(self, bank, cid, args):
        self.log.append((bank, cid, args))
        if (bank, cid) == (1, 11):
            self.flags[args[0]] = args[1]
        if (bank, cid) == (1, 20):
            self.talk_list = []
        if (bank, cid) == (1, 19):
            self.talk_list.append(tuple(args))
        if (bank, cid) in ((1, 10), (1, 41), (1, 76)):
            self.menu_open.add('talk')
            if cid == 41:
                self.menu_open.add(100)
        menus = {31: 23, 48: 13, 23: 12, 74: 1000, 75: 1001, 87: 380, 22: 11, 86: 370, 46: 64, 30: 200}
        if bank == 1 and cid in menus:
            self.menu_open.add(menus[cid])
        if (bank, cid) == (1, 17):
            self.dialog_open = True
        if (bank, cid) == (1, 47) and args[1] == 5:
            self.status[args[0]] = args[2]


def evaluate(code, env, args, call_result):
    st, regs = [], env.regs
    i = 0
    while i < len(code):
        c = code[i]
        if c <= 0x7f:
            st.append(c - 64); i += 1
        elif c == 0x80:
            st.append(struct.unpack_from('<f', code, i + 1)[0]); i += 5
        elif c == 0x81:
            st.append(struct.unpack_from('<d', code, i + 1)[0]); i += 9
        elif c == 0x82:
            st.append(struct.unpack_from('<i', code, i + 1)[0]); i += 5
        elif 0x84 <= c <= 0x8a:
            n = c - 0x84
            a = [st.pop() for _ in range(n)][::-1]
            fid = st.pop()
            st.append(env.func(fid, a)); i += 1
        elif c in (0x8c, 0x8e, 0x8f, 0x90, 0x91, 0x92, 0x93, 0x94, 0x95, 0x96, 0x98, 0x99):
            b, a = st.pop(), st.pop()
            if a is ONGOING or b is ONGOING:
                r = {0x95: a is b, 0x96: a is not b}[c]
            else:
                r = {0x8c: a + b, 0x8e: a - b, 0x8f: a * b, 0x90: a / b if b else 0, 0x91: a <= b,
                     0x92: a >= b, 0x93: a < b, 0x94: a > b, 0x95: a == b, 0x96: a != b,
                     0x98: bool(a) and bool(b), 0x99: bool(a) or bool(b)}[c]
            st.append(int(r) if isinstance(r, bool) else r); i += 1
        elif c == 0xa6:
            i += 1
        elif c == 0xa5:
            j = i + 1
            while code[j:j + 2] != b'\0\0':
                j += 2
            st.append(code[i + 1:j].decode('utf-16-le')); i = j + 2
        elif 0xa7 <= c <= 0xae:
            regs[c - 0xa7] = st[-1]; i += 1
        elif 0xaf <= c <= 0xb6:
            st.append(regs[c - 0xaf]); i += 1
        elif c == 0xb8:
            st.append(args[st.pop()]); i += 1
        elif c == 0xb9:
            st.append(call_result); i += 1
        elif c == 0xba:
            st.append(ONGOING); i += 1
        elif c == 0xa1:
            break
        else:
            raise ValueError(f'byte {c:#x}')
    return st[-1]


class Frame:
    def __init__(self, gid, args):
        self.gid, self.args, self.state, self.call_result, self.child = gid, args, None, ONGOING, None


class Machine:
    def __init__(self, esd, env, gid, args):
        self.esd, self.env = esd, env
        self.root = Frame(gid, args)
        self.returned = None
        self.enter(self.root, 0)

    def ev(self, frame, cmds):
        for b, i, a in cmds:
            vals = [evaluate(x, self.env, frame.args, frame.call_result) for x in a]
            if b == 6:
                child = Frame(i, vals)
                frame.child = child
                frame.call_result = ONGOING
                self.enter(child, 0)
            elif b == 7:
                frame.ret = vals[0] if vals else 0
            else:
                self.env.command(b, i, vals)

    def enter(self, frame, sid):
        frame.state = sid
        frame.call_result = ONGOING
        frame.child = None
        self.ev(frame, self.esd['groups'][frame.gid][sid]['entry'])

    def tick(self):
        """Uma volta: avalia das maquinas mais internas para fora. Retorna False se terminou."""
        chain = []
        f = self.root
        while f:
            chain.append(f)
            f = f.child
        for depth in range(len(chain) - 1, -1, -1):
            f = chain[depth]
            if f is not chain[depth]:
                continue
            st = self.esd['groups'][f.gid][f.state]
            self.ev(f, st['while'])
            res = self.conds(f, st['conds'])
            if res is None:
                continue
            target, passc = res
            self.ev(f, st['exit'])
            f.ret = 0
            self.ev(f, passc)
            if target is None:
                # retorno
                if depth == 0:
                    self.returned = f.ret
                    return False
                parent = chain[depth - 1]
                parent.child = None
                parent.call_result = f.ret
                return True
            self.enter(f, target)
            return True
        return True

    def conds(self, f, conds):
        for c in conds:
            if evaluate(c['eval'], self.env, f.args, f.call_result):
                if c['subs']:
                    r = self.conds(f, c['subs'])
                    if r is not None:
                        return r[0], c['pass'] + r[1]
                    continue
                return c['target'], c['pass']
        return None


def load(path, name):
    for f in bnd4_unpack(dcx_decompress(open(path, 'rb').read())):
        if f['name'].lower().endswith(name):
            return parse_esd(f['data'])
    raise FileNotFoundError(name)
