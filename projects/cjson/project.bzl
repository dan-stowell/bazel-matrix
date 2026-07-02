load("//bazel_runner:defs.bzl", "LOCAL", "RBE", "bcr_module_source", "build_spec", "project_spec", "test_spec")
# cJSON — ultralightweight JSON parser in C (DaveGamble/cJSON). A "BCR module"
# project: the runner bazel_dep()s cjson from the Bazel Central Registry and runs
# its own @cjson//... targets. LOCAL uses the ambient host gcc; RBE uses hermetic
# LLVM. Pinned to BCR 1.7.19 (bcr.4).
#
_RUNFILE_SENSITIVE_TESTS = ["@cjson//tests:parse_examples"]

CJSON_PROJECT = project_spec(
    name = "cjson",
    source = bcr_module_source(
        module = "cjson",
        version = "1.7.19-0.20240923110858-12c4bf1986c2.bcr.4",
    ),
    environments = [LOCAL, RBE],
    build = build_spec(targets = ["@cjson"], flags = ["-c", "opt"]),
    test = test_spec(
        targets = ["@cjson//..."],
        flags = ["-c", "opt"],
        exclude_on = {
            "local": _RUNFILE_SENSITIVE_TESTS,
            "rbe": _RUNFILE_SENSITIVE_TESTS,
        },
    ),
)
