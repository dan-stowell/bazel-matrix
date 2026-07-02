load("//bazel_runner:defs.bzl", "HERMETIC_LLVM", "HERMETIC_ZIP", "LOCAL", "RBE", "build_spec", "project_spec", "tarball_source", "test_spec")
# file_test exercises real POSIX filesystem semantics that invert when the test
# runs as root: it asserts a permission-stripped file is *unreadable* and that a
# protected path *can't* be removed — both false for root, which the RBE executor
# runs as. (It also writes a multi-GB sparse file the executor's tmp can't hold.)
# So it's excluded off-host; the local goal, not root, still runs it. The rest of
# //src/test/cpp/... is environment-neutral.
_ROOT_SENSITIVE_TESTS = ["//src/test/cpp/util:file_test"]

# Bazel itself — the flagship "Bazel builds Bazel" build (Java + C++).
# Source pinned in //bazel_runner:extension.bzl (@bazel_archive, release 9.1.1).
# The release's own .bazelversion pins 9.0.1; we run the 9.1.1 inner (a
# patch-newer Bazel builds it). If that mismatch bites, pin a 9.0.1 inner in
# //bazel_runner and set bazel_version here.
#
# Built with the fully-hermetic LLVM toolchain: Bazel's MODULE uses rules_cc's
# autodetected Unix toolchain, so HERMETIC_LLVM's --extra_toolchains wins for
# the C++ actions (the client + native code); Java uses Bazel's bundled JDK.
# HERMETIC_ZIP supplies `zip` on the inner PATH (Bazel's genrules call it ~72x),
# built from Info-ZIP source — so no host `zip` is required.
#
#   bazel run //projects/bazel:build_local_linux_amd64 -- //src:bazel-bin
#   bazel run //projects/bazel:test_local_linux_amd64
#   bazel run //projects/bazel:test_rbe_linux_amd64
#
# LOCAL + RBE. The build is //src:bazel-bin; the test goal scopes to the C++
# client unit tests (see test_spec below). On RBE the zip genrules are satisfied
# by the executor image's own `zip` (HERMETIC_ZIP's from-source `zip` is what
# makes the *local* build need no host zip).
#
# RBE covers the remote execution path; LOCAL covers the ambient host toolchain
# path.
BAZEL_PROJECT = project_spec(
    name = "bazel",
    source = tarball_source(
        archive = "@bazel_archive//file",
        strip_prefix = "bazel-9.1.1",
    ),
    toolchains = [HERMETIC_LLVM, HERMETIC_ZIP],
    environments = [LOCAL, RBE],
    # HERMETIC_LLVM appends the `llvm` module, which resolves newer transitive
    # versions of platforms/bazel_features/rules_cc than Bazel's own MODULE pins
    # as direct deps. Bazel-the-tool builds with strict direct-dependency
    # checking (error by default), so relax it for this project — the upgrades
    # are backward-compatible and only the overlay introduces them.
    build = build_spec(
        targets = ["//src:bazel-bin"],
        flags = [
            "--check_direct_dependencies=off",
            "--java_language_version=21",
            "--tool_java_language_version=21",
            "--java_runtime_version=remotejdk_21",
            "--tool_java_runtime_version=remotejdk_21",
        ],
    ),
    # Test parity is the C++ client unit tests (//src/test/cpp/...): pure
    # gtest+abseil unit tests that exercise Bazel's own C++ (startup options, rc
    # parsing, the launcher's archive/util layers) under the hermetic LLVM
    # toolchain — no running server, no bazel-in-bazel. The Java and shell
    # integration suites need a built Bazel + many host tools, so we scope to the
    # hermetic C++ core, mirroring grpc (promise core) and ortools (CP-SAT core).
    test = test_spec(
        targets = ["//src/test/cpp/..."],
        flags = [
            "--check_direct_dependencies=off",
            "--java_language_version=21",
            "--tool_java_language_version=21",
            "--java_runtime_version=remotejdk_21",
            "--tool_java_runtime_version=remotejdk_21",
        ],
        # file_test's permission/large-file assertions fail under the root RBE
        # executor; run it only on the (non-root) local host. See above.
        exclude_on = {"rbe": _ROOT_SENSITIVE_TESTS},
    ),
)
