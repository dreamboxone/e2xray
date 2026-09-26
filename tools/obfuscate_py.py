#!/usr/bin/env python3
from __future__ import print_function

import hashlib
import os
import struct
import sys
import zlib
from pathlib import Path


def _keystream(key, nonce, length):
    output = bytearray()
    counter = 0
    while len(output) < length:
        output.extend(hashlib.sha256(key + nonce + struct.pack(">I", counter)).digest())
        counter += 1
    return bytes(output[:length])


def obfuscate(path):
    path = Path(path)
    source = path.read_bytes()
    compressed = zlib.compress(source, 9)
    key = os.urandom(32)
    nonce = os.urandom(16)
    stream = _keystream(key, nonce, len(compressed))
    encoded = bytes(value ^ stream[index] for index, value in enumerate(compressed))

    payload_hex = encoded.hex()
    chunks = [payload_hex[i : i + 120] for i in range(0, len(payload_hex), 120)]
    payload_literal = "\n".join('    "%s"' % chunk for chunk in chunks)

    # The runtime wrapper intentionally reconstructs the original BYTE STREAM.
    # Python 2.7 must receive bytes (not Unicode) when the source contains a
    # PEP-263 coding declaration such as '# -*- coding: utf-8 -*-'.
    wrapper = '''# -*- coding: ascii -*-\n# Protected e2xray build artifact. Readable source is intentionally not shipped.\nimport binascii as _b\nimport hashlib as _h\nimport struct as _t\nimport sys as _s\nimport zlib as _z\n_K = "%s"\n_N = "%s"\n_H = "%s"\n_P = (\n%s\n)\n\ndef _u(_v):\n    if not isinstance(_v, bytes):\n        _v = _v.encode("ascii")\n    return _b.unhexlify(_v)\n\ndef _n(_v):\n    return _v if isinstance(_v, int) else ord(_v)\n\n_k = _u(_K)\n_v = _u(_N)\n_p = _u(_P)\n_o = _u("")\n_i = 0\nwhile len(_o) < len(_p):\n    _o += _h.sha256(_k + _v + _t.pack(">I", _i)).digest()\n    _i += 1\n_d = ''.join(chr(_n(_p[_i]) ^ _n(_o[_i])) for _i in range(len(_p)))\nif _s.version_info[0] >= 3:\n    _d = _d.encode("latin-1")\n_src = _z.decompress(_d)\nif _h.sha256(_src).hexdigest() != _H:\n    raise ImportError("e2xray protected payload integrity failure")\n_code = compile(_src, __file__, "exec")\neval(_code, globals(), globals())\n''' % (key.hex(), nonce.hex(), hashlib.sha256(source).hexdigest(), payload_literal)
    path.write_text(wrapper, encoding="ascii")


def main():
    if len(sys.argv) < 2:
        print("usage: obfuscate_py.py FILE [FILE ...]", file=sys.stderr)
        return 2
    for value in sys.argv[1:]:
        obfuscate(value)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
