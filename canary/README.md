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

`canary/server.py` (Python 3 stdlib only) runs the canary on BuildBuddy prod
RBE against each configured image and arch, one step at a time, forever, and
serves the results:

```sh
mkdir -p ~/canary-data
nohup python3 canary/server.py >>~/canary-data/server.log 2>&1 &  # http://0.0.0.0:8000
# flags: --port, --data-dir (~/canary-data), --work-dir (~/canary-work)
```

It needs `BUILDBUDDY_API_KEY` in its environment. It does not use
`bb remote`: Bazel runs on this machine (the one exception to building
only through `bb remote`, for this app), in its own clone `~/canary-work`
(created on first run, reset to `origin/<repo_branch>` each cycle), with
one output base per arch under `~/canary-out`, and its actions run on RBE in
the image of the clone's `tools/remote.bazelrc`, whose container-image line
is rewritten (uncommitted) for each image. The key goes on the command line
as `--remote_header=x-buildbuddy-api-key=...` and is redacted from the
recorded command, the logs and the UI. Each cycle runs, in order:

1. `probe` for every candidate column, then every baseline column:
   `bazel test //canary:tls_probe_test --config=remote-minimal
   --nocache_test_results --test_output=all --test_env=CANARY_EXPECT=trusted`
   (`distrusted` for a candidate).
2. `subset` for each column that has one: `bazel test //<p>:test ...
   --//:inner_flags=--remote_instance_name=canary-<cycle>`. The salt puts
   each cycle's inner Bazels in a fresh remote instance, so their actions run
   cold (`salt_inner: false` leaves them warm).

A column is an image and an arch (`archs`, default `["amd64", "arm64"]`).
arm64 adds `--remote_default_exec_properties=Arch=arm64` (and the same as an
inner flag for a subset). A step that runs longer than `step_timeout_s`
(3 h) is interrupted (SIGINT to its process group, then SIGKILL), as is the
running one when the server gets SIGTERM/SIGINT. When less than
`min_free_gb` (15) is free, every output base is `bazel clean --expunge`d
before the next step.

### The subset

The projects' `:test` actions are `no-remote-exec`, so their inner Bazels
run on this machine (Ubuntu 24.04, gcc 13), not in the image, and an inner
Bazel that autodetects a C++ toolchain finds this machine's, whose paths
need not exist in the executor image. That is not what a customer sees, so
the subset keeps only projects that pass on the baseline of that release
and arch in this mode (mostly ones with hermetic toolchains); see
`SUBSET_*` in `server.py` for the lists and what was dropped. Configure it
as `subset` in the config: `"22.04"` for amd64, `"22.04/arm64"` for arm64.
A column without one shows `n/a`.

### The page

`/` (refreshes every 30 s) shows the running step and a log tail link, then
a grid of rows by columns (grouped by release, baselines first):

- **Rejects eMudhra**: on a candidate, `yes` when every `emudhra*` probe
  check passes in distrusted mode, `no` (with the failing checks) when the
  image still trusts eMudhra. The probe's CA store diff vs the baseline is
  in a collapsible list.
- **Works for customers**: `no` when a non-eMudhra probe check fails or a
  subset project fails while the baseline of the same release and arch
  passes it (a regression); `pending` until there are results.
- the probe and subset steps and each target, with their latest status,
  invocation links, the failing probe checks, and `regression` marks.

Below it are the recent runs. `/api/runs` gives the runs as JSON, and
`/logs/<file>` gives a step's full output (`?tail=N` for its last lines).

### Data dir (`~/canary-data`)

- `config.json`: seeded on first start, re-read each cycle; edit it by hand.
- `runs.jsonl`: a line when each step starts and one when it ends (the last
  line per `id` wins): cycle, image (name, ref, role, release, arch), step,
  start/end, exit code, `status` (`passed`, `failed` (exit 1 or 3),
  `error` (any other exit, or a setup failure), `timeout`, `skipped`, or
  `interrupted` for a step running when the server stopped), invocation
  links, per-target results from the test summary, probe checks, and the
  log file name.
- `logs/`: each step's full output.

### Adding a candidate image

Add it to `images` in `~/canary-data/config.json`, pinned by digest (a
multi-arch index for arm64). It is picked up at the next cycle:

```json
{"name": "ubuntu22-04-candidate", "role": "candidate", "release": "22.04",
 "archs": ["amd64", "arm64"],
 "ref": "docker://gcr.io/flame-public/rbe-ubuntu22-04@sha256:<digest>"}
```

`release` (`22.04` or `24.04`) picks the subset it runs and the baselines it
is compared with. Look a digest up with e.g.
`curl -sI -H "Authorization: Bearer $(curl -s 'https://gcr.io/v2/token?scope=repository:flame-public/rbe-ubuntu22-04:pull' | python3 -c 'import json,sys; print(json.load(sys.stdin)["token"])')" -H 'Accept: application/vnd.oci.image.index.v1+json' https://gcr.io/v2/flame-public/rbe-ubuntu22-04/manifests/<tag> | grep -i digest`.

Other keys: `repo_branch` (default `rbe-image-canary`), `salt_inner`
(default true), `step_timeout_s`, `cycle_pause_s` (wait between cycles,
60), `bazel` (`bazel`), `output_root` (`~/canary-out`) and `min_free_gb`.
