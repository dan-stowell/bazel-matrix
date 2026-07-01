load("//kiss:defs.bzl", "CIIMG", "LOCAL", "RBE", "bcr_module_source", "build_spec", "project_spec", "test_spec")
# lexy — C++ parser combinator library (foonathan/lexy). A "BCR module" project
# running its own @lexy//:lexy_test target. Pinned to the Bazel 8.7 inner (its
# test target isn't visible to the Bazel 9 inner). LOCAL + CIIMG use the ambient
# host/CI-image gcc; RBE uses hermetic LLVM. BCR 2025.05.0.
LEXY_PROJECT = project_spec(
    name = "lexy",
    source = bcr_module_source(
        module = "lexy",
        version = "2025.05.0",
    ),
    bazel_version = "8.7.0",
    environments = [LOCAL, CIIMG, RBE],
    build = build_spec(targets = ["@lexy//:lexy"], flags = ["-c", "opt"]),
    test = test_spec(targets = ["@lexy//:lexy_test"], flags = ["-c", "opt"]),
)
