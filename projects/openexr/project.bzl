load("//kiss:defs.bzl", "LOCAL", "RBE", "build_spec", "project_spec", "tarball_source", "test_spec")
# OpenEXR — the Academy Software Foundation's high-dynamic-range image format and
# library (C++). Source pinned in //kiss:extension.bzl (@openexr_archive,
# v3.4.13-rc3). First-party Bazel: its BUILD loads cc_* from rules_cc, so the
# default 9.1.1 inner. The hermetic LLVM modification lives in
# //projects/openexr/hermetic_llvm. OpenEXR's MODULE declares a
# direct platforms dep (no PLATFORMS_DEP).
#
OPENEXR_PROJECT = project_spec(
    name = "openexr",
    source = tarball_source(
        archive = "@openexr_archive//file",
        strip_prefix = "openexr-3.4.13-rc3",
    ),
    bazel_version = "9.1.1",
    environments = [LOCAL, RBE],
    build = build_spec(targets = ["//:OpenEXR"], flags = ["-c", "opt"]),
    test = test_spec(targets = ["//:IexTest"], flags = ["-c", "opt"]),
)
