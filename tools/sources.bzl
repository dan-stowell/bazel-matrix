"""The `projects` module extension: one source repo per project.

It reads //:projects.json (written by tools/sync.py) and creates, for every
project, a repo `src_<module>` holding `source.tar`: the project's BCR
source archive with the BCR's patches and overlay applied and the registry's
MODULE.bazel in place of its own (as when Bazel fetches it from a registry),
as one deterministic tar. A hub repo `projects` aliases them as
`@projects//:<module>`, so MODULE.bazel needs a single use_repo; it also
has the pinned inner Bazels of tools/versions.bzl as `@projects//:bazel_<v>`
and in `@projects//:modules.bzl` the modules' names (MODULES) and the
packages with a generated BUILD.bazel (GENERATED). Repos are
fetched lazily: only when a target that needs that project's source runs.
"""

load("@bazel_tools//tools/build_defs/repo:http.bzl", "http_file")
load(":versions.bzl", "INNER_BAZELS")

def _bcr_source_impl(rctx):
    rctx.download_and_extract(
        url = rctx.attr.urls,
        integrity = rctx.attr.integrity,
        stripPrefix = rctx.attr.strip_prefix,
        type = rctx.attr.archive_type,
    )
    # The order of http_archive for a registry module: overlay, then the
    # registry's patches, then the registry's MODULE.bazel.
    for path, url_integrity in rctx.attr.overlay.items():
        url, integrity = url_integrity.split(" ")
        # Executable, as http_archive's remote_file_urls: overlaid files
        # may be shell scripts (git's t/bazel-test-wrapper.sh).
        rctx.download(url = url, output = path, integrity = integrity, executable = True)
    for i, (url, integrity) in enumerate(rctx.attr.patches.items()):
        patch = ".bazel_matrix_patch_%d" % i
        rctx.download(url = url, output = patch, integrity = integrity)
        rctx.patch(patch, strip = rctx.attr.patch_strip)
        rctx.delete(patch)
    rctx.delete("MODULE.bazel")
    rctx.download(url = rctx.attr.module_file[0], output = "MODULE.bazel", integrity = rctx.attr.module_file[1])
    if rctx.attr.module_append:
        # projects.txt `override` lines, as single_version_override()s.
        rctx.file("MODULE.bazel", rctx.read("MODULE.bazel") + rctx.attr.module_append)

    # Bazel's patch writes a git symlink (mode 120000) as a regular file
    # holding the target path, with mode 0044 (circl 1.3.8's bazel-bin), which
    # tar can't read. --mode below sets u+rw on every entry anyway, so this
    # leaves every other tar's bytes as they were.
    result = rctx.execute(["chmod", "-R", "u+r", "."])
    if result.return_code:
        fail("chmod of %s failed: %s" % (rctx.name, result.stderr))

    # A deterministic tar of the patched tree, so the outer action key only
    # changes when the source does.
    entries = [e.basename for e in rctx.path(".").readdir()]
    result = rctx.execute([
        "tar",
        "--create",
        "--file=.bazel_matrix_source.tar",
        "--format=gnu",
        "--sort=name",
        "--mtime=@0",
        "--owner=0",
        "--group=0",
        "--numeric-owner",
        "--mode=u+rwX,go+rX,go-w",
        "--",
    ] + sorted(entries))
    if result.return_code:
        fail("tar of %s failed: %s" % (rctx.name, result.stderr))
    for e in entries:
        rctx.delete(e)
    result = rctx.execute(["mv", ".bazel_matrix_source.tar", "source.tar"])
    if result.return_code:
        fail("mv failed: " + result.stderr)
    rctx.file("REPO.bazel", "")
    rctx.file("BUILD.bazel", 'exports_files(["source.tar"])\n')

    # Lets the remote repo contents cache serve this repo: a fully cached
    # run then needs only source.tar's digest, not the download.
    return rctx.repo_metadata(reproducible = True)

bcr_source = repository_rule(
    implementation = _bcr_source_impl,
    attrs = {
        "archive_type": attr.string(),
        "integrity": attr.string(mandatory = True),
        # [url, integrity] of the registry's MODULE.bazel.
        "module_file": attr.string_list(mandatory = True),
        # Appended to MODULE.bazel; see tools/sync.py's module_append.
        "module_append": attr.string(),
        # path -> "url integrity"
        "overlay": attr.string_dict(),
        "patch_strip": attr.int(),
        # url -> integrity, applied in order.
        "patches": attr.string_dict(),
        "strip_prefix": attr.string(),
        "urls": attr.string_list(mandatory = True),
    },
)

def _alias(name, actual):
    return 'alias(\n    name = "%s",\n    actual = "%s",\n    visibility = ["//visibility:public"],\n)\n\n' % (name, actual)

def _hub_impl(rctx):
    rctx.file("REPO.bazel", "")
    rctx.file("BUILD.bazel", "".join(
        [_alias(name, "@src_%s//:source.tar" % name) for name in rctx.attr.names] +
        [_alias("bazel_" + v, "@%s//file" % _bazel_repo(v)) for v in INNER_BAZELS],
    ))
    # For tools/BUILD.bazel's generated_test: the fetched modules, and the
    # packages with a generated BUILD.bazel (which must be the same).
    rctx.file("modules.bzl", "MODULES = %s\nGENERATED = %s\n" % (
        json.encode(rctx.attr.names),
        json.encode(rctx.attr.generated),
    ))

_hub = repository_rule(
    implementation = _hub_impl,
    attrs = {"generated": attr.string_list(), "names": attr.string_list()},
)

def _bazel_repo(version):
    return "inner_bazel_" + version.replace(".", "_")

def _generated(mctx):
    """The top-level packages whose BUILD.bazel tools/sync.py wrote."""
    root = mctx.path(Label("//:projects.json")).dirname
    found = []
    for d in root.readdir():
        build = d.get_child("BUILD.bazel")
        if d.is_dir and build.exists and mctx.read(build).startswith("# Generated by tools/sync.py"):
            found.append(d.basename)
    return sorted(found)

def _projects_impl(mctx):
    data = json.decode(mctx.read(Label("//:projects.json")))
    names = []
    for p in data["projects"]:
        s = p["source"]
        bcr_source(
            name = "src_" + p["name"],
            urls = s["urls"],
            integrity = s["integrity"],
            strip_prefix = s.get("strip_prefix", ""),
            archive_type = s.get("archive_type", ""),
            patches = {x["url"]: x["integrity"] for x in s.get("patches", [])},
            patch_strip = s.get("patch_strip", 0),
            overlay = {x["path"]: x["url"] + " " + x["integrity"] for x in s.get("overlay", [])},
            module_file = [s["module_file"]["url"], s["module_file"]["integrity"]],
            module_append = s.get("module_append", ""),
        )
        names.append(p["name"])
    for v, info in INNER_BAZELS.items():
        http_file(
            name = _bazel_repo(v),
            downloaded_file_path = "bazel",
            executable = True,
            sha256 = info.sha256,
            urls = ["https://github.com/bazelbuild/bazel/releases/download/%s/bazel-%s-linux-x86_64" % (v, v)],
        )
    _hub(name = "projects", names = names, generated = _generated(mctx))
    return mctx.extension_metadata(
        root_module_direct_deps = ["projects"],
        root_module_direct_dev_deps = [],
        reproducible = True,
    )

projects = module_extension(implementation = _projects_impl)
