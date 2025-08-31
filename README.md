# PoC: Template-based Streaming Compression (MVP)

## Overview

This repository contains a proof-of-concept for **template-based streaming compression** where repeated low-level byte patterns are replaced by symbolic "notes" and hierarchical rules (symbols of symbols). The goal is to transmit very large files on the network as tiny templates (a "score") that an interpreter (decoder) can expand as a stream, or even partially interpret without expanding the whole file.

Key ideas:
- Work directly at byte-stream level (no file-format assumptions).
- Build a global or local dictionary of repeated byte-chunks (notes).
- Create a symbol sequence for the input stream (streaming, chunked).
- Apply hierarchical substitutions (Re-Pair–like) to create rules (R0, R1, ...).
- Store the template (dictionary + rules + sequence) compressed.
- Decoder expands symbols on the fly and can pick context-specific expansions.

This PoC is **not production-ready** but demonstrates the core idea and provides a foundation for:
- off-chain dictionary storage (IPFS), on-chain pointers (Merkle roots),
- ANS/Huffman entropy coding of symbol streams,
- Online grammar induction (Sequitur) to avoid two-pass approaches,
- ML-based codebooks (VQ) for semantic tokenization.

## Files

- `encode.py`: streaming encoder that outputs `template.bin` (zlib-compressed JSON).
- `decode.py`: streaming decoder that reconstructs the original file from `template.bin`.
- `README.md`: this document.

## How to use

1. (Optional) Build a global dictionary from sample files:
```bash
python3 encode.py --build-dict samples/* --out global_dict.json --chunk-size 4096 --verbose
```

2. Encode a file:
```bash
python3 encode.py --input large_input.bin --out template.bin --dict global_dict.json --contexts VIDEO,TEXT --chunk-size 4096 --min-pair-freq 3 --verbose
```

3. Decode a template:
```bash
python3 decode.py --template template.bin --out reconstructed.bin --context VIDEO --verbose
```

Notes:
- The encoder performs two streaming passes when local symbols are present:
  1. map chunks to symbols (hash-based)
  2. collect raw bytes for local symbols
- The template stores hex-encoded chunks for dictionary/local symbols. For production you'd avoid embedding raw chunks and use off-chain storage + content-addressed pointers.

## Design notes for further development

- **Streaming interpretation**: the decoder expands symbols as a stream and writes bytes incrementally. This allows reading fragments of the output in real time.
- **Multi-meaning symbols**: dictionary entries can contain multiple context expansions. The decoder chooses by context or receives a small disambiguation map as part of the template/session.
- **Security & integrity**: each dictionary blob can be content-addressed (IPFS CID) and its root recorded on-chain for immutability and verification.
- **Entropy coding & binary formats**: replace JSON/text with varints + ANS coding for real compression wins.
- **Online grammar induction**: implement Sequitur or other online grammar learners to avoid heavy memory usage or two-pass constraints.

## License & Disclaimer

This PoC is provided "as-is" for demonstration and research purposes. It is not a finalized product. Use at your own risk.
