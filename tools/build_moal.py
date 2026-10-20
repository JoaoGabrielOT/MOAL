#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""
MOAL (More Options At Lantern) para Bloodborne 1.09 (CUSA03173), gerado a partir dos arquivos do
proprio jogo. Saida: uma pasta de mod no formato do port para PC (mods/<nome>/dvdroot_ps4/...).

O que faz em cada lanterna acesa (fora do multiplayer):
  - Menu com: Voltar ao Sonho do Cacador, Viajar (lapides), Canalizar Ecos de Sangue, oficina
    (fortalecer, reparar, gemas, runas, nevoa arcana), mensageiros (comprar, comprar com
    Discernimento, vender), bau e Renascer.
  - Viajar: as mesmas 5 lapides do Sonho, com a mesma lista de lanternas acesas
    (StartWarpMenuInit). A escolha liga uma flag do mapa atual; um evento novo no .emevd do mapa
    espera essa flag e chama WarpPlayerToRespawnPoint (o mesmo comando que as lapides usam).
  - Renascer: o mesmo do mod DollRebirth (Nexus, autor "V"), em qualquer lanterna. Precisa do
    patch DollRebirth.xml (eboot 1.09) e dos textos do mod DollRebirth.

Usa esd.py, emevd.py e fromsoft.py do port Jgamrot/bloodborne_pc (GPL-2.0-or-later).

Uso: python3 build_moal.py <pasta do jogo (com dvdroot_ps4)> <pasta de saida do mod>
"""
import os
import struct
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import esd  # noqa: E402
from emevd import Emevd  # noqa: E402
from fromsoft import Bnd4, dcx_compress, dcx_decompress  # noqa: E402

# ---------------------------------------------------------------- ids do jogo

GROUP_ACTIVE = 2147483644      # x3: lanterna acesa, fora do multiplayer
GROUP_WARP = 2147483643        # x4: "Voltar ao Sonho do Cacador?" (vanilla)
GROUP_MENU = 2147483500        # novo: menu do MOAL
GROUP_TRAVEL = 2147483501      # novo: viajar entre lanternas
GROUP_REBIRTH = 2147483502     # novo: renascer (DollRebirth)

# comandos (banco 1)
C_SHOW_SHOP_MESSAGE = 10
C_SET_EVENT_FLAG = 11
C_OPEN_GENERIC_DIALOG = 17
C_ADD_TALK_LIST_DATA = 19
C_CLEAR_TALK_LIST_DATA = 20
C_OPEN_REGULAR_SHOP = 22
C_OPEN_REPAIR_SHOP = 23
C_OPEN_REPOSITORY = 30
C_OPEN_SOUL = 31
C_START_WARP_MENU_INIT = 41
C_OPEN_SELL_SHOP = 46
C_OPEN_FORTIFY = 48             # OpenEquipmentChangeOfPurposeShop = "Fortalecer arma"
C_SET_TALK_TIME = 68
C_OPEN_BLOOD_GEM = 74
C_OPEN_CARYLL_RUNE = 75
C_OPEN_INSIGHT_SHOP = 86
C_OPEN_ARCANE_HAZE = 87

# funcoes
F_GET_EVENT_FLAG = 15
F_IS_GENERIC_DIALOG_OPEN = 21
F_TALK_LIST_RESULT = 23
F_IS_TALK_EXCLUSIVE_MENU_OPEN = 53
F_CHECK_MENU_OPEN = 59

# textos (EventText do jogo)
T_RETURN_TO_DREAM = 70011001
T_TRAVEL = 70010110           # "Awakening Headstone"
T_LEVEL_UP = 15000100
T_FORTIFY = 15000110
T_REPAIR = 15000120
T_BLOOD_GEM = 15000111
T_RUNES = 70000008            # "Memory Altar"
T_ARCANE_HAZE = 10011050
T_PURCHASE = 15000140
T_INSIGHT_SHOP = 15000150     # "Buy with Insight"
T_SELL = 15000141
T_STORAGE = 70000000
T_LEAVE = 15000005
# Textos do mod DollRebirth (msg/<idioma>/menu.msgbnd.dcx dele)
T_REBIRTH = 15009100            # "Rebirth"
T_REBIRTH_CONFIRM = 10019100    # "Return to your origin? ..."
T_REBIRTH_NO_LEVELS = 10019101  # "There are no levels to undo."
T_REBIRTH_NO_PATCH = 10019102   # "Rebirth needs the Doll Rebirth (respec) patch..."
T_REBIRTH_DONE = 10019103       # "You have returned to your origin. ..."

# Renascer (DollRebirth): GetStatus/ChangePlayerStat com os slots do patch DollRebirth.xml
C_CHANGE_PLAYER_STAT = 47
F_GET_STATUS = 29
F_GENERIC_DIALOG_BUTTON = 22
STAT_LEVEL, STAT_ORIGIN = 14, 20
ORIGIN_STATS = (0, 1, 3, 4, 5, 6)   # vitalidade, vigor, forca, habilidade, sangue, arcano
ORIGINS = [  # (nivel, atributos) das 9 origens, na ordem da criacao de personagem
    (10, (11, 10, 12, 10, 9, 8)),    # Milquetoast
    (10, (14, 11, 11, 10, 7, 7)),    # Lone Survivor
    (10, (9, 14, 9, 13, 6, 9)),      # Troubled Childhood
    (10, (12, 11, 15, 9, 6, 7)),     # Violent Past
    (10, (9, 12, 9, 15, 7, 8)),      # Professional
    (10, (10, 10, 14, 13, 7, 6)),    # Military Veteran
    (10, (7, 8, 9, 13, 14, 9)),      # Noble Scion
    (10, (10, 12, 10, 9, 5, 14)),    # Cruel Fate
    (4, (10, 9, 10, 9, 7, 9)),       # Waste of Skin
]
WASTE_OF_SKIN = 8

# menus (CheckSpecificPersonMenuIsOpen)
M_SOUL, M_SHOP, M_REPAIR, M_FORTIFY, M_SELL, M_STORAGE, M_WARP = 23, 11, 12, 13, 64, 200, 100
M_INSIGHT, M_HAZE, M_GEM, M_RUNE = 370, 380, 1000, 1001

# Loja dos mensageiros: a mesma escolha de estoque do Sonho (t210691)
SHOP_STAGES = [(6603, 140000, 149999), (9802, 130000, 139999), (9801, 120000, 129999),
               (9800, 110000, 119999)]
SHOP_DEFAULT = (100000, 109999)

# Lapides do Sonho do Cacador: script -> texto do nome
HEADSTONES = [('t210000.esd', 70010100), ('t210001.esd', 70010101), ('t210002.esd', 70010102),
              ('t210003.esd', 70010103), ('t210721.esd', 70010104)]

# Flag de viagem no bloco do mapa atual: 7AAA0150 + destino (o bloco 7AAA01xx e usado pelo jogo
# em todos os mapas, ex.: 7AAA0100 = voltar ao Sonho); 0150-0193 nao sao usados.
TRAVEL_FLAG_BASE = 70000150
TRAVEL_EVENT_BASE = 10006100   # evento novo: 1AAA6100 + destino (6100-6199 nao e usado como id nem flag)

WARP_ANIMATION = 101160        # a mesma da lanterna -> Sonho (evento comum 7200)
WARP_WAIT = 4.0


# ---------------------------------------------------------------- bytecode

def lit(v):
    return esd.lit(v)


def call(fn, *args):
    return esd.call(fn, list(args))


def arg(k):
    return bytes([0x40 + k, 0xb8])


def eq(code, v):
    return code + lit(v) + b'\x95'


def done(code):
    return esd.done(code)


TRUE = done(lit(1))
CALL_DONE = done(b'\xb9\xba\x96')


def flag_on(f):
    return eq(call(F_GET_EVENT_FLAG, f), 1)


def talk_result(v):
    return eq(call(F_TALK_LIST_RESULT), v)


def menu_closed(menu_id):
    return done(eq(call(F_CHECK_MENU_OPEN, menu_id, 0), 0))


def double(v):
    return b'\x81' + struct.pack('<d', v) + b'\xa1'


# ---------------------------------------------------------------- construcao de grupos

class GroupBuilder:
    """Grupo novo num esd.Script. Estados por nome; transicoes resolvidas no fim."""

    def __init__(self, script, gid):
        self.s, self.gid = script, gid
        self.names = []
        self.index = {}
        self.pending = {}

    def state(self, name, entry=(), conds=(), whiles=(), exit=()):
        sid = len(self.names)
        idx = self.s.state(sid)
        self.names.append(name)
        self.index[name] = idx
        st = self.s.states[idx]
        st.entry = self.s.run([self.cmd(*c) for c in entry])
        st.whiles = self.s.run([self.cmd(*c) for c in whiles])
        st.exit = self.s.run([self.cmd(*c) for c in exit])
        self.pending[name] = list(conds)
        return name

    def cmd(self, bank, cid, *args):
        """args: int -> literal; bytes -> expressao pronta (sem 0xa1)"""
        return self.s.cmd(bank, cid, [done(a) if isinstance(a, bytes) else done(lit(a)) for a in args])

    def finish(self):
        for name, conds in self.pending.items():
            items = []
            for c in conds:
                target, ev = c[0], c[1]
                passc = c[2] if len(c) > 2 else ()
                t = -1 if target is None else self.index[target]
                p = self.s.run([self.cmd(*x) for x in passc])
                items.append(self.s.cond(t, ev, p))
            self.s.states[self.index[name]].conds = self.s.run(items)
        if self.s.group(self.gid):
            raise ValueError(f'grupo {self.gid} ja existe')
        self.s.groups.append(esd.Group(self.gid, [self.index[n] for n in self.names]))


def ret(v=0):
    return (None, TRUE, [(7, -1, v)])


def C(cid, *args):
    return (1, cid, *args)


WAIT = C(C_SET_TALK_TIME, double(0.33)[:-1])


def open_menu_state(g, name, command, menu_id, back):
    g.state(name, [command], [(back, menu_closed(menu_id))], [WAIT])


# ---------------------------------------------------------------- menu da lanterna

def build_menu(s, warp_args, travel, rebirth):
    """Grupo do menu. warp_args: quantos argumentos o x4 vanilla recebe (3 normal, 2 calice)."""
    g = GroupBuilder(s, GROUP_MENU)
    items = [(1, T_RETURN_TO_DREAM, 'dream')]
    if travel:
        items.append((2, T_TRAVEL, 'travel'))
    items += [(3, T_LEVEL_UP, 'level'), (4, T_FORTIFY, 'fortify'), (5, T_REPAIR, 'repair'),
              (6, T_BLOOD_GEM, 'gem'), (7, T_RUNES, 'rune'), (8, T_ARCANE_HAZE, 'haze'),
              (9, T_PURCHASE, 'shop'), (10, T_INSIGHT_SHOP, 'insight'), (11, T_SELL, 'sell'),
              (12, T_STORAGE, 'storage')]
    if rebirth:
        items.append((13, T_REBIRTH, 'rebirth'))

    entry = [C(C_CLEAR_TALK_LIST_DATA)] + [C(C_ADD_TALK_LIST_DATA, i, t, -1) for i, t, _ in items]
    entry += [C(C_ADD_TALK_LIST_DATA, 99, T_LEAVE, -1), C(C_SHOW_SHOP_MESSAGE, 0, 0, 0)]
    closed = done(eq(call(F_TALK_LIST_RESULT), 0) + eq(call(F_TALK_LIST_RESULT), 99) + b'\x99' +
                  eq(call(F_IS_TALK_EXCLUSIVE_MENU_OPEN), 0) + b'\x99')
    g.state('menu', entry, [('end', closed)] + [(n, done(talk_result(i))) for i, _, n in items], [WAIT])

    # Voltar ao Sonho: o x4 do proprio jogo (pergunta e liga a flag do evento 7200)
    passthrough = [arg(k) for k in range(warp_args)]
    g.state('dream', [(6, GROUP_WARP, *passthrough)], [('end', CALL_DONE)])
    if travel:
        g.state('travel', [(6, GROUP_TRAVEL, arg(0))],
                [('end', done(b'\xb9' + lit(1) + b'\x95')), ('menu', CALL_DONE)])
    open_menu_state(g, 'level', C(C_OPEN_SOUL), M_SOUL, 'menu')
    open_menu_state(g, 'fortify', C(C_OPEN_FORTIFY), M_FORTIFY, 'menu')
    open_menu_state(g, 'repair', C(C_OPEN_REPAIR_SHOP), M_REPAIR, 'menu')
    open_menu_state(g, 'gem', C(C_OPEN_BLOOD_GEM), M_GEM, 'menu')
    open_menu_state(g, 'rune', C(C_OPEN_CARYLL_RUNE), M_RUNE, 'menu')
    open_menu_state(g, 'haze', C(C_OPEN_ARCANE_HAZE), M_HAZE, 'menu')
    g.state('shop', [], [(f'shop{k}', done(flag_on(f))) for k, (f, _, _) in enumerate(SHOP_STAGES)] +
            [('shop_default', TRUE)])
    for k, (_, lo, hi) in enumerate(SHOP_STAGES):
        open_menu_state(g, f'shop{k}', C(C_OPEN_REGULAR_SHOP, lo, hi), M_SHOP, 'menu')
    open_menu_state(g, 'shop_default', C(C_OPEN_REGULAR_SHOP, *SHOP_DEFAULT), M_SHOP, 'menu')
    open_menu_state(g, 'insight', C(C_OPEN_INSIGHT_SHOP, 200000, 200099), M_INSIGHT, 'menu')
    open_menu_state(g, 'sell', C(C_OPEN_SELL_SHOP, -1, -1), M_SELL, 'menu')
    open_menu_state(g, 'storage', C(C_OPEN_REPOSITORY), M_STORAGE, 'menu')
    if rebirth:
        g.state('rebirth', [(6, GROUP_REBIRTH)], [('menu', CALL_DONE)])
    g.state('end', [], [ret()])
    g.finish()


def build_travel(s, headstones):
    """Grupo de viagem. ARG[0] = codigo do mapa da lanterna atual (ex.: 220).
    headstones: [(texto, [(destino, area, indice, texto do nome, flag acesa, texto se desligada)])]"""
    g = GroupBuilder(s, GROUP_TRAVEL)
    # Lapides: so as que tem alguma lanterna acesa (estados em cadeia, AddTalkListData nao tem "if")
    g.state('start', [C(C_CLEAR_TALK_LIST_DATA)], [('h0', TRUE)])
    for k, (text, lamps) in enumerate(headstones):
        lit_any = b''
        for j, l in enumerate(lamps):
            lit_any += flag_on(l[4]) + (b'\x99' if j else b'')
        nxt = f'h{k + 1}' if k + 1 < len(headstones) else 'show'
        g.state(f'h{k}', [], [(f'h{k}add', done(lit_any)), (nxt, TRUE)])
        g.state(f'h{k}add', [C(C_ADD_TALK_LIST_DATA, k + 1, text, -1)], [(nxt, TRUE)])
    closed = done(eq(call(F_TALK_LIST_RESULT), 0) + eq(call(F_IS_TALK_EXCLUSIVE_MENU_OPEN), 0) + b'\x99')
    g.state('show', [C(C_SHOW_SHOP_MESSAGE, 0, 0, 0)],
            [('back', closed)] + [(f'list{k}', done(talk_result(k + 1))) for k in range(len(headstones))],
            [WAIT])
    for k, (text, lamps) in enumerate(headstones):
        entry = [C(C_CLEAR_TALK_LIST_DATA)]
        entry += [C(C_ADD_TALK_LIST_DATA, j + 1, l[3], l[4]) for j, l in enumerate(lamps)]
        entry += [C(C_START_WARP_MENU_INIT)]
        wclosed = done(eq(call(F_TALK_LIST_RESULT), 0) + eq(call(F_CHECK_MENU_OPEN, M_WARP, 0), 0) + b'\x99')
        g.state(f'list{k}', entry, [('start', wclosed)] +
                [(f'go{l[0]}', done(talk_result(j + 1))) for j, l in enumerate(lamps)], [WAIT])
        for l in lamps:
            d, area, i, _, _, off_text = l
            disabled = done(flag_on(70000000 + area * 10 + i))
            g.state(f'go{d}', [], [(f'off{d}', disabled), (f'warp{d}', TRUE)])
            g.state(f'off{d}', [C(C_OPEN_GENERIC_DIALOG, 7, off_text, 1, 0, 1)],
                    [('start', done(eq(call(F_IS_GENERIC_DIALOG_OPEN), 0)))], [WAIT])
            # flag = ARG[0] * 10000 + 70000150 + destino: o evento do mapa atual faz a viagem
            flag = arg(0) + lit(10000) + b'\x8f' + lit(TRAVEL_FLAG_BASE + d) + b'\x8c'
            g.state(f'warp{d}', [C(C_SET_EVENT_FLAG, flag, 1)], [ret(1)])
    g.state('back', [], [ret(0)])
    g.finish()


def build_rebirth(s):
    """Renascer como o mod DollRebirth (Nexus, autor "V"): volta a origem com os comandos do jogo.
    ChangePlayerStat(0-6, Set, ...) muda os atributos; o patch DollRebirth.xml (eboot 1.09) acrescenta
    GetStatus(14) = nivel, GetStatus(20) = origem e ChangePlayerStat(20, Set, nivel) = nivel com os
    Ecos devolvidos. Sem o patch, GetStatus(14) <= 1 e o menu so avisa."""
    g = GroupBuilder(s, GROUP_REBIRTH)
    level = call(F_GET_STATUS, STAT_LEVEL)
    origin = call(F_GET_STATUS, STAT_ORIGIN)
    dialog_closed = done(eq(call(F_IS_GENERIC_DIALOG_OPEN), 0))
    g.state('check', [], [('need_patch', done(level + lit(1) + b'\x91')),
                          ('need_patch', done(origin + lit(len(ORIGINS) - 1) + b'\x94')),
                          ('low_origin', done(eq(origin, WASTE_OF_SKIN))),
                          ('normal_origin', TRUE)])
    g.state('low_origin', [], [('no_levels', done(level + lit(4) + b'\x93')), ('confirm', TRUE)])
    g.state('normal_origin', [], [('no_levels', done(level + lit(10) + b'\x93')), ('confirm', TRUE)])
    g.state('need_patch', [C(C_OPEN_GENERIC_DIALOG, 1, T_REBIRTH_NO_PATCH, 1, 0, 1)],
            [('end', dialog_closed)], [WAIT])
    g.state('no_levels', [C(C_OPEN_GENERIC_DIALOG, 1, T_REBIRTH_NO_LEVELS, 1, 0, 1)],
            [('end', dialog_closed)], [WAIT])
    g.state('confirm', [C(C_OPEN_GENERIC_DIALOG, 2, T_REBIRTH_CONFIRM, 3, 4, 2)],
            [('apply', done(eq(call(F_GENERIC_DIALOG_BUTTON), 1))), ('end', dialog_closed)], [WAIT])
    g.state('apply', [], [(f'origin{k}', done(eq(origin, k))) for k in range(len(ORIGINS))] + [('end', TRUE)])
    for k, (lvl, stats) in enumerate(ORIGINS):
        entry = [C(C_CHANGE_PLAYER_STAT, STAT_ORIGIN, 5, lvl)]
        entry += [C(C_CHANGE_PLAYER_STAT, stat, 5, v) for stat, v in zip(ORIGIN_STATS, stats)]
        g.state(f'origin{k}', entry, [('done', TRUE)])
    g.state('done', [C(C_OPEN_GENERIC_DIALOG, 1, T_REBIRTH_DONE, 1, 0, 1)], [('level', dialog_closed)], [WAIT])
    g.state('level', [C(C_OPEN_SOUL)], [('end', menu_closed(M_SOUL))], [WAIT])
    g.state('end', [], [ret()])
    g.finish()


# ---------------------------------------------------------------- lanternas

def lamp_info(s):
    """(estado que chama o x4, argumentos do x4, area, indice) ou None se nao for lanterna."""
    active = s.group(GROUP_ACTIVE)
    if not active or not s.group(GROUP_WARP) or s.group(GROUP_MENU):
        return None
    for si in active.states:
        st = s.states[si]
        items = s.runs[st.entry].items
        for k, ci in enumerate(items):
            c = s.cmds[ci]
            if c.bank == 6 and c.id == GROUP_WARP:
                args = [s.exprs[x].code for x in s.runs[c.args].items]
                return si, k, args
    return None


def root_args(s):
    """Argumentos do CALL x1(...) do grupo 0: (..., area, indice[, texto])"""
    g0 = next(g for g in s.groups if g.id < 0x70000000)
    for si in g0.states:
        for ci in s.runs[s.states[si].entry].items:
            c = s.cmds[ci]
            if c.bank == 6:
                return [s.exprs[x].code for x in s.runs[c.args].items]
    return None


def code_int(code):
    t = code[:-1]
    if len(t) == 1 and t[0] < 0x80:
        return t[0] - 64
    if len(t) == 5 and t[0] == 0x82:
        return struct.unpack('<i', t[1:])[0]
    return None


def patch_lamp(data, headstones, map_area):
    s = esd.parse(data)
    info = lamp_info(s)
    if not info:
        return None, None
    si, k, args = info
    if [x.endswith(b'\xb8\xa1') for x in args] != [True] * len(args):
        raise ValueError('argumentos do x4 inesperados')
    warp_args = len(args)
    ra = root_args(s)
    if not ra or len(ra) != warp_args + 4:
        return None, None
    area, index = code_int(ra[4]), code_int(ra[5])
    if area is None or not 200 <= area < 400:
        return None, None
    chalice = warp_args == 2
    travel = not chalice
    if travel and area != map_area:
        raise ValueError(f'lanterna da area {area} no mapa {map_area}')
    rebirth = True
    # Troca CALL x4(args) por CALL menu(args), no mesmo estado e com as mesmas transicoes
    st = s.states[si]
    items = list(s.runs[st.entry].items)
    items[k] = s.cmd(6, GROUP_MENU, args)
    st.entry = s.run(items)
    build_menu(s, warp_args, travel, rebirth)
    if travel:
        build_travel(s, headstones)
    if rebirth:
        build_rebirth(s)
    out = esd.serialize(s)
    if esd.serialize(esd.parse(out)) != out:
        raise ValueError('o script modificado nao faz round-trip')
    return out, (area, index, chalice, rebirth)


# ---------------------------------------------------------------- lapides do Sonho

def read_headstones(talk_dir):
    bnd = Bnd4(dcx_decompress((talk_dir / 'm21_00_00_00.talkesdbnd.dcx').read_bytes()))
    result = []
    dest = 0
    for name, text in HEADSTONES:
        s = esd.parse(bnd.files[bnd.index(name)])
        lamps = []
        # x6: AddTalkListData(j, 70000000 + A*10 + i, lit flag) e x2(A, i, texto se desligada)
        adds = {}
        for st in s.states:
            for ci in s.runs[st.entry].items:
                c = s.cmds[ci]
                a = [s.exprs[x].code for x in s.runs[c.args].items]
                if c.bank == 1 and c.id == C_ADD_TALK_LIST_DATA and len(a) == 3:
                    j = code_int(a[0])
                    adds[j] = (a[1], a[2])
        calls = {}
        for g in s.groups:
            for si in g.states:
                st = s.states[si]
                for ci in s.runs[st.entry].items:
                    c = s.cmds[ci]
                    a = [s.exprs[x].code for x in s.runs[c.args].items]
                    if c.bank == 6 and len(a) == 3 and all(code_int(x) is not None for x in a):
                        calls[(code_int(a[0]), code_int(a[1]))] = code_int(a[2])
        for j in sorted(adds):
            area, i = eval_area_index(adds[j][0])
            lamps.append((dest, area, i, 70000000 + area * 10 + i,
                          10000000 + area * 10000 + 7810 + 20 * i, calls[(area, i)]))
            dest += 1
        result.append((text, lamps))
    return result


def eval_area_index(code):
    """((70000000 + (A * 10)) + i) -> (A, i)"""
    stack = []
    for tok in tokens(code[:-1]):
        if tok in (b'\x8c', b'\x8f'):
            b, a = stack.pop(), stack.pop()
            stack.append(a + b if tok == b'\x8c' else a * b)
        else:
            stack.append(code_int(tok + b'\xa1'))
    v = stack[0]
    return (v - 70000000) // 10, (v - 70000000) % 10


def tokens(code):
    i = 0
    while i < len(code):
        n = 5 if code[i] == 0x82 else 1
        yield code[i:i + n]
        i += n


def respawn_points(event_dir):
    """Destinos (A, i) -> respawn point, lidos do evento 12107000 do Sonho (lapides)."""
    from emevd import Emevd
    e = Emevd(dcx_decompress((event_dir / 'm21_00_00_00.emevd.dcx').read_bytes()))
    result = {}
    for bank, code, a in e.event_instructions(0):
        if (bank, code) == (2000, 0) and len(a) >= 20:
            slot, eid, flag, entity, respawn = struct.unpack_from('<iIiii', a)
            if eid == 12107000:
                area, i = (flag - 72100000) // 10, (flag - 72100000) % 10
                result[(area, i)] = respawn
    return result


# ---------------------------------------------------------------- eventos de viagem

def map_area(name):
    """m24_01_00_00 -> 241"""
    return int(name[1:3]) * 10 + int(name[4:6])


def travel_events(data, area, destinations, respawn):
    e = Emevd(data)
    for d, dest_area, i in destinations:
        flag = TRAVEL_FLAG_BASE + area * 10000 + d     # 7AAA0150 + destino
        event_id = TRAVEL_EVENT_BASE + area * 10000 + d
        r = respawn[(dest_area, i)]
        ins = [
            (1003, 6, struct.pack('<BBxx', 0, 1)),               # termina se for cliente (como o 7200)
            (2003, 2, struct.pack('<iBxxx', flag, 0)),            # limpa a flag ao carregar o mapa
            (3, 0, struct.pack('<bBBxi', 0, 1, 0, flag)),         # espera a flag (grupo MAIN)
            (2003, 2, struct.pack('<iBxxx', flag, 0)),
            (2003, 18, struct.pack('<iiBBBx', 10000, WARP_ANIMATION, 0, 0, 0)),
            (1001, 0, struct.pack('<f', WARP_WAIT)),
            (2003, 49, struct.pack('<i', r)),                     # WarpPlayerToRespawnPoint
            (1000, 4, struct.pack('<Bxxx', 1)),                   # reinicia (permite viajar de novo)
        ]
        e.append_initialized_event(event_id, ins)
    return e.to_bytes()


# ---------------------------------------------------------------- main

def main():
    game = Path(sys.argv[1])
    out = Path(sys.argv[2])
    dvd = game / 'dvdroot_ps4' if (game / 'dvdroot_ps4').is_dir() else game
    talk, event = dvd / 'script' / 'talk', dvd / 'event'

    headstones = read_headstones(talk)
    respawn = respawn_points(event)
    destinations = [(l[0], l[1], l[2]) for _, lamps in headstones for l in lamps]
    assert len(destinations) == len(respawn) == 44, (len(destinations), len(respawn))

    report = []
    lamp_maps = set()
    for packed_path in sorted(talk.glob('m*.talkesdbnd.dcx')):
        name = packed_path.name.split('.')[0]
        if name.startswith('m21_00'):
            continue
        packed = packed_path.read_bytes()
        bnd = Bnd4(dcx_decompress(packed))
        changed = False
        for k, fname in enumerate(bnd.names):
            area = map_area(name)
            new, info = patch_lamp(bnd.files[k], headstones, area)
            if new is None:
                continue
            bnd.files[k] = new
            changed = True
            report.append((name, fname.replace('\\', '/').split('/')[-1], info))
            if not info[2]:
                lamp_maps.add(name)
        if changed:
            dest = out / 'dvdroot_ps4' / 'script' / 'talk' / packed_path.name
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(dcx_compress(bnd.to_bytes(), template=packed))

    for name in sorted(lamp_maps):
        src = event / f'{name}.emevd.dcx'
        packed = src.read_bytes()
        data = travel_events(dcx_decompress(packed), map_area(name), destinations, respawn)
        dest = out / 'dvdroot_ps4' / 'event' / src.name
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(dcx_compress(data, template=packed))
        report.append((name, src.name, f'{len(destinations)} eventos de viagem'))

    for r in report:
        print(*r)
    print(f'{sum(1 for r in report if isinstance(r[2], tuple))} lanternas, {len(lamp_maps)} mapas com viagem')


if __name__ == '__main__':
    main()
