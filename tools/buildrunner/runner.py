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
import hashlib
import json
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

def _synthesize_bcr_workspace(dest, module_spec):
    """Create a minimal root module that bazel_dep()s a BCR module, so its own
    @NAME//... targets become buildable/testable. The module's source, patches,
    and MODULE.bazel are resolved by the registry; overlays then append onto the
    MODULE.bazel we write here (e.g. the hermetic toolchain), exactly as for a
    source-archive project."""
    name, _, version = module_spec.partition("=")
    if not name or not version:
        sys.exit(f"runner: bad --bcr-module {module_spec!r} (want NAME=VERSION)")
    os.makedirs(dest, exist_ok=True)
    # `platforms` is declared so the injected //museum_rbe package (pin_platform
    # envs) can see @platforms; the dep module pulls its own transitive deps.
    module_bazel = (
        'module(name = "museum_bcr_root", version = "0.0.0")\n'
        'bazel_dep(name = "{name}", version = "{version}")\n'
        'bazel_dep(name = "platforms", version = "1.1.0")\n'
    ).format(name=name, version=version)
    with open(os.path.join(dest, "MODULE.bazel"), "w", encoding="utf-8") as f:
        f.write(module_bazel)
    # An empty package at the root so `bazel` is happy resolving the workspace.
    open(os.path.join(dest, "BUILD.bazel"), "w").close()
    return dest


def _clean_env(home, tmp, path_prepend=None):
    env = {k: os.environ[k] for k in _ENV_ALLOWLIST if k in os.environ}
    env["HOME"] = home
    env["TMPDIR"] = tmp
    env.setdefault("LANG", "C.UTF-8")
    env.setdefault("USER", "museum")
    if path_prepend:
        env["PATH"] = os.pathsep.join([path_prepend] + ([env["PATH"]] if env.get("PATH") else []))
    return env


def _stage_tools(rf, specs, toolbin):
    """Stage pinned tool binaries into toolbin/ so the inner build finds them on
    PATH instead of the host's. Each spec is RLOC=NAME; the resolved binary is
    symlinked to toolbin/NAME (executable). Returns toolbin if any were staged.

    This is how a project whose build shells out to a host tool stays hermetic:
    e.g. Bazel's own genrules call `zip`, which the scrubbed environment doesn't
    provide -- the HERMETIC_ZIP overlay pins one built from source and injects it
    here, so no host `zip` is required.
    """
    if not specs:
        return None
    os.makedirs(toolbin, exist_ok=True)
    for spec in specs:
        src_rloc, _, name = spec.rpartition("=")
        if not src_rloc or not name:
            sys.exit(f"runner: bad --tool spec {spec!r} (want RLOC=NAME)")
        src = _resolve(rf, src_rloc)
        dest = os.path.join(toolbin, name)
        if os.path.islink(dest) or os.path.exists(dest):
            os.remove(dest)
        os.symlink(src, dest)
        os.chmod(src, os.stat(src).st_mode | 0o111)
        print(f"  tool: {name} <= {os.path.basename(src)} (on PATH)", file=sys.stderr)
    return toolbin


# PATH inside the container: a stock Debian PATH, plus the per-goal toolbin so
# pinned tools (HERMETIC_ZIP etc.) still take precedence. Deliberately no host
# dirs — the container provides its own (toolchain-free) userland.
_CONTAINER_PATH = "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"


def _containerize(cmd, image, runtime, base, bazel, workspace, env, toolbin):
    """Wrap `cmd` so the inner bazel runs inside `image`.

    The museum build root (`base`: per-goal output roots, fresh source, home,
    tmp, toolbin) and the shared repo cache live under `base`; the inner bazel
    binary lives in runfiles. Both are bind-mounted at *identical* paths, so the
    absolute-path flags (--output_user_root, --repository_cache, cwd) and the
    bazel argv work unchanged inside. We run as the host uid so cache/output
    files stay host-owned (no root-owned droppings to sudo away later), use the
    host network so dependency downloads (BCR, hermetic LLVM) just work, and pass
    only the scrubbed env — with a container PATH, never the host's.
    """
    path = os.pathsep.join([toolbin, _CONTAINER_PATH]) if toolbin else _CONTAINER_PATH
    docker = [
        runtime, "run", "--rm", "--init",
        "--network", "host",
        "--user", "%d:%d" % (os.getuid(), os.getgid()),
        # We always pass an explicit inner-bazel argv as `cmd`, so clear any image
        # ENTRYPOINT (e.g. the CI image's bazelisk) — otherwise it would swallow
        # the inner-bazel path as its own argument. No-op for entrypoint-less
        # images (museum-minimg).
        "--entrypoint", "",
        "-v", "%s:%s" % (base, base),
        "-v", "%s:%s:ro" % (bazel, bazel),
        "-w", workspace,
        "-e", "PATH=" + path,
    ]
    for k, v in env.items():
        if k == "PATH":
            continue  # replaced with the container PATH above
        docker += ["-e", "%s=%s" % (k, v)]
    docker.append(image)
    return docker + cmd


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _resolve_bep_file(fobj, execroots):
    """Resolve a BEP file object to a local path, or None if not on disk.

    Local builds report `file://` URIs. Remote (RBE) builds report
    `bytestream://.../blobs/<digest>/<size>` — the bytes live in the remote CAS —
    but with `--remote_download_toplevel` the requested targets' outputs are
    materialised locally too, under the execroot at the path the file's
    `pathPrefix` (+ name) describes (e.g. bazel-out/<config>/bin/libre2.a). So for
    a non-file URI we reconstruct that local path and use it if it exists.
    """
    uri = fobj.get("uri", "")
    if uri.startswith("file://"):
        p = uri[len("file://"):]
        return p if os.path.isfile(p) else None
    name = fobj.get("name")
    if not name:
        return None
    prefix = fobj.get("pathPrefix") or []
    for er in execroots:
        cand = os.path.join(er, *prefix, name)
        if os.path.isfile(cand):
            return cand
    return None


def _emit_artifacts(bep_path, dest_dir, output_user_root):
    """Copy a finished build's outputs into dest_dir + write an artifacts.json
    manifest (target -> files, each with sha256 + size).

    We read the build's *Build Event Protocol* stream (--build_event_json_file):
    one JSON object per line. Each `targetCompleted` event names its output
    groups, which reference `namedSet` events by id; a named set holds file URIs
    and can nest further sets — so we resolve them transitively. The files are
    ones Bazel *already produced* (freshly built, a cache hit, or downloaded from
    RBE), so emitting is a pure post-build copy: it never changes an action key
    and never forces a rebuild. The bytes are the same ones the build cached, so
    the manifest's sha256s are stable across cached reruns and across local/RBE.
    """
    if not os.path.exists(bep_path):
        print("  artifacts: no build-event file at %s; nothing to emit" % bep_path,
              file=sys.stderr)
        return
    events = []
    with open(bep_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    # Execroots under the output root, for reconstructing RBE-downloaded paths.
    import glob as _glob
    execroots = [p for p in _glob.glob(os.path.join(output_user_root, "*", "execroot", "*"))
                 if os.path.isdir(p)]

    # id -> namedSetOfFiles payload (its files + nested fileSets).
    named = {}
    for ev in events:
        nid = ev.get("id", {}).get("namedSet", {}).get("id")
        if nid is not None:
            named[nid] = ev.get("namedSetOfFiles", {})

    def files_of(set_id, seen):
        if set_id is None or set_id in seen:
            return []
        seen.add(set_id)
        payload = named.get(set_id, {})
        out = list(payload.get("files", []))
        for child in payload.get("fileSets", []):
            out += files_of(child.get("id"), seen)
        return out

    os.makedirs(dest_dir, exist_ok=True)
    manifest = []
    for ev in events:
        tid = ev.get("id", {}).get("targetCompleted")
        comp = ev.get("completed")
        if not tid or not comp or not comp.get("success"):
            continue
        label = tid.get("label", "")
        safe = label.lstrip("@/").replace("/", "_").replace(":", "_") or "_root"
        seen_sets, seen_uri, outs = set(), set(), []
        for og in comp.get("outputGroup", []):
            for fs in og.get("fileSets", []):
                for fobj in files_of(fs.get("id"), seen_sets):
                    uri = fobj.get("uri", "")
                    if uri in seen_uri:
                        continue
                    seen_uri.add(uri)
                    src = _resolve_bep_file(fobj, execroots)
                    if not src:
                        continue
                    tgt_dir = os.path.join(dest_dir, safe)
                    os.makedirs(tgt_dir, exist_ok=True)
                    dst = os.path.join(tgt_dir, os.path.basename(src))
                    shutil.copyfile(src, dst)
                    outs.append({
                        "name": fobj.get("name", os.path.basename(src)),
                        "path": os.path.relpath(dst, dest_dir),
                        "sha256": _sha256(src),
                        "size": os.path.getsize(src),
                    })
        if outs:
            manifest.append({"target": label, "outputs": outs})
    manifest.sort(key=lambda m: m["target"])
    with open(os.path.join(dest_dir, "artifacts.json"), "w", encoding="utf-8") as mf:
        json.dump({"artifacts": manifest}, mf, indent=2, sort_keys=True)
        mf.write("\n")
    n = sum(len(m["outputs"]) for m in manifest)
    print("  artifacts: %d file(s) from %d target(s) -> %s" % (n, len(manifest), dest_dir),
          file=sys.stderr)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--name", required=True, help="short project name (for the build root)")
    p.add_argument("--bazel", required=True, help="runfiles path to the inner bazel binary")
    p.add_argument("--source-archive", default="", help="runfiles path to the source tarball")
    p.add_argument("--strip-prefix", default="", help="top-level dir to enter after extraction")
    p.add_argument("--bcr-module", default="", metavar="NAME=VERSION",
                   help="instead of extracting a source tarball, synthesize a tiny root "
                        "workspace that bazel_dep()s this Bazel Central Registry module at "
                        "the given version, and build/test its @NAME//... targets. The BCR "
                        "resolves the module's source, patches, and MODULE.bazel; overlays "
                        "(e.g. the hermetic toolchain) still append onto the synthesized "
                        "MODULE.bazel as usual.")
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
    p.add_argument("--tool", action="append", default=[], dest="tools",
                   metavar="RLOC=NAME",
                   help="stage the pinned binary RLOC into a private toolbin/ dir as NAME "
                        "and prepend that dir to the inner build's PATH -- so a project whose "
                        "build shells out to a host tool (e.g. Bazel's genrules call `zip`) "
                        "gets a hermetic, pinned one instead of the host's (repeatable)")
    p.add_argument("--container-image", default=None,
                   help="if set, run the inner bazel inside this container image "
                        "(e.g. a minimal image with no host C/C++ toolchain) instead "
                        "of on the host. The museum build root and the inner bazel "
                        "binary are bind-mounted at identical paths.")
    p.add_argument("--container-runtime", default="docker",
                   help="container runtime for --container-image (default: docker)")
    p.add_argument("--emit-artifacts", nargs="?", const="", default=None,
                   metavar="DIR",
                   help="after a successful build, copy each target's outputs into "
                        "DIR (default <build_root>/artifacts) and write an "
                        "artifacts.json manifest (target -> files with sha256). Reads "
                        "the build's outputs via the Build Event Protocol, so it never "
                        "triggers a rebuild. Also honoured via MUSEUM_EMIT_ARTIFACTS.")
    p.add_argument("extra", nargs="*", help="extra args/targets forwarded to the inner build")
    # parse_known_args so that any flag we don't define (e.g. --subcommands,
    # --verbose_failures passed after `bazel run ... --`) is forwarded verbatim
    # to the inner `bazel build` rather than rejected.
    args, unknown = p.parse_known_args(argv)
    args.extra = list(args.extra) + unknown

    rf = _runfiles()
    bazel = _resolve(rf, args.bazel)
    if not args.bcr_module and not args.source_archive:
        sys.exit("runner: need either --source-archive or --bcr-module")
    archive = _resolve(rf, args.source_archive) if args.source_archive else None

    root = _build_root(args.name)
    output_user_root = os.path.join(root, "output_root")
    repo_cache = _shared_repo_cache()  # shared across goals; see _shared_repo_cache
    home = os.path.join(root, "home")
    tmp = os.path.join(root, "tmp")
    work = os.path.join(root, "work")
    toolbin = os.path.join(root, "toolbin")
    for d in (output_user_root, repo_cache, home, tmp):
        os.makedirs(d, exist_ok=True)

    # Artifact emission (opt-in): resolve the destination dir and a BEP sink the
    # inner build writes its event stream to. Lives under `root`, which is inside
    # the bind-mounted build base, so it resolves identically for container envs.
    emit_dir = None
    if args.emit_artifacts is not None:
        emit_dir = args.emit_artifacts or os.path.join(root, "artifacts")
    else:
        ev = os.environ.get("MUSEUM_EMIT_ARTIFACTS")
        if ev:
            emit_dir = os.path.join(root, "artifacts") if ev.lower() in ("1", "true", "yes", "on") else ev
    bep_path = os.path.join(root, "bep.json") if emit_dir else None
    if bep_path and os.path.exists(bep_path):
        os.remove(bep_path)  # stale stream from a prior run would mislead the copy

    # Optional shared action cache (content-addressed) across goals — opt-in via
    # MUSEUM_DISK_CACHE (a path, or "1" => <base>/disk_cache). Off by default so
    # each goal stays isolated. Turning it on lets the expensive hermetic LLVM
    # toolchain compile once and be reused by every other goal/project/env — what
    # makes a full local/minimg sweep tractable. Placed under the build base so it
    # is bind-mounted into container envs. Safe to share: keyed by action inputs.
    disk_cache = os.environ.get("MUSEUM_DISK_CACHE")
    if disk_cache:
        if disk_cache.lower() in ("1", "true", "yes", "on"):
            disk_cache = os.path.join(_museum_base(), "disk_cache")
        os.makedirs(disk_cache, exist_ok=True)
    # Fresh source tree each run for reproducibility; caches persist for speed.
    if os.path.isdir(work):
        shutil.rmtree(work)
    if args.bcr_module:
        workspace = _synthesize_bcr_workspace(work, args.bcr_module)
    else:
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

    # If we're staging pinned tools onto a toolbin/, that dir must be on the
    # *action* PATH, not just the runner's: Bazel doesn't pass the client PATH to
    # action environments — genrules run with a default PATH (/bin:/usr/bin), so
    # without this the inner build looks for `zip` etc. on the host, not in our
    # toolbin. --action_env/--host_action_env put it on PATH for both the target
    # and exec (host-tool) configurations. toolbin is a stable per-goal path, so
    # the action-cache key it adds is stable across runs.
    tool_flags = []
    if args.tools:
        action_path = os.pathsep.join([toolbin, "/usr/bin", "/bin"])
        tool_flags = [
            "--action_env=PATH=" + action_path,
            "--host_action_env=PATH=" + action_path,
        ]

    flags = list(args.build_flags) + header_flags + tool_flags + extra_flags
    if disk_cache:
        flags.append("--disk_cache=" + disk_cache)
    if bep_path:
        # Ride the build's event stream to learn its outputs — no extra analysis.
        flags.append("--build_event_json_file=" + bep_path)
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

    # Stage any pinned tools (e.g. a hermetic `zip`) and put them on PATH.
    tool_path = _stage_tools(rf, args.tools, toolbin)
    env = _clean_env(home, tmp, path_prepend=tool_path)

    # MINIMG-style environments run the inner bazel inside a minimal container
    # image (no host C/C++ toolchain — the hermetic LLVM overlay supplies it).
    if args.container_image:
        cmd = _containerize(cmd, args.container_image, args.container_runtime,
                            _museum_base(), bazel, workspace, env, tool_path)

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

    # On the host path, run with the scrubbed env. When containerizing, `cmd` is
    # the docker CLI — give it the host env (it needs the real PATH/DOCKER_* to
    # run); the scrubbed env was already handed to the container via -e.
    proc = subprocess.run(cmd, cwd=workspace, env=None if args.container_image else env)

    # On success, copy the build's outputs out + record a manifest. Reads files
    # the build already produced (cached or fresh), so it can't perturb caching.
    if emit_dir and proc.returncode == 0:
        _emit_artifacts(bep_path, emit_dir, output_user_root)
    return proc.returncode


if __name__ == "__main__":
    sys.exit(main())
