"""Run an inner `bazel build`/`test` for a museum project, isolated, daemonless.

This is the engine behind `bazel run //builds/<project>:<goal>`. It is invoked
by the outer Bazel via the museum_project/goal macros, which pass runfiles paths
to a pinned inner Bazel binary and the project's pinned source tarball, plus the
goal's command, targets, overlays, and flags.

What "isolation" means here (Tier 1 — works with only Bazel on the host):
  * a pinned, hermetic inner Bazel binary (not the host's),
  * the project source extracted fresh from a content-addressed tarball,
  * a dedicated --output_user_root + --repository_cache (never the host's
    ~/.cache/bazel), under a per-project build root,
  * --batch (no Bazel server / daemon),
  * --nohome_rc / --nosystem_rc so host bazelrc files can't leak in,
  * a scrubbed environment (only an explicit allowlist is passed through).

Network is left open so the inner build can fetch its own dependencies from the
Bazel Central Registry; the repository cache makes reruns fast.

Usage (constructed by the macro, but documented for clarity):
  runner.py --name absl --bazel <rloc> --source-archive <rloc>
            --strip-prefix abseil-cpp-20260526.0
            --build-flag=-c --build-flag=opt
            --target //absl/... [-- <extra bazel args/targets>]
"""

import argparse
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile

# Environment variables passed through to the inner build. Everything else is
# dropped so the host / outer-Bazel environment cannot influence the build.
# Proxy + TLS vars are kept so dependency downloads work behind a proxy.
_ENV_ALLOWLIST = (
    "PATH",
    "LANG",
    "LC_ALL",
    "TZ",
    "CC",
    "CXX",
    "BAZEL_CXXOPTS",
    "http_proxy",
    "https_proxy",
    "no_proxy",
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "NO_PROXY",
    "SSL_CERT_FILE",
    "SSL_CERT_DIR",
    "CURL_CA_BUNDLE",
)


def _runfiles():
    from python.runfiles import runfiles

    return runfiles.Create()


def _resolve(rf, rloc):
    path = rf.Rlocation(rloc)
    if not path or not os.path.exists(path):
        sys.exit(f"runner: could not resolve runfile: {rloc!r} -> {path!r}")
    return path


def _museum_base():
    base = os.environ.get("MUSEUM_BUILD_ROOT")
    if not base:
        base = os.path.join(tempfile.gettempdir(), "bazel-museum")
    return base


def _build_root(name):
    """Per-project build root holding a per-goal output root + a fresh workdir."""
    return os.path.join(_museum_base(), name)


def _shared_repo_cache():
    """Repository (download) cache shared across all goals.

    Bazel's repository cache is content-addressed (keyed by sha256), so sharing
    it between goals is safe and is what it's for: a toolchain or source archive
    — most notably the rate-limited macOS SDK and the hermetic LLVM tarballs — is
    fetched once and reused everywhere instead of re-downloaded per goal (which
    otherwise trips upstream rate limits). The per-goal output_user_root,
    fresh-extracted source, scrubbed env, and --batch isolation are unchanged.
    """
    return os.path.join(_museum_base(), "repo_cache")


def _extract(archive, dest, strip_prefix):
    os.makedirs(dest, exist_ok=True)
    with tarfile.open(archive, mode="r:*") as tar:
        # filter="data" guards against path traversal / unsafe members (py3.12+).
        tar.extractall(dest, filter="data")
    if strip_prefix:
        root = os.path.join(dest, strip_prefix)
        if not os.path.isdir(root):
            sys.exit(f"runner: strip-prefix {strip_prefix!r} not found under archive")
        return root
    # Autodetect a single top-level directory.
    entries = [e for e in os.listdir(dest) if not e.startswith(".")]
    if len(entries) == 1 and os.path.isdir(os.path.join(dest, entries[0])):
        return os.path.join(dest, entries[0])
    return dest


def _clean_env(home, tmp):
    env = {k: os.environ[k] for k in _ENV_ALLOWLIST if k in os.environ}
    env["HOME"] = home
    env["TMPDIR"] = tmp
    env.setdefault("LANG", "C.UTF-8")
    env.setdefault("USER", "museum")
    return env


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--name", required=True, help="short project name (for the build root)")
    p.add_argument("--bazel", required=True, help="runfiles path to the inner bazel binary")
    p.add_argument("--source-archive", required=True, help="runfiles path to the source tarball")
    p.add_argument("--strip-prefix", default="", help="top-level dir to enter after extraction")
    p.add_argument("--target", action="append", default=[], dest="targets",
                   help="inner build target (repeatable)")
    p.add_argument("--build-flag", action="append", default=[], dest="build_flags",
                   help="flag passed to the inner `bazel build` (repeatable)")
    p.add_argument("--command", default="build",
                   help="inner bazel command to run (e.g. build, test)")
    p.add_argument("--append", action="append", default=[], dest="appends",
                   metavar="RLOC=DEST",
                   help="append the runfile RLOC onto DEST (relative to the workspace "
                        "root) before building -- e.g. inject a toolchain into MODULE.bazel "
                        "(repeatable)")
    p.add_argument("--write", action="append", default=[], dest="writes",
                   metavar="RLOC=DEST",
                   help="copy the runfile RLOC verbatim to DEST (relative to the "
                        "workspace root), creating parent dirs -- e.g. drop a patch "
                        "file and a BUILD marker into a fresh museum_patches/ package "
                        "(repeatable). Unlike --append, the destination is overwritten "
                        "exactly, with no leading newline.")
    p.add_argument("--patch", action="append", default=[], dest="patches",
                   metavar="RLOC",
                   help="apply a unified-diff patch (patch -p1) to the source before "
                        "building (repeatable)")
    p.add_argument("--remote-header-env", action="append", default=[], dest="remote_header_envs",
                   metavar="ENVVAR:HEADER",
                   help="read ENVVAR from the environment and pass it to the inner build as "
                        "--remote_header=HEADER=<value>, keeping the secret off the command "
                        "the macro bakes in (e.g. BUILDBUDDY_API_KEY:x-buildbuddy-api-key)")
    p.add_argument("extra", nargs="*", help="extra args/targets forwarded to the inner build")
    # parse_known_args so that any flag we don't define (e.g. --subcommands,
    # --verbose_failures passed after `bazel run ... --`) is forwarded verbatim
    # to the inner `bazel build` rather than rejected.
    args, unknown = p.parse_known_args(argv)
    args.extra = list(args.extra) + unknown

    rf = _runfiles()
    bazel = _resolve(rf, args.bazel)
    archive = _resolve(rf, args.source_archive)

    root = _build_root(args.name)
    output_user_root = os.path.join(root, "output_root")
    repo_cache = _shared_repo_cache()  # shared across goals; see _shared_repo_cache
    home = os.path.join(root, "home")
    tmp = os.path.join(root, "tmp")
    work = os.path.join(root, "work")
    for d in (output_user_root, repo_cache, home, tmp):
        os.makedirs(d, exist_ok=True)
    # Fresh source tree each run for reproducibility; caches persist for speed.
    if os.path.isdir(work):
        shutil.rmtree(work)
    workspace = _extract(archive, work, args.strip_prefix)

    # Drop verbatim files into the source tree (e.g. a patch + its BUILD marker
    # into a fresh museum_patches/ package). Unlike --append this overwrites the
    # destination exactly, so a patch file isn't corrupted by a leading newline.
    for spec in args.writes:
        src_rloc, _, dest = spec.rpartition("=")
        if not src_rloc or not dest:
            sys.exit(f"runner: bad --write spec {spec!r} (want RLOC=DEST)")
        src = _resolve(rf, src_rloc)
        target = os.path.join(workspace, dest)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        shutil.copyfile(src, target)
        print(f"  overlay(write): {dest} <= {os.path.basename(src)}", file=sys.stderr)

    # Apply overlays: append snippets onto existing source files (e.g. inject a
    # hermetic toolchain into the project's MODULE.bazel). Deterministic because
    # the source is content-pinned and the snippets are static.
    for spec in args.appends:
        src_rloc, _, dest = spec.rpartition("=")
        if not src_rloc or not dest:
            sys.exit(f"runner: bad --append spec {spec!r} (want RLOC=DEST)")
        src = _resolve(rf, src_rloc)
        target = os.path.join(workspace, dest)
        # Append-onto-existing is the common case (e.g. MODULE.bazel), but an
        # overlay may also drop a wholly new file into a fresh package (e.g. an
        # injected RBE platform), so create any missing parent directories.
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(src, "r", encoding="utf-8") as s:
            snippet = s.read()
        with open(target, "a", encoding="utf-8") as t:
            t.write("\n" + snippet)
        print(f"  overlay(append): {dest} += {os.path.basename(src)}", file=sys.stderr)

    # Apply unified-diff patches over the source (for changes appends can't make).
    for patch_rloc in args.patches:
        patch_file = _resolve(rf, patch_rloc)
        if not shutil.which("patch"):
            sys.exit("runner: `patch` not found on PATH but a patch overlay was requested")
        print(f"  overlay(patch): {os.path.basename(patch_file)}", file=sys.stderr)
        with open(patch_file, "rb") as pf:
            r = subprocess.run(
                ["patch", "-p1", "--no-backup-if-mismatch"], cwd=workspace, stdin=pf
            )
        if r.returncode != 0:
            sys.exit(f"runner: failed to apply patch {patch_rloc}")

    # Resolve any --remote-header-env into --remote_header flags (e.g. the
    # BuildBuddy API key), so secrets stay out of the baked-in command line.
    header_flags = []
    for spec in args.remote_header_envs:
        name, _, header = spec.partition(":")
        value = os.environ.get(name)
        if not value:
            sys.exit(f"runner: env var {name!r} is not set (needed for --remote-header-env)")
        header_flags.append("--remote_header={}={}".format(header, value))

    # Extra args come from `bazel run //... -- <here>`. If any of them is a
    # concrete target (doesn't start with "-"), they *replace* the configured
    # default targets; if they're all flags, they're added on top of the
    # defaults. This makes both of these do the intuitive thing:
    #   bazel run //builds/abseil_cpp:build -- //absl/strings:strings   # subset
    #   bazel run //builds/abseil_cpp:build -- --verbose_failures       # default + flag
    # Split flags from target patterns. A token is a flag iff it starts with "-"
    # *and* isn't a negative target pattern (-//..., -@..., -:...). Targets are
    # placed after a "--" so negative patterns are accepted by Bazel.
    def _is_flag(tok):
        if tok.startswith(("-//", "-@", "-:")):
            return False
        return tok.startswith("-")

    extra = [a for a in args.extra if a != "--"]
    extra_flags = [a for a in extra if _is_flag(a)]
    extra_targets = [a for a in extra if not _is_flag(a)]

    flags = list(args.build_flags) + header_flags + extra_flags
    # Targets passed via `-- <targets>` override the configured defaults.
    targets = extra_targets if extra_targets else list(args.targets)
    if not targets:
        sys.exit("runner: no targets specified")

    cmd = [
        bazel,
        "--batch",                       # daemonless: no server process
        "--nohome_rc",
        "--nosystem_rc",
        "--output_user_root=" + output_user_root,
        args.command,
        "--repository_cache=" + repo_cache,
        "--curses=no",
        "--color=no",
    ] + flags + ["--"] + targets

    env = _clean_env(home, tmp)

    # Redact secret-bearing header flags when echoing the command.
    shown = [a if not a.startswith("--remote_header=") else
             a.split("=")[0] + "=" + a.split("=")[1] + "=<redacted>" for a in cmd[1:]]
    print("=" * 72, file=sys.stderr)
    print(f"museum: running `{args.command}` for '{args.name}' in isolation", file=sys.stderr)
    print(f"  workspace:        {workspace}", file=sys.stderr)
    print(f"  inner bazel:      {bazel}", file=sys.stderr)
    print(f"  output_user_root: {output_user_root}", file=sys.stderr)
    print(f"  repository_cache: {repo_cache}", file=sys.stderr)
    print(f"  command:          bazel {' '.join(shown)}", file=sys.stderr)
    print("=" * 72, file=sys.stderr)

    proc = subprocess.run(cmd, cwd=workspace, env=env)
    return proc.returncode


if __name__ == "__main__":
    sys.exit(main())
