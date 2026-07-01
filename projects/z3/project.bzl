load("//kiss:defs.bzl", "HERMETIC_LLVM", "LOCAL", "MINIMG", "RBE", "build_spec", "project_spec", "tarball_source")
# z3 — Microsoft Research's Z3 SMT theorem prover (C++). Source pinned in
# //kiss:extension.bzl (@z3_archive, release z3-4.16.0). First-party
# Bazel: its //:z3 target is a rules_foreign_cc cmake() build, so the host-local
# path drives the project's own CMake build with the host cmake/make/gcc. No
# upstream Bazel test target, so this is a build-only project. z3's MODULE
# declares a direct platforms dep, so no PLATFORMS_DEP overlay.
#
#   bazel run //projects/z3:build_local_linux_amd64
Z3_PROJECT = project_spec(
    name = "z3",
    source = tarball_source(
        archive = "@z3_archive//file",
        strip_prefix = "z3-z3-4.16.0",
    ),
    toolchains = [HERMETIC_LLVM],
    bazel_version = "9.1.1",
    environments = [LOCAL, RBE, MINIMG],
    build = build_spec(targets = ["//:z3"], flags = ["-c", "opt"]),
)
