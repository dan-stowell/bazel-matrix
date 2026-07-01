load("//kiss:defs.bzl", "LOCAL", "RBE", "build_spec", "project_spec", "tarball_source", "test_spec")
# cctz/time tests read the host tzdata, absent off-host (RBE); see below.
_CCTZ_TIME_TESTS = [
    "//absl/time:time_test",
    "//absl/time/internal/cctz:time_zone_format_test",
    "//absl/time/internal/cctz:time_zone_lookup_test",
]

# Abseil's C++ common libraries — the matrix's first build.
# Source pinned in //kiss:extension.bzl (@absl_archive, release
# 20260526.0), built from the upstream source/module as-is. The hermetic
# LLVM modification lives in //projects/abseil_cpp/hermetic_llvm.
#
ABSEIL_CPP_PROJECT = project_spec(
    name = "abseil_cpp",
    source = tarball_source(
        archive = "@absl_archive//file",
        strip_prefix = "abseil-cpp-20260526.0",
    ),
    environments = [LOCAL, RBE],
    build = build_spec(targets = ["//absl/..."], flags = ["-c", "opt"]),
    test = test_spec(
        targets = ["//absl/..."],
        # The cctz/time tests read the system timezone database
        # (/usr/share/zoneinfo), which the RBE executor image does not ship and
        # which isn't a Bazel-tracked input — so they're excluded off-host. A hermetic tzdata
        # input, or a tzdata-bearing executor, would re-include them.
        exclude_on = {
            "rbe": _CCTZ_TIME_TESTS,
        },
    ),
)
