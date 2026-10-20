"""Confere os .esd gerados: grupos chamados existem, argumentos suficientes, alvos validos,
nenhum WorkValue, e o round-trip pelo esd.py do port."""
import sys, os, glob
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from souls import parse_esd, bnd4_unpack, dcx_decompress, disasm_expr
import esd

def tokens(e):
    i = 0
    while i < len(e):
        c = e[i]
        n = 5 if c in (0x80, 0x82) else 9 if c == 0x81 else 1
        yield e[i:i + n]
        i += n

def max_arg(group):
    m = -1
    def scan(code):
        nonlocal m
        prev = None
        for t in tokens(code):
            if t == b'\xb8' and prev is not None and len(prev) == 1 and prev[0] < 0x80:
                m = max(m, prev[0] - 64)
            prev = t
    def cmds(cs):
        for b, i, a in cs:
            for x in a: scan(x)
    def cond(c):
        scan(c['eval']); cmds(c['pass'])
        for s in c['subs']: cond(s)
    for st in group.values():
        for k in ('entry', 'exit', 'while'): cmds(st[k])
        for c in st['conds']: cond(c)
    return m

errors = 0
count = 0
for p in sorted(glob.glob(sys.argv[1] + '/*.talkesdbnd.dcx')):
    for f in bnd4_unpack(dcx_decompress(open(p, 'rb').read())):
        data = f['data']
        if esd.serialize(esd.parse(data)) != data:
            print('round-trip', p, f['name']); errors += 1
        e = parse_esd(data)
        count += 1
        for gid, g in e['groups'].items():
            for sid, st in g.items():
                for k in ('entry', 'exit', 'while'):
                    for b, i, a in st[k]:
                        if b == 6:
                            if i not in e['groups']:
                                print('grupo inexistente', p, f['name'], i); errors += 1
                            elif len(a) <= max_arg(e['groups'][i]):
                                print('args', p, f['name'], gid, sid, i, len(a), max_arg(e['groups'][i])); errors += 1
                        if (b, i) in ((1, 100), (5, 100)):
                            print('WorkValue', p); errors += 1
print(count, 'scripts,', errors, 'erros')
