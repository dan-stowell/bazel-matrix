load("//kiss:defs.bzl", "LOCAL", "RBE", "build_spec", "project_spec", "tarball_source", "test_spec")
# cctz — Google's C++ library for civil-time and time-zone calculations (the
# basis of absl::time). Source pinned in //kiss:extension.bzl
# (@cctz_archive, master commit f353c12), built from the upstream source/module
# as-is. The hermetic LLVM modification lives in //projects/cctz/hermetic_llvm.
# cctz declares the platforms dep directly (no PLATFORMS_DEP) and
# googletest comes from its own MODULE dep (BCR). Although its own BUILD loads
# cc_* explicitly, a transitive dev-dep (fuzztest → rules_go / aspect_bazel_lib)
# registers toolchains that use Bazel-9-removed APIs (CcInfo), so it runs on the
# Bazel 8.7 inner.
#
CCTZ_PROJECT = project_spec(
    name = "cctz",
    source = tarball_source(
        archive = "@cctz_archive//file",
        strip_prefix = "cctz-f353c121a9e4fb55a9c623899e87197eaee0392d",
    ),
    bazel_version = "8.7.0",
    environments = [LOCAL, RBE],
    build = build_spec(targets = ["//:time_zone"], flags = ["-c", "opt"]),
    # civil_time_test is pure date arithmetic and fully hermetic. The two
    # time-zone tests read tz data from the system /usr/share/zoneinfo (cctz
    # bundles none as a Bazel data dep); they pass in the local sandbox but fail
    # on the RBE executors, which carry no zoneinfo — so they're excluded.
    test = test_spec(
        targets = ["//:civil_time_test"],
        flags = ["-c", "opt"],
    ),
)
