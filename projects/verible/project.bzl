load("//kiss:defs.bzl", "LOCAL", "RBE", "build_spec", "project_spec", "tarball_source", "test_spec")
# verible — CHIPS Alliance's SystemVerilog developer suite (parser, style linter,
# formatter, language server), C++. Source pinned in //kiss:extension.bzl
# (@verible_archive, the v0.0-4080-ga0a8d8eb commit), built from the upstream
# source/module as-is. The hermetic LLVM modification lives in
# //projects/verible/hermetic_llvm. First-party Bazel (MODULE.bazel + loaded
# cc_* rules) declaring all of its deps in-module (abseil, skylib,
# nlohmann_json, protobuf, re2, rules_*, platforms), so it runs on the default
# Bazel 9 inner with no dep overlay.
VERIBLE_PROJECT = project_spec(
    name = "verible",
    source = tarball_source(
        archive = "@verible_archive//file",
        strip_prefix = "verible-a0a8d8eb8cfa9fd8969c9d646454d363b48aa449",
    ),
    environments = [LOCAL, RBE],
    build = build_spec(targets = ["//verible/common/util:logging"], flags = ["-c", "opt"]),
    # A deterministic core of verible/common/util unit tests — the generic
    # container/algorithm/interval utilities that underpin the whole suite. These
    # depend only on abseil + googletest (NOT the bison/flex SystemVerilog parser),
    # so the goal stays fast and hermetic on local, the container, and RBE. The
    # full tree has 217 cc_tests, many tied to the heavy parser/formatter.
    test = test_spec(
        targets = [
            "//verible/common/util:algorithm_test",
            "//verible/common/util:auto-pop-stack_test",
            "//verible/common/util:bijective-map_test",
            "//verible/common/util:enum-flags_test",
            "//verible/common/util:forward_test",
            "//verible/common/util:interval_test",
            "//verible/common/util:interval-set_test",
            "//verible/common/util:range_test",
            "//verible/common/util:type-traits_test",
            "//verible/common/util:value-saver_test",
        ],
        flags = ["-c", "opt"],
    ),
)
