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

## Running the server

`canary/server.py` (Python 3 stdlib only) answers, for each candidate image
and arch, whether it is protected from the eMudhra compromise and whether
builds with popular rulesets still pass on it, and serves the answers as one
table on port 8000:

```sh
mkdir -p ~/canary-data
nohup python3 canary/server.py >>~/canary-data/server.log 2>&1 &  # http://0.0.0.0:8000
# flags: --port, --data-dir (~/canary-data), --work-dir (~/canary-work)
canary/restart.sh --between   # pick up new code once the running step ends
```

`canary/restart.sh` frees the port first and starts the new server at once.
The old process finishes its running step in the background (without
`--between`, it interrupts that step), and the new runner waits for the work
dir's lock.

It needs `BUILDBUDDY_API_KEY` in its environment. For this app only, Bazel
runs on this machine, not through `bb remote`. It runs in its own clone,
`~/canary-work`, which is created on first run and reset to
`origin/<repo_branch>` each cycle, with one output base per arch under
`~/canary-out`. Its actions run on BuildBuddy prod RBE, in the image named
on the clone's `tools/remote.bazelrc` container-image line, which is
rewritten (uncommitted) for each image.

The binary is the bazelisk-downloaded Bazel for `.bazelversion`, not
`bazel`/`bb`: the bb CLI adds the key to Bazel's argv. The key reaches Bazel
through `tools/buildbuddy_credential_helper.py` and a 0600 file
(`~/canary-out/.api-key`), and is never put on a command line, in the runs,
in the logs or on the page.

Each cycle runs, in order:

1. The probe for every candidate column, then every baseline column:
   `bazel test //canary:tls_probe_test --config=remote-minimal
   --nocache_test_results --test_output=all --test_env=CANARY_EXPECT=trusted`
   (`distrusted` for a candidate).
2. The subset for each column that has one, baselines first:
   `bazel test //<p>:test ... --//:inner_flags=--remote_instance_name=canary-<cycle>`.
   The salt makes each cycle's inner actions run cold (`salt_inner: false`
   keeps them warm).

A column is an image and an arch (`archs`, default `["amd64", "arm64"]`).
arm64 adds `--remote_default_exec_properties=Arch=arm64`, outer and inner.
A step that outlives `step_timeout_s` (3 h) gets SIGINT, then SIGKILL, to
its process group, and `bazel shutdown`. Inner work dirs of dead processes
are pruned, and this server's output bases are `clean --expunge`d below
`min_free_gb` (15) free. `runs.jsonl` keeps the newest 200 runs, and logs
are kept 3 days.

### The table

There is one row per candidate release and arch:

- **eMudhra protected**: ✓ when every `emudhra*` probe check passes in
  distrusted mode, ✗ when one fails, pending without a complete probe
  result (summary printed, every counted check seen) for that exact digest
  and arch.
- **One column per ruleset** (`GROUPS` in `server.py`: the ruleset module
  and a few small dependents, chosen from their BCR `bazel_dep`s): N/M,
  where M is the group's projects that passed on the baseline of the same
  release and arch (same subset, same repo revision) and N is how many of
  those pass on the candidate. ✗ when N < M. pending without complete runs
  of both, n/a when the column has none of the group's projects.
- A note under the image when a non-eMudhra probe check fails (hosts builds
  use; the CA store diff is informational).

`details` (collapsed) has the baselines, the subsets, the recent runs, and
the logs. `/api/runs` gives the runs as JSON, and `/logs/<file>` a step's
output (`?tail=N`).

### The subset

The projects' `:test` actions are `no-remote-exec`, so their inner Bazels
run on this machine (Ubuntu 24.04, gcc 13), not in the image. An inner
Bazel that autodetects a C++ toolchain finds this machine's, so the subset
of each release and arch keeps only the `GROUPS` projects that pass on its
baseline in this mode (`SUBSETS` in `server.py`). `:test` runs the inner
`bazel test //...`, which builds everything the inner build would, so
`:build` isn't run separately. The config's `subset` key is `"22.04"` for
amd64 and `"22.04/arm64"` for arm64.

### Data dir (`~/canary-data`)

- `config.json`: seeded on first start, re-read each cycle, edited by hand;
  missing keys and subsets get the defaults.
- `runs.jsonl`: a line when each step starts and one when it ends (the last
  per `id` wins). Each holds the cycle, image (name, ref, role, release,
  arch), repo revision, step, subset, start/end, exit code, status
  (`passed`, `failed` (exit 1 or 3), `error`, `timeout`, `interrupted`),
  invocation links, per-target results, the parsed probe, and the log name.
- `logs/`: each step's output.

### Adding a candidate image

Add it to `images` in `~/canary-data/config.json`, pinned by digest (a
multi-arch index for arm64); it is picked up at the next cycle:

```json
{"name": "ubuntu22-04-candidate", "role": "candidate", "release": "22.04",
 "ref": "docker://gcr.io/flame-public/rbe-ubuntu22-04@sha256:<digest>"}
```

Other keys: `repo_branch` (default `rbe-image-canary`), `salt_inner`,
`step_timeout_s`, `cycle_pause_s` (60), `bazel` (a Bazel binary; empty:
auto), `output_root` (`~/canary-out`) and `min_free_gb`.
