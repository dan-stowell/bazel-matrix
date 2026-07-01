load("//kiss:defs.bzl", "CIIMG", "LOCAL", "RBE", "bcr_module_source", "build_spec", "project_spec", "test_spec")
# simdutf — fast SIMD Unicode validation & transcoding (UTF-8/16/32, base64), C++.
# This is a "BCR module" project: rather than pinning the upstream source and
# running its in-repo BUILD, the runner synthesizes a root module that
# bazel_dep()s simdutf from the Bazel Central Registry and builds/tests its own
# @simdutf//... targets — the build_targets/test_targets the BCR's presubmit.yml
# runs. The registry resolves simdutf's source, patches, and MODULE.bazel.
# Pinned to BCR 7.7.0.
#
# Toolchain by env (bcr_project default): LOCAL + CIIMG build with the ambient
# host / CI-image gcc (no hermetic overlay); RBE uses hermetic LLVM (the host
# toolchain can't match the remote executor's compiler).
#
#   bazel run //projects/simdutf:test_local_linux_amd64
#   bazel run //projects/simdutf:test_ciimg_linux_amd64
#   bazel run //projects/simdutf:test_rbe_linux_amd64
SIMDUTF_PROJECT = project_spec(
    name = "simdutf",
    source = bcr_module_source(
        module = "simdutf",
        version = "7.7.0",
    ),
    environments = [LOCAL, CIIMG, RBE],
    build = build_spec(targets = ["@simdutf"], flags = ["-c", "opt"]),
    test = test_spec(targets = ["@simdutf//:test"], flags = ["-c", "opt"]),
)
