# Embedded Xray cores

Both binaries are from the official XTLS/Xray-core `v26.5.9` release.

| DEB architecture | Xray release asset | Release archive SHA256 |
| --- | --- | --- |
| `arm64` | `Xray-linux-arm64-v8a.zip` | `7bc1da606e26e4ac2d7831181745bb3bcf4dca0fd7825f41388ae032e1247d15` |
| `mipsel` | `Xray-linux-mips32le.zip` | `587d3b379097fc6f96cb8b9250a51a7b7fe1016098e80f06b9277597cb3fac2a` |

The package builder checks the extracted binary hashes recorded in
`SHA256SUMS`. GitHub Actions also validates the ELF class, machine and byte
order before creating either DEB.

The MIPS package uses the regular `xray` binary from the little-endian
`mips32le` archive. It does not use the separate soft-float binary.
