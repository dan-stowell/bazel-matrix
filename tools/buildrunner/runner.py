"""Run an inner `bazel build` for a museum project, in isolation, daemonless.

This is the engine behind `bazel run //builds/<project>:build`. It is invoked
by the outer Bazel via the `museum_build` macro, which passes runfiles paths to
a pinned inner Bazel binary and the project's pinned source tarball.

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


def _build_root(name):
    """Per-project build root holding persistent caches + a fresh workdir."""
    base = os.environ.get("MUSEUM_BUILD_ROOT")
    if not base:
        base = os.path.join(tempfile.gettempdir(), "bazel-museum")
    return os.path.join(base, name)


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
    p.add_argument("extra", nargs="*", help="extra args/targets forwarded to the inner build")
    args = p.parse_args(argv)

    rf = _runfiles()
    bazel = _resolve(rf, args.bazel)
    archive = _resolve(rf, args.source_archive)

    root = _build_root(args.name)
    output_user_root = os.path.join(root, "output_root")
    repo_cache = os.path.join(root, "repo_cache")
    home = os.path.join(root, "home")
    tmp = os.path.join(root, "tmp")
    work = os.path.join(root, "work")
    for d in (output_user_root, repo_cache, home, tmp):
        os.makedirs(d, exist_ok=True)
    # Fresh source tree each run for reproducibility; caches persist for speed.
    if os.path.isdir(work):
        shutil.rmtree(work)
    workspace = _extract(archive, work, args.strip_prefix)

    # Extra args come from `bazel run //... -- <here>`. If any of them is a
    # concrete target (doesn't start with "-"), they *replace* the configured
    # default targets; if they're all flags, they're added on top of the
    # defaults. This makes both of these do the intuitive thing:
    #   bazel run //builds/abseil_cpp:build -- //absl/strings:strings   # subset
    #   bazel run //builds/abseil_cpp:build -- --verbose_failures       # default + flag
    extra = [a for a in args.extra if a != "--"]
    has_explicit_target = any(not a.startswith("-") for a in extra)
    if has_explicit_target:
        build_args = list(args.build_flags) + extra
    else:
        build_args = list(args.build_flags) + list(args.targets) + extra
    if not any(not a.startswith("-") for a in build_args):
        sys.exit("runner: no targets specified")

    cmd = [
        bazel,
        "--batch",                       # daemonless: no server process
        "--nohome_rc",
        "--nosystem_rc",
        "--output_user_root=" + output_user_root,
        "build",
        "--repository_cache=" + repo_cache,
        "--curses=no",
        "--color=no",
    ] + build_args

    env = _clean_env(home, tmp)

    print("=" * 72, file=sys.stderr)
    print(f"museum: building '{args.name}' in isolation", file=sys.stderr)
    print(f"  workspace:        {workspace}", file=sys.stderr)
    print(f"  inner bazel:      {bazel}", file=sys.stderr)
    print(f"  output_user_root: {output_user_root}", file=sys.stderr)
    print(f"  repository_cache: {repo_cache}", file=sys.stderr)
    print(f"  command:          bazel {' '.join(cmd[1:])}", file=sys.stderr)
    print("=" * 72, file=sys.stderr)

    proc = subprocess.run(cmd, cwd=workspace, env=env)
    return proc.returncode


if __name__ == "__main__":
    sys.exit(main())
