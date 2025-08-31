#!/usr/bin/env python3
"""
encode.py - Streaming template extractor / compressor (MVP)

This script reads any file as a stream of raw bytes (chunks), builds a
symbolic "score" (template) where repeated byte-chunks become symbols ("notes"),
applies a simple hierarchical substitution (Re-Pair–like) on the symbol sequence,
and writes a compact template (zlib-compressed JSON) that contains:

 - dictionary: symbol -> { context_name: hex(chunk_bytes) }
 - rules: hierarchical rules Rn -> [a, b]
 - sequence: compressed, rule-applied symbol sequence (comma-separated)

Designed as a proof-of-concept to demonstrate "notes" and streaming decoding.
Usage:
  # Build a global dictionary from sample files (optional)
  python3 encode.py --build-dict samples/* --out global_dict.json --chunk-size 4096 --verbose

  # Encode a single file (stream, two passes; never load full file into RAM)
  python3 encode.py --input bigfile.bin --out template.bin --dict global_dict.json --contexts VIDEO,TEXT --chunk-size 4096 --min-pair-freq 3 --verbose
"""
import argparse, hashlib, json, zlib, os, sys, random
from collections import Counter, defaultdict

DEFAULT_CHUNK_SIZE = 4096
DEFAULT_MIN_FREQ = 2

def short_hash(b):
    return hashlib.sha256(b).hexdigest()[:12]

def stream_chunks(path, chunk_size):
    with open(path, "rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            yield chunk

def build_global_dict(paths, out_path, chunk_size=DEFAULT_CHUNK_SIZE, min_freq=DEFAULT_MIN_FREQ, verbose=False):
    counts = Counter()
    sample_map = {}
    total = 0
    for p in paths:
        if verbose: print(f"[DICT] scanning {p}")
        for c in stream_chunks(p, chunk_size):
            h = short_hash(c)
            counts[h] += 1
            if h not in sample_map:
                sample_map[h] = c
            total += 1
    if verbose:
        print(f"[DICT] scanned {len(paths)} files; total chunks seen: {total}; unique chunk-hashes: {len(counts)}")
    entries = {}
    for h, cnt in counts.items():
        if cnt >= min_freq:
            sym = "S" + h
            entries[sym] = {"DEFAULT": sample_map[h].hex(), "freq": cnt}
    with open(out_path, "w") as f:
        json.dump({"meta": {"chunk_size": chunk_size, "min_freq": min_freq}, "entries": entries}, f)
    if verbose:
        print(f"[DICT] wrote {len(entries)} entries to {out_path}")
    return out_path

def build_hierarchical_rules(sequence, max_new_symbols=10000, min_pair_freq=2, verbose=False):
    seq = sequence[:]
    rules = {}
    next_idx = 0
    def new_sym():
        nonlocal next_idx
        s = f"R{next_idx}"
        next_idx += 1
        return s
    while True:
        pairs = Counter()
        for i in range(len(seq) - 1):
            pairs[(seq[i], seq[i+1])] += 1
        if not pairs:
            break
        (a,b), freq = pairs.most_common(1)[0]
        if freq < min_pair_freq or len(rules) >= max_new_symbols:
            if verbose: print(f"[RULES] stopping: top pair freq {freq}, threshold {min_pair_freq}")
            break
        ns = new_sym()
        rules[ns] = [a, b]
        new_seq = []
        i = 0
        while i < len(seq):
            if i < len(seq)-1 and seq[i] == a and seq[i+1] == b:
                new_seq.append(ns)
                i += 1
                i += 1
            else:
                new_seq.append(seq[i])
                i += 1
        seq = new_seq
        if verbose:
            print(f"[RULES] created {ns} -> ({a},{b}) frequency={freq} seq_len={len(seq)} rules={len(rules)}")
    return seq, rules

def encode_file(input_path, out_path, dict_path=None, contexts=["DEFAULT"], chunk_size=DEFAULT_CHUNK_SIZE, verbose=False, min_pair_freq=2):
    global_dict = {}
    if dict_path:
        if verbose: print(f"[ENC] loading dict {dict_path}")
        with open(dict_path, "r") as f:
            j = json.load(f)
            for sym,info in j.get("entries", {}).items():
                global_dict[sym] = {k: v for k, v in info.items() if k != "freq"}
        if verbose: print(f"[ENC] loaded {len(global_dict)} dictionary entries")
    hash_to_sym = {}
    for sym in global_dict.keys():
        if sym.startswith("S"):
            h = sym[1:]
            hash_to_sym[h] = sym
    sequence = []
    local_symbol_map = {}
    total_chunks = 0
    if verbose: print(f"[ENC] streaming input {input_path} chunk_size={chunk_size}")
    for chunk in stream_chunks(input_path, chunk_size):
        h = short_hash(chunk)
        total_chunks += 1
        sym = None
        if h in hash_to_sym:
            sym = hash_to_sym[h]
            if verbose:
                print(f"[ENC] chunk#{total_chunks} hash {h} -> global sym {sym}")
        else:
            if h in local_symbol_map:
                sym = local_symbol_map[h]
            else:
                sym = "L" + h
                local_symbol_map[h] = sym
            if verbose:
                print(f"[ENC] chunk#{total_chunks} hash {h} -> local sym {sym}")
        sequence.append(sym)
    if verbose:
        print(f"[ENC] produced initial symbol sequence length {len(sequence)} (chunks={total_chunks})")
    template_dict = defaultdict(dict)
    for sym, m in global_dict.items():
        template_dict[sym].update(m)
    if local_symbol_map:
        if verbose: print("[ENC] collecting bytes for local symbols (second streaming pass)")
        seen = set()
        for chunk in stream_chunks(input_path, chunk_size):
            h = short_hash(chunk)
            if h in local_symbol_map and h not in seen:
                sym = local_symbol_map[h]
                for ctx in contexts:
                    template_dict[sym][ctx] = chunk.hex()
                seen.add(h)
                if verbose: print(f"[ENC] symbol {sym} <- collected {len(chunk)} bytes")
            if len(seen) == len(set(local_symbol_map.values())):
                break
    seq_after, rules = build_hierarchical_rules(sequence, min_pair_freq=min_pair_freq, verbose=verbose)
    out_dict = {k: v for k, v in template_dict.items()}
    template_obj = {
        "meta": {
            "chunk_size": chunk_size,
            "orig_file": os.path.basename(input_path),
            "total_chunks": total_chunks
        },
        "dictionary": out_dict,
        "rules": rules,
        "sequence": ",".join(seq_after)
    }
    blob = zlib.compress(json.dumps(template_obj).encode("utf-8"))
    with open(out_path, "wb") as f:
        f.write(blob)
    if verbose:
        print(f"[ENC] template written to {out_path} (compressed {len(blob)} bytes)")
    return out_path

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--build-dict", nargs="+", help="If provided, build global dictionary from listed files; output is path to dict JSON")
    ap.add_argument("--dict", help="path to existing dictionary JSON")
    ap.add_argument("--input", help="input file to encode")
    ap.add_argument("--out", help="output template path (binary)")
    ap.add_argument("--chunk-size", type=int, default=DEFAULT_CHUNK_SIZE)
    ap.add_argument("--min-pair-freq", type=int, default=2)
    ap.add_argument("--contexts", default="DEFAULT", help="comma-separated contexts to include (e.g. TEXT,VIDEO)")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()
    if args.build_dict:
        out = args.dict if args.dict else "global_dict.json"
        build_global_dict(args.build_dict, out, chunk_size=args.chunk_size, min_freq=DEFAULT_MIN_FREQ, verbose=args.verbose)
        print(f"Global dict saved to {out}")
        return
    if not args.input or not args.out:
        print("Need --input and --out (or --build-dict). Use --help for details.")
        return
    contexts = [c.strip() for c in args.contexts.split(",") if c.strip()]
    encode_file(args.input, args.out, dict_path=args.dict, contexts=contexts, chunk_size=args.chunk_size, verbose=args.verbose, min_pair_freq=args.min_pair_freq)

if __name__ == "__main__":
    main()
