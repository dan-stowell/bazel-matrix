"""Module extensions that fetch hermetic, pinned build inputs.

Two extensions:

* `inner_bazel` — the Bazel binary used to run the *inner* project builds. We
  pin a specific release (version + sha256) and download the official binary,
  rather than depending on a host-installed bazel/bazelisk. linux + darwin,
  amd64 + arm64.

* `project_sources` — source tarballs of the museum's projects, pinned by
  sha256. This is the kickoff's "project source code as a dep in MODULE.bazel":
  each project's source is an immutable, content-addressed input. We fetch the
  tarball as an opaque file (http_file) so the *outer* Bazel never parses the
  project's own BUILD files — the inner Bazel does that, against an extracted
  copy.
"""

load("@bazel_tools//tools/build_defs/repo:http.bzl", "http_file")

# --- Inner Bazel binaries --------------------------------------------------

# The default inner Bazel. Most projects build with this; a project that targets
# an older Bazel (see its .bazelversion / bazel_compatibility) can ask for a
# different version via museum_project(bazel_version = ...).
DEFAULT_INNER_BAZEL_VERSION = "9.1.1"

# version -> {repo suffix: (release arch tag, sha256 of the binary)}. The repos
# are named inner_bazel_<version-with-underscores>_<suffix> (e.g.
# inner_bazel_9_1_1_linux_amd64). Add a version block to support a new inner.
_INNER_BAZELS = {
    "9.1.1": {
        "linux_amd64": ("linux-x86_64", "857bed5d2756b4d998d3caebf2d941d13d434c4eda4b1d6d7dda205736c25a93"),
        "linux_arm64": ("linux-arm64", "82d1163884e45a6a7ff764cc01197b1b1ed497000726b84dc4b47c1dfc8a2bb4"),
        "darwin_amd64": ("darwin-x86_64", "6fd490084bdccf044d7a6d8360a26f8770fa09f4e624328efea292f493204930"),
        "darwin_arm64": ("darwin-arm64", "2db883718453f0437a7bcb408e889dbf8539cdc4d61c8ebc3807a1a88d02ff08"),
    },
    # Mature projects (grpc, flatbuffers, ...) target Bazel 8; building them with
    # the Bazel 9 inner fights their pre-Bazel-9 transitive dep graph. We pin a
    # late Bazel 8: it predates Bazel 9's rule removals BUT has repo_metadata
    # (added in 8.3), which the hermetic-llvm toolchain requires — so the same
    # zero-sysroot toolchain works here. (8.0.1, grpc's own .bazelversion, lacks
    # repo_metadata and can't carry hermetic-llvm.)
    "8.7.0": {
        "linux_amd64": ("linux-x86_64", "d7606e679b78067c811096fb3d6cf135225b528835ca396e3a4dddf957859544"),
        "linux_arm64": ("linux-arm64", "bfe9558bd8a2ecfe4841ec46c0dbccb4b469fe22d81f2f859de0de222b3e7ce3"),
        "darwin_amd64": ("darwin-x86_64", "76f3eb05782098e9f9ddd8247ec969b085195a3ae2978c81721a2235052ccf26"),
        "darwin_arm64": ("darwin-arm64", "575f20fb23955e02f73519befd180df635b4ed0960c60f0e70fcc8d74014a713"),
    },
}


def _version_tag(version):
    return version.replace(".", "_")


def _inner_bazel_impl(_ctx):
    for version, plats in _INNER_BAZELS.items():
        vtag = _version_tag(version)
        for suffix, (arch, sha256) in plats.items():
            http_file(
                name = "inner_bazel_{}_{}".format(vtag, suffix),
                urls = ["https://github.com/bazelbuild/bazel/releases/download/{v}/bazel-{v}-{a}".format(
                    v = version,
                    a = arch,
                )],
                sha256 = sha256,
                executable = True,
                downloaded_file_path = "bazel",
            )


inner_bazel = module_extension(implementation = _inner_bazel_impl)

# --- Project source archives ----------------------------------------------

# repo name -> dict(url, sha256, filename). Add a line here to vendor a new
# project's source. The repo's file is reachable as `@<name>//file`.
_PROJECT_SOURCES = {
    "absl_archive": {
        "url": "https://github.com/abseil/abseil-cpp/releases/download/20260526.0/abseil-cpp-20260526.0.tar.gz",
        "sha256": "6e1aee535473414164bf83e4ebc40240dec71a4701f8a642d906e95bea1aea0c",
        "filename": "abseil-cpp-20260526.0.tar.gz",
    },
    "copybara_archive": {
        "url": "https://github.com/google/copybara/archive/refs/tags/v20260622.tar.gz",
        "sha256": "62fd6f98f6414c0ed846f839f391e3c88bbbc7d2440cb353b4009a711b4d5ea0",
        "filename": "copybara-v20260622.tar.gz",
    },
    "cxx_archive": {
        "url": "https://github.com/dtolnay/cxx/archive/refs/tags/1.0.194.tar.gz",
        "sha256": "2edf94915ab43778b02a13e522d050a76dea607d1a05f769911775676d27cb3c",
        "filename": "cxx-1.0.194.tar.gz",
    },
    # Protocol Buffers — the canonical first-party Bazel C++ project. We pin the
    # release's Bazel-specific source dist (the variant the BCR consumes), which
    # ships the bzlmod MODULE.bazel and depends on abseil-cpp/rules_cc/zlib.
    "protobuf_archive": {
        "url": "https://github.com/protocolbuffers/protobuf/releases/download/v35.1/protobuf-35.1.bazel.tar.gz",
        "sha256": "75b7b0b36b630c7b6e3aeb07b2e58993fb9494fbb2b08bba0891aaa231d4e4d1",
        "filename": "protobuf-35.1.bazel.tar.gz",
    },
    # gRPC — first-party Bazel; pairs naturally with protobuf. Fully bzlmod
    # (its legacy WORKSPACE is ignored under Bazel 9); pulls boringssl, abseil,
    # c-ares, protobuf, re2, zlib from the BCR.
    "grpc_archive": {
        "url": "https://github.com/grpc/grpc/archive/refs/tags/v1.81.1.tar.gz",
        "sha256": "48ae0d05f87206112d9e9144a923191ee1e482141a70686ec58dc86d0b40fddc",
        "filename": "grpc-1.81.1.tar.gz",
    },
    # GoogleTest — the C++ test framework. First-party Bazel, builds + tests
    # itself with the hermetic LLVM toolchain.
    "googletest_archive": {
        "url": "https://github.com/google/googletest/archive/refs/tags/v1.17.0.tar.gz",
        "sha256": "65fab701d9829d38cb77c14acdc431d2108bfdbf8979e40eb8ae567edf10b27c",
        "filename": "googletest-1.17.0.tar.gz",
    },
    # nlohmann/json — JSON for Modern C++. Header-only; first-party Bazel.
    "json_archive": {
        "url": "https://github.com/nlohmann/json/archive/refs/tags/v3.12.0.tar.gz",
        "sha256": "4b92eb0c06d10683f7447ce9406cb97cd4b453be18d7279320f7b2f025c10187",
        "filename": "json-3.12.0.tar.gz",
    },
    # FlatBuffers — serialization library + flatc compiler. First-party Bazel.
    "flatbuffers_archive": {
        "url": "https://github.com/google/flatbuffers/archive/refs/tags/v25.12.19-2026-02-06-03fffb2.tar.gz",
        "sha256": "ccbce58684691de1e7d51f5e87786266b37d06ab66e9dfe2d0ec106fe50aace0",
        "filename": "flatbuffers-25.12.19-2026-02-06-03fffb2.tar.gz",
    },
    # Catch2 — C++ test framework. First-party Bazel.
    "catch2_archive": {
        "url": "https://github.com/catchorg/Catch2/archive/refs/tags/v3.15.1.tar.gz",
        "sha256": "be23a52b85cf04cd9587612147a10b023d59ed9757fa1843cc99e615d6c0893c",
        "filename": "Catch2-3.15.1.tar.gz",
    },
    # OR-Tools — Google's optimization suite. First-party Bazel, modern deps.
    "ortools_archive": {
        "url": "https://github.com/google/or-tools/archive/refs/tags/v9.15.tar.gz",
        "sha256": "6395a00a97ff30af878ee8d7fd5ad0ab1c7844f7219182c6d71acbee1b5f3026",
        "filename": "or-tools-9.15.tar.gz",
    },
    # Brotli — compression library + CLI. Release ships BUILD files but no
    # MODULE.bazel (see //builds/brotli, which synthesizes one).
    "brotli_archive": {
        "url": "https://github.com/google/brotli/archive/refs/tags/v1.2.0.tar.gz",
        "sha256": "816c96e8e8f193b40151dad7e8ff37b1221d019dbcb9c35cd3fadbfe6477dfec",
        "filename": "brotli-1.2.0.tar.gz",
    },
    # Bazel itself — the flagship "Bazel builds Bazel" build (Java + C++). The
    # release's own .bazelversion pins 9.0.1 to build it; we run the 9.1.1 inner
    # (a patch-newer Bazel builds it). Target //src:bazel-bin. Bazel's MODULE
    # uses rules_cc's autodetected Unix toolchain, so HERMETIC_LLVM slots in as
    # for the other C++ projects.
    "bazel_archive": {
        "url": "https://github.com/bazelbuild/bazel/archive/refs/tags/9.1.1.tar.gz",
        "sha256": "bdc0f7fb282eaa31df2e97d1bb1fc22965ec6d9ec95a8e8f126c7a2a7636552c",
        "filename": "bazel-9.1.1.tar.gz",
    },
    # RE2 — Google's regular-expression library (C++). First-party Bazel
    # (modern MODULE.bazel + rules_cc loads), depends on abseil-cpp. Release
    # tarball; built with hermetic LLVM like the other C++ projects.
    "re2_archive": {
        "url": "https://github.com/google/re2/releases/download/2025-11-05/re2-2025-11-05.tar.gz",
        "sha256": "87f6029d2f6de8aa023654240a03ada90e876ce9a4676e258dd01ea4c26ffd67",
        "filename": "re2-2025-11-05.tar.gz",
    },
    # snappy — Google's fast compression/decompression library (C++). First-party
    # Bazel; its BUILD calls cc_* unloaded and its tests pull in googletest, so it
    # runs on the Bazel 8.7 inner like the other pre-Bazel-9 C++ projects.
    "snappy_archive": {
        "url": "https://github.com/google/snappy/archive/refs/tags/1.2.2.tar.gz",
        "sha256": "90f74bc1fbf78a6c56b3c4a082a05103b3a56bb17bca1a27e052ea11723292dc",
        "filename": "snappy-1.2.2.tar.gz",
    },
    # google/benchmark — the C++ microbenchmark library. First-party Bazel; the
    # library loads rules_cc, but its tests use googletest (cc_* unloaded), so it
    # runs on the Bazel 8.7 inner.
    "benchmark_archive": {
        "url": "https://github.com/google/benchmark/archive/refs/tags/v1.9.5.tar.gz",
        "sha256": "9631341c82bac4a288bef951f8b26b41f69021794184ece969f8473977eaa340",
        "filename": "benchmark-1.9.5.tar.gz",
    },
    # zlib — the ubiquitous DEFLATE compression library (C). First-party Bazel
    # (ships MODULE.bazel + a BUILD that loads rules_cc), so it builds on the
    # default 9.1.1 inner. Exercises the hermetic LLVM toolchain's C path.
    "zlib_archive": {
        "url": "https://github.com/madler/zlib/archive/refs/tags/v1.3.2.tar.gz",
        "sha256": "b99a0b86c0ba9360ec7e78c4f1e43b1cbdf1e6936c8fa0f6835c0cd694a495a1",
        "filename": "zlib-1.3.2.tar.gz",
    },
    # highway — Google's portable SIMD/vector library (C++). First-party Bazel;
    # the library loads rules_cc but its tests use googletest (cc_* unloaded), so
    # it runs on the Bazel 8.7 inner.
    "highway_archive": {
        "url": "https://github.com/google/highway/archive/refs/tags/1.4.0.tar.gz",
        "sha256": "e72241ac9524bb653ae52ced768b508045d4438726a303f10181a38f764a453c",
        "filename": "highway-1.4.0.tar.gz",
    },
    # jsoncpp — the classic C++ JSON library. First-party Bazel (loads rules_cc;
    # its unit test uses its own harness, not googletest), so it builds on the
    # default 9.1.1 inner.
    "jsoncpp_archive": {
        "url": "https://github.com/open-source-parsers/jsoncpp/archive/refs/tags/1.9.8.tar.gz",
        "sha256": "51828cf3574281d2b79ec2a1c56a9e4c20cc1103711321ea96384cffb8d2d904",
        "filename": "jsoncpp-1.9.8.tar.gz",
    },
    # magic_enum — static reflection for C++ enums (header-only). First-party
    # Bazel (loads rules_cc; its tests vendor a Catch2 single-header), so it
    # builds on the default 9.1.1 inner.
    "magic_enum_archive": {
        "url": "https://github.com/Neargye/magic_enum/archive/refs/tags/v0.9.8.tar.gz",
        "sha256": "1e54959a3f3cb675938d858603ad69d0f3f7c82439fc2bf86d7232daec2bd10e",
        "filename": "magic_enum-0.9.8.tar.gz",
    },
}


def _project_sources_impl(_ctx):
    for name, info in _PROJECT_SOURCES.items():
        http_file(
            name = name,
            urls = [info["url"]],
            sha256 = info["sha256"],
            downloaded_file_path = info["filename"],
        )


project_sources = module_extension(implementation = _project_sources_impl)
