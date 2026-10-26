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

### The broad run

Each cycle runs every project in `projects.txt` that isn't known-failing
(on arm64, not one pinned to `bazel 8.4.2`, which has no arm64 binary) as
`//<p>:test` with `--config=inner-remote[-arm64]`: each project's inner Bazel
runs as an RBE action in the image under test. In order:

1. The probe for each candidate image (`bazel test //canary:tls_probe_test
   --config=remote-minimal --nocache_test_results --test_output=all
   --test_env=CANARY_EXPECT=distrusted`).
2. Tier 1 on every candidate column, then tier 2, then tier 3, in batches of
   `batch_size` (200) projects per invocation (`--jobs`, `jobs`: 100), batch
   k of every image before batch k+1. An image's amd64 and arm64 batches run
   at once (`parallel_archs`), each in its own output base.
3. The same for the baselines (probes with `CANARY_EXPECT=trusted`).

`--//:inner_flags=--remote_instance_name=canary-<cycle>` makes each cycle's
inner actions run cold (`salt_inner: false` keeps them warm). A restart
resumes the unfinished cycle: a project with a result from a finished batch
of this cycle at this revision isn't run again. The revision is the newest
commit touching more than the server's own files (`SERVER_FILES`), so
pushing server changes keeps the results.

Tiers (`tiers()`, from `canary/deps.json`: each project's `bazel_dep`s in
its BCR MODULE.bazel, written by `python3 canary/server.py --write-deps
~/.cache/bazel-matrix/bcr` after `tools/sync.py`): tier 1 is C/C++ projects
on the image's autodetected cc toolchain (not a ruleset, no hermetic C++
toolchain dep, a dep on rules_cc/rules_foreign_cc or on another tier-1
project); tier 2 the popular rulesets (`POPULAR`) and their direct
dependents; tier 3 the rest. The page's details spell it out.

The reference for a candidate column is its baseline's result at the same
revision; until that exists, for 22.04 amd64 the matrix's own record (not
known-failing in projects.txt, from `bb remote` mode on that same image),
elsewhere "baseline pending". A candidate failure of a project that passes
on the reference is a regression.

A step that outlives `step_timeout_s` gets SIGINT, then SIGKILL, to its
process group, and `bazel shutdown`. Inner work dirs of dead processes are
pruned, and this server's output bases are `clean --expunge`d below
`min_free_gb` (20) free. `runs.jsonl` keeps the newest 600 runs, and logs
are kept 3 days.

### The page

Plain HTML, refreshed every minute, results live as each project finishes:

- **Summary**: one row per candidate release and arch: eMudhra protected
  (✓ when every `emudhra*` probe check passes in distrusted mode, ✗ when one
  fails, pending without a complete probe result for that digest and arch),
  then per tier N/M ok with the regressions (red), other failures, flaky,
  infra, running and pending counts, an ETA while it runs, and the
  reference ("vs baseline", "vs matrix record", "baseline pending").
- **Popular rulesets**: the same counts for each `GROUPS` ruleset and a few
  small dependents.
- **Projects**: one row per project, regressions first, then failures, then
  infra, then the rest by tier; per candidate column the result (linked to
  its invocation) and the reference's.

Infra: a wrapper killed by infrastructure (`infra_killed`/`wrapper_error`
in its test.xml) is retried once in a follow-up invocation; still killed is
"infra", neither pass nor failure. Passing only on a retry is "flaky" (a pass).

`details` (collapsed) has the tier heuristic and sizes, the running steps,
the baselines, the recent runs and the logs. `/api/runs` gives the runs as
JSON, and `/logs/<file>` a step's output (`?tail=N`).

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
