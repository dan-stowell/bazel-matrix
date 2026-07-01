load("//kiss:defs.bzl", "HERMETIC_LLVM", "LOCAL", "MINIMG", "RBE", "build_spec", "overlay", "project_spec", "tarball_source", "test_spec")
# jsoncpp — the classic C++ JSON parser/serializer.
# Source pinned in //kiss:extension.bzl (@jsoncpp_archive, release
# 1.9.8), built with the fully-hermetic LLVM toolchain. jsoncpp ships
# first-party Bazel files that load rules_cc and its unit test uses its own
# harness (not googletest), so the default 9.1.1 inner builds it as-authored.
#
#   bazel run //projects/jsoncpp:build_local_linux_amd64
#   bazel run //projects/jsoncpp:test_local_linux_amd64

# jsoncpp's MODULE.bazel has no direct `platforms` dep, so @platforms isn't
# visible to its root module — which the injected RBE platform package needs.
# Append a direct bazel_dep (see platforms.MODULE.bazel).
JSONCPP_PLATFORMS = overlay(
    name = "jsoncpp_platforms",
    appends = [("//projects/jsoncpp:platforms.MODULE.bazel", "MODULE.bazel")],
)

JSONCPP_PROJECT = project_spec(
    name = "jsoncpp",
    source = tarball_source(
        archive = "@jsoncpp_archive//file",
        strip_prefix = "jsoncpp-1.9.8",
    ),
    toolchains = [JSONCPP_PLATFORMS, HERMETIC_LLVM],
    environments = [LOCAL, RBE, MINIMG],
    build = build_spec(targets = ["//:jsoncpp"], flags = ["-c", "opt"]),
    # jsoncpp's own unit test (its self-contained test harness over //:jsoncpp).
    test = test_spec(targets = ["//src/test_lib_json:jsoncpp_test"], flags = ["-c", "opt"]),
)
