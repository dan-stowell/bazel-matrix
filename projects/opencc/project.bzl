load("//kiss:defs.bzl", "LOCAL", "RBE", "build_spec", "project_spec", "tarball_source", "test_spec")
# OpenCC — Open Chinese Convert, conversion between Traditional/Simplified
# Chinese (C++). Source pinned in //kiss:extension.bzl (@opencc_archive,
# release ver.1.3.1), built from the upstream source/module as-is. The hermetic
# LLVM modification lives in //projects/opencc/hermetic_llvm.
#
# The library (//:opencc) pulls a handful of BCR modules (marisa-trie,
# darts-clone, rapidjson, tclap); some call cc_* unloaded, so it runs on the
# Bazel 8.7 inner. (OpenCC declares platforms directly, so no PLATFORMS_DEP.)
#
OPENCC_PROJECT = project_spec(
    name = "opencc",
    source = tarball_source(
        archive = "@opencc_archive//file",
        strip_prefix = "OpenCC-ver.1.3.1",
    ),
    bazel_version = "8.7.0",
    environments = [LOCAL, RBE],
    build = build_spec(targets = ["//:opencc"], flags = ["-c", "opt"]),
    test = test_spec(targets = ["//src/...", "//test/..."], flags = ["-c", "opt"]),
)
