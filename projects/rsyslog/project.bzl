load("//kiss:defs.bzl", "LOCAL", "bcr_module_source", "project_spec", "test_spec")
# rsyslog — high-performance system log processing in C (rsyslog/rsyslog).
# A "BCR module" project running its own @rsyslog//... presubmit test target on
# the Bazel 8.7 inner with the ambient host toolchain.
#
# LOCAL only: the test passes on the host gcc-13 but fails under the CI image's
# gcc (CIIMG) — a toolchain-sensitive case, like cjson. A host-tier "builds+tests
# on the dev host" entry, not (yet) reproducible.
RSYSLOG_PROJECT = project_spec(
    name = "rsyslog",
    source = bcr_module_source(
        module = "rsyslog",
        version = "8.2504.0",
    ),
    bazel_version = "8.7.0",
    environments = [LOCAL],
    test = test_spec(targets = ["@rsyslog//..."], flags = ["-c", "opt"]),
)
