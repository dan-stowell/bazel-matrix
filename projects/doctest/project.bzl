load("//kiss:defs.bzl", "HERMETIC_LLVM", "LOCAL", "MINIMG", "PLATFORMS_DEP", "RBE", "build_spec", "project_spec", "tarball_source", "test_spec")
# doctest — the fast, header-only C++ unit-testing framework.
# Source pinned in //kiss:extension.bzl (@doctest_archive, release
# v2.5.2), built with the fully-hermetic LLVM toolchain. Its BUILD files
# explicitly load the cc_* rules from @rules_cc, so it runs on the default Bazel
# 9.1.1 inner.
#
# doctest's only Bazel test lives in its examples/ tree, which is a *nested*
# standalone module (its own MODULE.bazel + WORKSPACE.bazel that pull doctest
# back in via local_path_override="..", like magic_enum's test/). So we extract
# the full archive root and run inner Bazel from examples/, leaving the parent
# doctest module available as @doctest. examples/ already declares rules_cc and
# bazel_skylib; it lacks platforms, so PLATFORMS_DEP supplies @platforms for the
# injected RBE platform package.
#
#   bazel run //projects/doctest:build_local_linux_amd64
#   bazel run //projects/doctest:test_local_linux_amd64
DOCTEST_PROJECT = project_spec(
    name = "doctest",
    source = tarball_source(
        archive = "@doctest_archive//file",
        strip_prefix = "doctest-2.5.2",
        source_subdir = "examples",
    ),
    toolchains = [HERMETIC_LLVM, PLATFORMS_DEP],
    environments = [LOCAL, RBE, MINIMG],
    # Build the doctest library itself (consumed as @doctest from the examples
    # module), then run the upstream Bazel-wired static-library example as a
    # smoke test for consuming doctest from multiple linked libraries.
    build = build_spec(targets = ["@doctest//:doctest"], flags = ["-c", "opt"]),
    test = test_spec(targets = ["//exe_with_static_libs:exe_with_static_libs"], flags = ["-c", "opt"]),
)
