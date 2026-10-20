"""
Gera dumps de texto de todos os talkesdbnd.dcx de uma pasta (ex.: Game/script/talk).
Uso: python dump_esd.py <pasta com .talkesdbnd.dcx> <pasta de saida> [<menu_dlc2.msgbnd.dcx para mostrar textos>]
Variavel opcional: ESDLANG_TALK_JSON (nomes das funcoes, do ESDLang).
"""
import glob
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from souls import bnd4_unpack, dcx_decompress, dump_esd, parse_esd, parse_fmg  # noqa


def main():
    src, out = sys.argv[1], sys.argv[2]
    texts = {}
    if len(sys.argv) > 3:
        for f in bnd4_unpack(dcx_decompress(open(sys.argv[3], "rb").read())):
            for k, v in parse_fmg(f["data"]).items():
                if v and f["id"] in (30, 200, 204, 1):
                    texts.setdefault(k, v)
    os.makedirs(out, exist_ok=True)

    def annotate(txt):
        return re.sub(r"(?<![\d.])\d{8}(?![\d.])",
                      lambda m: f"{m.group(0)}«{texts[int(m.group(0))][:40]}»" if int(m.group(0)) in texts else m.group(0),
                      txt)

    for p in sorted(glob.glob(os.path.join(src, "*.talkesdbnd.dcx"))):
        bnd = os.path.basename(p).split(".")[0]
        for f in bnd4_unpack(dcx_decompress(open(p, "rb").read())):
            name = f["name"].replace("\\", "/").split("/")[-1]
            text = annotate(dump_esd(parse_esd(f["data"])))
            open(os.path.join(out, f"{bnd}__{name}.txt"), "w", encoding="utf-8").write(text)
    print("ok")


if __name__ == "__main__":
    main()
