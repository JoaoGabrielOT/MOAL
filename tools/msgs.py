"""
Procura textos nos FMG de um .msgbnd.dcx.
Uso: python msgs.py <arquivo .msgbnd.dcx> <palavra ou ID>
Ex.: python msgs.py Game/msg/porbr/menu_dlc2.msgbnd.dcx "Fogueira"
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from souls import bnd4_unpack, dcx_decompress, parse_fmg  # noqa


def fmgs(path):
    return {f["id"]: (f["name"].replace("\\", "/").split("/")[-1], parse_fmg(f["data"]))
            for f in bnd4_unpack(dcx_decompress(open(path, "rb").read()))}


def main():
    path, query = sys.argv[1], sys.argv[2]
    for fid, (name, table) in fmgs(path).items():
        for k, v in table.items():
            if v and (query == str(k) or query.lower() in v.lower()):
                print(f"{fid:5} {name:35} {k:12} {v[:80]!r}")


if __name__ == "__main__":
    main()
