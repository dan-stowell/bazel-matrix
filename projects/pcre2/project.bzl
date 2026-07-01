load("//kiss:defs.bzl", "LOCAL", "RBE", "build_spec", "project_spec", "tarball_source", "test_spec")
# PCRE2 — Perl Compatible Regular Expressions (version 2), the C regex engine used
# by Git, PHP, Apache, nginx and many others. Source pinned in
# //kiss:extension.bzl (@pcre2_archive, pcre2-10.47). First-party Bazel:
# root BUILD loads cc_* from rules_cc, so the default 9.1.1 inner builds it
# as-authored. The hermetic LLVM modification lives in //projects/pcre2/hermetic_llvm. Upstream's Bazel file wraps the pcre2test CLI test harness as
# //:pcre2_test. pcre2's MODULE declares a direct platforms dep (no PLATFORMS_DEP).
#
PCRE2_PROJECT = project_spec(
    name = "pcre2",
    source = tarball_source(
        archive = "@pcre2_archive//file",
        strip_prefix = "pcre2-pcre2-10.47",
    ),
    bazel_version = "9.1.1",
    environments = [LOCAL, RBE],
    build = build_spec(targets = ["//:pcre2"], flags = ["-c", "opt"]),
    test = test_spec(targets = ["//:pcre2_test"], flags = ["-c", "opt"]),
)
