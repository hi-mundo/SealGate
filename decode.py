#!/usr/bin/env python3
"""
decode.py - Streaming template-based decoder (MVP)

Reads template.bin written by encode.py (zlib-compressed JSON) and reconstructs
the original byte sequence by expanding symbols and hierarchical rules.

Supports context selection (e.g., VIDEO, TEXT) so a single symbol may have
multiple possible expansions; decoder picks the expansion for the chosen context.

Usage:
  python3 decode.py --template template.bin --out reconstructed.bin --context VIDEO --verbose
"""
import argparse, json, zlib, os
from functools import lru_cache

def decode_template(template_path, out_path, context="DEFAULT", verbose=False):
    with open(template_path, "rb") as f:
        blob = f.read()
    txt = zlib.decompress(blob).decode("utf-8")
    tpl = json.loads(txt)
    dictionary = tpl.get("dictionary", {})
    rules = tpl.get("rules", {})
    seq_str = tpl.get("sequence", "")
    if verbose:
        print(f"[DEC] loaded template for file {tpl.get('meta',{}).get('orig_file')} chunks={tpl.get('meta',{}).get('total_chunks')}")
        print(f"[DEC] dict entries: {len(dictionary)} rules: {len(rules)} sequence_symbols: {len(seq_str.split(',')) if seq_str else 0}")
    @lru_cache(maxsize=65536)
    def expand_symbol(sym):
        if sym in dictionary:
            e = dictionary[sym]
            if context in e:
                return bytes.fromhex(e[context])
            if "DEFAULT" in e:
                return bytes.fromhex(e["DEFAULT"])
            for v in e.values():
                try:
                    return bytes.fromhex(v)
                except:
                    continue
            return b""
        if sym in rules:
            a,b = rules[sym]
            return expand_symbol(a) + expand_symbol(b)
        return b""
    seq = seq_str.split(",") if seq_str else []
    if verbose:
        print(f"[DEC] beginning expansion for {len(seq)} sequence items")
    with open(out_path, "wb") as f_out:
        idx = 0
        for s in seq:
            idx += 1
            b = expand_symbol(s)
            f_out.write(b)
            if verbose and idx % 1000 == 0:
                print(f"[DEC] wrote {idx} symbols -> {f_out.tell()} bytes so far")
    if verbose:
        print(f"[DEC] finished; output written to {out_path}; total bytes {os.path.getsize(out_path)}")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--template", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--context", default="DEFAULT")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()
    decode_template(args.template, args.out, context=args.context, verbose=args.verbose)

if __name__ == "__main__":
    main()
