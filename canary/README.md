# RBE image canary

## TLS probe

`//canary:tls_probe_test` runs on an RBE executor (in the image of
`tools/remote.bazelrc`'s `container-image`), `//canary:tls_probe_runner_test`
on the `bb remote` runner (`tools/bb.sh` passes the same image as
`--container_image`). Both are `manual`, so `//...` skips them. They run
`tls_probe.py` with the image's own `/usr/bin/python3`, `curl`, `openssl` and
`git` (a missing one fails) and write one JUnit testcase per check:

- `trust_store/*`: the SHA-256 fingerprints of
  `/etc/ssl/certs/ca-certificates.crt` and of the hashed CApath certs equal
  `roots/<VERSION_ID>.txt`, or with `CANARY_EXPECT=distrusted` that minus
  `emudhra.txt` exactly.
- `emudhra_fixture/*`: `openssl verify -attime` (2026-11-01) of
  `emudhra_chain.pem` against the bundle and the CApath: verifies when
  trusted; when distrusted must fail with an untrusted-issuer error.
- `host/<host>/{python,curl,openssl}` for hosts builds hit, `git_ls_remote`,
  `github_release_asset` (follows the redirect): must verify.
- `control/*`: expired.badssl.com and untrusted-root.badssl.com must fail
  verification. `emudhra_online/www.internet2.edu` is informational.

DNS, connect and timeout errors (after one retry) are `NETERR`: a JUnit
`<error>`, not a failure, unless every host check got one.

```sh
tools/bb.sh test //canary:tls_probe_test //canary:tls_probe_runner_test \
  --nocache_test_results --test_output=all --test_env=CANARY_EXPECT=distrusted
```

For another image, edit the `container-image` line of `tools/remote.bazelrc`
without committing: `bb remote` sends uncommitted and untracked changes.
`--test_env=CANARY_SIMULATE_DISTRUST=1` checks against a copy of the store
without the `emudhra.txt` roots, a stand-in for a candidate image.

`roots/22.04.txt` is from `gcr.io/flame-public/rbe-ubuntu22-04@sha256:0d84a80b...`
(the pinned baseline), `roots/24.04.txt` from
`gcr.io/flame-public/rbe-ubuntu24-04@sha256:f7db0d4791247f032fdb4451b7c3ba90e567923a341cc6dc43abfc283436791a`
(`latest` on 2026-10-26); the two are identical. Regenerate one with
`--test_env=CANARY_DUMP=1 --test_output=all` and copy the printed list.
`emudhra.txt` is the four roots in those stores whose subject names emSign
or eMudhra (emSign Root CA - G1, C1, ECC G3, ECC C3).
`emudhra_chain.pem` is www.internet2.edu's chain as served on 2026-10-26
(leaf `internet2.edu`, valid 2026-09-17 to 2027-04-04, <- InCommon
Intermediate CA - OVG2C <- emSign Root TLS CA - G1, cross-signed by emSign
Root CA - G1). The fixed `-attime` keeps the offline check valid after the
leaf expires.
