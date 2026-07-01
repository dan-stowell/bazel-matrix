load("//kiss:defs.bzl", "LOCAL", "RBE", "build_spec", "project_spec", "tarball_source", "test_spec")
S2_TEST_TARGETS = [
    "//:s1angle_test",
    "//:s1chord_angle_test",
    "//:s1interval_test",
    "//:r1interval_test",
    "//:r2rect_test",
    "//:s2cell_id_test",
    "//:s2coords_test",
    "//:s2latlng_test",
    "//:s2point_test",
    "//:s2cap_test",
]

# s2geometry — Google's S2, a C++ library for spherical geometry (cells, regions,
# indexing on the sphere; the math behind geographic systems). Source pinned in
# //kiss:extension.bzl (@s2geometry_archive, a commit archive), built from the
# upstream source/module as-is. The hermetic LLVM modification lives in
# //projects/s2geometry/hermetic_llvm. First-party Bazel, but the Bazel module
# is rooted at the repo's src/ subdir (src/MODULE.bazel), so strip_prefix
# descends into src/ to make that the workspace root and targets are //:...
# It loads cc_* rules and its MODULE declares all deps (abseil, skylib,
# rules_cc, googletest) including platforms, so it runs on the default Bazel 9
# inner with no dep overlay.
S2GEOMETRY_PROJECT = project_spec(
    name = "s2geometry",
    source = tarball_source(
        archive = "@s2geometry_archive//file",
        strip_prefix = "s2geometry-3f5bd2d93feda62a5d6fd0c3d7992f427968a66b/src",
    ),
    environments = [LOCAL, RBE],
    build = build_spec(targets = S2_TEST_TARGETS, flags = ["-c", "opt"]),
    # A core of deterministic primitive unit tests — the angle/interval scalar
    # types, S2 cell-id addressing, lat/lng + projection coords, the planar
    # interval/rect helpers, and spherical caps. The full src/ suite (115 tests)
    # includes randomized/heavy index and builder tests; this subset keeps the
    # goal fast and deterministic on local, the container, and RBE.
    test = test_spec(targets = S2_TEST_TARGETS, flags = ["-c", "opt"]),
)
