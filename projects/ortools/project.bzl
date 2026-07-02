load("//bazel_runner:defs.bzl", "HERMETIC_LLVM", "LOCAL", "RBE", "build_spec", "project_spec", "tarball_source", "test_spec")
# OR-Tools — Google's operations-research / optimization suite.
# Source pinned in //bazel_runner:extension.bzl (@ortools_archive, v9.15), built
# with the fully-hermetic LLVM toolchain. We build CP-SAT (or-tools' flagship
# constraint solver), which is self-contained — it doesn't pull the external LP
# solvers (scip/highs/glpk).
#
# Built on the Bazel 8.7 inner: or-tools registers Go toolchains via rules_go
# 0.53, whose cgo.bzl uses the global CcInfo symbol that Bazel 9 removed (this
# bites even the C++ targets, since Bazel analyzes all registered toolchains).
# Bazel 8.7 keeps CcInfo global and still carries hermetic-llvm.
#
#   bazel run //projects/ortools:build_local_linux_amd64
ORTOOLS_PROJECT = project_spec(
    name = "ortools",
    source = tarball_source(
        archive = "@ortools_archive//file",
        strip_prefix = "or-tools-9.15",
    ),
    toolchains = [HERMETIC_LLVM],
    bazel_version = "8.7.0",
    environments = [LOCAL, RBE],
    build = build_spec(targets = ["//ortools/sat:cp_model_solver"], flags = ["-c", "opt"]),
    # CP-SAT's own test suite (the solver we build): the 87 cc_test in
    # //ortools/sat plus the 2 //ortools/sat/python tests — 89 tests of the
    # flagship constraint solver. Scoped to //ortools/sat/... so we don't pull
    # the external LP backends (scip/highs/glpk) the rest of the suite needs.
    #   * --build_tests_only: //ortools/sat also defines java_proto_library
    #     (non-test) targets that need a JDK the hermetic build has no host
    #     `java` for; build_tests_only keeps Bazel from building them (only test
    #     targets + their deps are built).
    #   * the java / go / samples subtrees are deselected. The java + go subtrees
    #     are language-binding tests needing a JDK/Go toolchain. The samples
    #     subtree's java_binary examples depend on //ortools/java:Loader →
    #     @maven//:jna, and Bazel *analyzes* them even under --build_tests_only;
    #     fetching @maven runs coursier, which needs a host `java` the hermetic
    #     build lacks. Dropping samples keeps the analysis (and the test goal)
    #     hermetic. The samples are usage examples, not core solver tests.
    test = test_spec(
        targets = [
            "//ortools/sat/...",
            "-//ortools/sat/java/...",
            "-//ortools/sat/go/...",
            "-//ortools/sat/samples/...",
        ],
        flags = ["-c", "opt", "--build_tests_only"],
        exclude_on = {
            "rbe": [
                # These Python tests pass analysis/build, but the generated
                # test runners use /usr/bin/env python3, which is absent on
                # the RBE executor image. Keep the 87 C++ CP-SAT tests.
                "//ortools/sat/python:cp_model_helper_test",
                "//ortools/sat/python:cp_model_test",
            ],
        },
    ),
)
