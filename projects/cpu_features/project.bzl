load("//kiss:defs.bzl", "LOCAL", "RBE", "build_spec", "project_spec", "tarball_source", "test_spec")
# cpu_features — Google's library for runtime CPU feature detection (C).
# Source pinned in //kiss:extension.bzl (@cpu_features_archive, release
# v0.11.0), built from the upstream source/module as-is. The hermetic LLVM
# modification lives in //projects/cpu_features/hermetic_llvm. First-party Bazel; its
# tests use googletest (cc_* unloaded), so it runs on the Bazel 8.7 inner.
# (cpu_features declares platforms directly, so no PLATFORMS_DEP.)
#
CPU_FEATURES_PROJECT = project_spec(
    name = "cpu_features",
    source = tarball_source(
        archive = "@cpu_features_archive//file",
        strip_prefix = "cpu_features-0.11.0",
    ),
    bazel_version = "8.7.0",
    environments = [LOCAL, RBE],
    build = build_spec(targets = ["//:cpuinfo"], flags = ["-c", "opt"]),
    # The portable unit tests (bit_utils/string_view/stack_line_reader) plus
    # cpuinfo_test, which exercises the x86 detection path on this host.
    test = test_spec(
        targets = [
            "//:bit_utils_test",
            "//:string_view_test",
            "//:stack_line_reader_test",
            "//:cpuinfo_test",
        ],
        flags = ["-c", "opt"],
    ),
)
