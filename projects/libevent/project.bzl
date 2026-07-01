load("//kiss:defs.bzl", "CIIMG", "LOCAL", "bcr_module_source", "project_spec", "test_spec")
# libevent — async event-notification C library (libevent/libevent).
# A "BCR module" project: the runner bazel_dep()s the module from the Bazel
# Central Registry and runs its own presubmit test target. Host tier: builds and
# tests with the ambient toolchain on LOCAL and in the full CI image (CIIMG) — no
# hermetic LLVM. (RBE/hermetic not wired: reach for it only when needed.)
LIBEVENT_PROJECT = project_spec(
    name = "libevent",
    source = bcr_module_source(
        module = "libevent",
        version = "2.1.12-stable.bcr.0",
    ),
    environments = [LOCAL, CIIMG],
    test = test_spec(targets = ["@libevent//..."], flags = ["-c", "opt"]),
)
