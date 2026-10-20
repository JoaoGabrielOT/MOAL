# MOAL - More Options At Lantern

Mod para BLOODBORNE (1.09, CUSA03173), desenvolvido pela FROM SOFTWARE, feito para o port de PC
[Jgamrot/bloodborne_pc](https://github.com/Jgamrot/bloodborne_pc).

Link para o mod: https://www.nexusmods.com/bloodborne/mods/107

Em cada lanterna acesa, um menu com: voltar ao Sonho do Caçador, viajar direto para outra lanterna
acesa (as 5 lápides do Sonho), Canalizar Ecos de Sangue, oficina (fortalecer, reparar, gemas,
runas, névoa arcana), mensageiros (comprar, comprar com Discernimento, vender), baú e renascer
(com o mod DollRebirth do Nexus Mods instalado).

Este repositório tem as ferramentas em Python que geram o mod a partir dos arquivos do próprio
jogo; nenhum arquivo do jogo vem junto. Detalhes, instalação e testes em [LEIA-ME.txt](LEIA-ME.txt).

```
python tools/build_moal.py "D:\Jogos\Bloodborne\game" saida/MOAL
python tools/check_moal.py saida/MOAL/dvdroot_ps4/script/talk
python tools/test_moal.py  saida/MOAL/dvdroot_ps4/script/talk
```

As versões anteriores (scripts ESD do ESDStudio, para shadPS4) continuam no histórico do git.

Licença: GPL-2.0-or-later ([LICENSE-GPL.txt](LICENSE-GPL.txt)), por usar `esd.py`, `emevd.py` e
`fromsoft.py` do port.
