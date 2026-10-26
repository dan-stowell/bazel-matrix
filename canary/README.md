# RBE image canary

## TLS probe

`//canary:tls_probe_test` runs on an RBE executor (in the image of
`tools/remote.bazelrc`'s `container-image`), `//canary:tls_probe_runner_test`
on the `bb remote` runner (`tools/bb.sh` passes the same image as
`--container_image`). Both are `manual`, so `//...` skips them. They run
`tls_probe.py` with the image's own `/usr/bin/python3`, `curl`, `openssl` and
`git` (a missing one fails) and write one JUnit testcase per check:

- `env`: no variable (`SSL_CERT_FILE`, `CURL_CA_BUNDLE`, `GIT_SSL_*`, ...),
  git config (`http.ssl*`, `url.*.insteadOf`), `~/.curlrc` or `openssl.cnf`
  directive redirects or disables verification, and python's default verify
  paths resolve to `/etc/ssl/certs`; so the checks below test what clients load.
- `trust_store/bundle`: trusted: the SHA-256 fingerprints of
  `/etc/ssl/certs/ca-certificates.crt` equal `roots/<VERSION_ID>.txt`;
  distrusted: informational, lists the roots removed and added vs that.
  `trust_store/capath`: the hashed CApath has valid names (subject hash,
  canonical `hash.N`, contiguous) and the same certs as the bundle.
- `emudhra/store_absent` (distrusted only): no root in the bundle or CApath
  is in `emudhra.txt` or has an eMudhra/emSign subject or issuer.
- `emudhra/fixture`: `openssl verify -attime` (2026-11-01) of
  `emudhra_chain.pem` against the bundle: verifies when trusted; when
  distrusted must fail at depth 2 for want of emSign Root CA - G1.
- `emudhra/online/www.internet2.edu/{python,curl,git}`: the live emSign chain
  must verify when trusted and be rejected for its certificate when distrusted.
- `host/<host>/{python,curl}` for hosts builds hit, `git_ls_remote`,
  `github_release_asset` (follows the redirect): must verify.
- `control/{expired,untrusted-root}.badssl.com/{python,curl,git}`: must be
  rejected for the certificate (a network error fails these).

`emudhra/*` answers "does the image reject eMudhra"; everything else "does it
still work for customers".

DNS, connect, timeout and transient TLS/HTTP errors (after one retry) are
`NETERR`, a JUnit `<error>` rather than `<failure>`, so a red run says
"network, not CA"; they still fail the test, which otherwise would pass on no
evidence. Online checks run 8 at a time; the probe stops at 200s (220s for
setup and offline checks; the test timeout is 300s) and fails what hasn't
finished. `env` also reads every curlrc curl would (`-q` skips them in the
probe) and `openssl.cnf` with its `.include`s.

```sh
tools/bb.sh test //canary:tls_probe_test //canary:tls_probe_runner_test \
  --nocache_test_results --test_output=all --test_env=CANARY_EXPECT=distrusted
```

For another image, edit the `container-image` line of `tools/remote.bazelrc`
without committing: `bb remote` sends uncommitted and untracked changes.
`--test_env=CANARY_SIMULATE_DISTRUST=1` points every client at a copy of the
store without the `emudhra.txt` roots (`SSL_CERT_FILE`/`DIR`, `GIT_SSL_CAINFO`/
`CAPATH`; curl needs `--cacert` and `--capath`, as it keeps its compiled-in
default for whichever one its variables don't set), a stand-in for a candidate.

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
