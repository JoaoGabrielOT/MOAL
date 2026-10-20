"""Cenarios do menu das lanternas no simulador (tools/sim_moal.py)."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim_moal import Env, Machine, load

OUT = sys.argv[1]
MENU = 2147483500
fails = 0

def check(cond, msg):
    global fails
    if not cond:
        fails += 1
        print('FALHOU:', msg)

def run_until(m, pred, limit=200):
    for _ in range(limit):
        if pred():
            return True
        if not m.tick():
            return pred()
    return pred()

def cmds(env):
    return [(b, i) for b, i, a in env.log]

def open_menu(path, name, args, flags=None):
    e = load(path, name)
    env = Env(flags)
    m = Machine(e, env, MENU, args)
    return e, env, m

T = OUT + '/m22_00_00_00.talkesdbnd.dcx'
LIT_ALL = {f: 1 for f in range(12007810, 13607900)}  # todas as lanternas acesas (aprox.)

# 1) Menu aparece com os itens e "Sair" fecha
e, env, m = open_menu(T, 't220000.esd', [220, 0, 10010715])
ids = [a[1] for a in env.talk_list]
check(ids[0] == 70011001 and 70010110 in ids and 15000100 in ids and ids[-1] == 15000005, f'itens {ids}')
env.talk_result = 99
run_until(m, lambda: m.returned is not None)
check(m.returned == 0, 'sair retorna')

# 2) Cada opcao abre o menu certo e volta ao menu da lanterna
expect = {3: (1, 31), 4: (1, 48), 5: (1, 23), 6: (1, 74), 7: (1, 75), 8: (1, 87), 9: (1, 22),
          10: (1, 86), 11: (1, 46), 12: (1, 30)}
menu_ids = {31: 23, 48: 13, 23: 12, 74: 1000, 75: 1001, 87: 380, 22: 11, 86: 370, 46: 64, 30: 200}
for choice, cmd in expect.items():
    e, env, m = open_menu(T, 't220000.esd', [220, 0, 10010715])
    env.talk_result = choice
    ok = run_until(m, lambda: cmd in cmds(env))
    check(ok, f'opcao {choice} abre {cmd}')
    env.talk_result = 0
    env.log.clear()
    env.menu_open.discard(menu_ids[cmd[1]])
    ok = run_until(m, lambda: (1, 10) in cmds(env))
    check(ok, f'opcao {choice} volta ao menu')

# 3) Loja dos mensageiros escolhe o estoque pelas flags de progresso
for flag, lo in ((6603, 140000), (9802, 130000), (None, 100000)):
    e, env, m = open_menu(T, 't220000.esd', [220, 0, 10010715], {flag: 1} if flag else {})
    env.talk_result = 9
    run_until(m, lambda: (1, 22) in cmds(env))
    shop = [a for b, i, a in env.log if (b, i) == (1, 22)]
    check(shop and shop[0][0] == lo, f'loja {flag} -> {shop}')

# 4) Voltar ao Sonho: chama o x4 do jogo (pergunta) e, com OK, liga a flag 72200100
e, env, m = open_menu(T, 't220000.esd', [220, 0, 10010715])
env.talk_result = 1
run_until(m, lambda: (1, 17) in cmds(env))
dialog = [a for b, i, a in env.log if (b, i) == (1, 17)]
check(dialog and dialog[0][1] == 10010713, f'pergunta do sonho {dialog}')
env.dialog_open = False
run_until(m, lambda: m.returned is not None)
check(env.flags.get(72200100) == 1, 'flag de voltar ao sonho')

# 5) Viajar: lapide de Yharnam -> 1a lanterna -> flag 72200150 (destino 0) e o menu fecha
flags = dict(LIT_ALL)
e, env, m = open_menu(T, 't220000.esd', [220, 0, 10010715], flags)
env.talk_result = 2
env.log.clear()
run_until(m, lambda: (1, 10) in cmds(env))
check([a[1] for a in env.talk_list] == [70010100, 70010101, 70010102, 70010103, 70010104],
      f'lapides {[a[1] for a in env.talk_list]}')
env.talk_result = 1
run_until(m, lambda: (1, 41) in cmds(env))
check(len(env.talk_list) == 12 and env.talk_list[0][1] == 70002410, f'lista de lanternas {env.talk_list[:2]}')
env.talk_result = 1
run_until(m, lambda: m.returned is not None)
check(env.flags.get(72200150) == 1, 'flag de viagem 72200150')
check(m.returned == 0, 'menu termina depois da viagem')

# 6) Lapide sem lanterna acesa nao aparece; lanterna "nao funcionando" mostra o aviso
flags = {12207810: 1, 12417810: 1, 70002410: 1}
e, env, m = open_menu(T, 't220000.esd', [220, 0, 10010715], flags)
env.talk_result = 2
env.log.clear()
run_until(m, lambda: (1, 10) in cmds(env))
check([a[1] for a in env.talk_list] == [70010100, 70010101], f'so lapides acesas {[a[1] for a in env.talk_list]}')
env.talk_result = 1
run_until(m, lambda: (1, 41) in cmds(env))
env.talk_result = 1
run_until(m, lambda: (1, 17) in cmds(env))
check(env.flags.get(72200150) != 1, 'lanterna desligada nao viaja')

# 7) Renascer (DollRebirth) em qualquer lanterna
def rebirth_env(status):
    e, env, m = open_menu(T, 't220000.esd', [220, 0, 10010715])
    env.status.update(status)
    env.talk_result = 13
    return e, env, m

e, env, m = open_menu(T, 't220000.esd', [220, 0, 10010715])
check(15009100 in [a[1] for a in env.talk_list], 'renascer no menu')
# sem o patch: GetStatus(14) = 0 -> aviso, nada muda
e, env, m = rebirth_env({})
run_until(m, lambda: (1, 17) in cmds(env))
check([a for b, i, a in env.log if (b, i) == (1, 17)][0][1] == 10019102, 'aviso do patch')
check((1, 47) not in cmds(env), 'sem patch nao muda nada')
# nivel da origem: nada a desfazer
e, env, m = rebirth_env({14: 3, 20: 8})
run_until(m, lambda: (1, 17) in cmds(env))
check([a for b, i, a in env.log if (b, i) == (1, 17)][0][1] == 10019101, 'sem niveis')
# Cruel Fate (7), nivel 60: confirma -> origem -> aviso -> menu de nivel -> volta ao menu
e, env, m = rebirth_env({14: 60, 20: 7})
run_until(m, lambda: (1, 17) in cmds(env))
check([a for b, i, a in env.log if (b, i) == (1, 17)][0][1] == 10019100, 'confirmacao')
env.dialog_open = False
run_until(m, lambda: [a for b, i, a in env.log if (b, i) == (1, 17)][-1][1] == 10019103)
check(env.status.get(20) == 10, 'nivel da origem (slot 20)')
env.dialog_open = False
ok = run_until(m, lambda: (1, 31) in cmds(env))
check(ok, 'abre o menu de nivel depois do aviso')
check([env.status.get(k) for k in (0, 1, 3, 4, 5, 6)] == [10, 12, 10, 9, 5, 14], f'atributos {env.status}')
env.menu_open.discard(23)
env.talk_result = 0
env.log.clear()
run_until(m, lambda: (1, 10) in cmds(env))
check((1, 10) in cmds(env), 'volta ao menu')
# Waste of Skin (8), nivel 11 -> nivel 4
e, env, m = rebirth_env({14: 11, 20: 8})
run_until(m, lambda: (1, 17) in cmds(env))
env.dialog_open = False
run_until(m, lambda: (1, 31) in cmds(env))
check(env.status.get(20) == 4 and env.status.get(0) == 10, f'waste of skin {env.status}')

# 8) Calice: sem viajar, voltar ao sonho com 2 argumentos
T3 = OUT + '/m29_00_00_00.talkesdbnd.dcx'
e, env, m = open_menu(T3, 't290119.esd', [290, 9])
ids = [a[1] for a in env.talk_list]
check(70010110 not in ids and ids[0] == 70011001 and 15009100 in ids, f'calice {ids}')

print('OK' if not fails else f'{fails} falhas')
