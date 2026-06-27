#!/usr/bin/env python3
# Render the README's "projects that build as they are" table from
# runner/verify-results.tsv (produced by runner/verify.sh).
#
#   python3 runner/_readme_table.py            # the works table (markdown)
#   python3 runner/_readme_table.py --notes    # also the "doesn't build as-is" list
#
# Each project: name (linked to source), one-line description, Bazel version,
# build command, test command — only listing what actually passed in the image.
import csv
import re
import sys

# proj-dir -> (display name, source repo, one-line description)
META = {
    "abseil_cpp":   ("abseil-cpp", "https://github.com/abseil/abseil-cpp", "Google's C++ standard-library extensions"),
    "abseil_py":    ("abseil-py", "https://github.com/abseil/abseil-py", "Google's Python common libraries (app/flags/logging)"),
    "benchmark":    ("google/benchmark", "https://github.com/google/benchmark", "Microbenchmark support library"),
    "boringssl":    ("BoringSSL", "https://github.com/google/boringssl", "Google's fork of OpenSSL"),
    "catch2":       ("Catch2", "https://github.com/catchorg/Catch2", "C++ unit-testing framework"),
    "cctz":         ("cctz", "https://github.com/google/cctz", "C++ civil-time and time-zone library"),
    "cli11":        ("CLI11", "https://github.com/CLIUtils/CLI11", "Command-line parser for C++11"),
    "copybara":     ("copybara", "https://github.com/google/copybara", "Transforms and moves code between repositories (Java)"),
    "cpu_features": ("cpu_features", "https://github.com/google/cpu_features", "Cross-platform CPU feature detection"),
    "crow":         ("Crow", "https://github.com/CrowCpp/Crow", "Header-only C++ web microframework"),
    "cxx":          ("cxx", "https://github.com/dtolnay/cxx", "Safe interop between Rust and C++ (Rust)"),
    "fast_float":   ("fast_float", "https://github.com/fastfloat/fast_float", "Fast number parsing from strings"),
    "flatbuffers":  ("FlatBuffers", "https://github.com/google/flatbuffers", "Memory-efficient serialization library"),
    "ftxui":        ("FTXUI", "https://github.com/ArthurSonzogni/FTXUI", "Functional terminal-UI library for C++"),
    "gflags":       ("gflags", "https://github.com/gflags/gflags", "Google's C++ command-line flags library"),
    "glog":         ("glog", "https://github.com/google/glog", "Google application-level logging library"),
    "googletest":   ("GoogleTest", "https://github.com/google/googletest", "Google's C++ test & mocking framework"),
    "gperftools":   ("gperftools", "https://github.com/gperftools/gperftools", "tcmalloc and performance profilers"),
    "highway":      ("highway", "https://github.com/google/highway", "Portable SIMD/vector intrinsics"),
    "json":         ("nlohmann/json", "https://github.com/nlohmann/json", "JSON for Modern C++"),
    "jsoncpp":      ("jsoncpp", "https://github.com/open-source-parsers/jsoncpp", "C++ library for reading/writing JSON"),
    "jsonnet":      ("jsonnet", "https://github.com/google/jsonnet", "Data-templating language"),
    "go_jsonnet":   ("go-jsonnet", "https://github.com/google/go-jsonnet", "Pure-Go implementation of Jsonnet"),
    "magic_enum":   ("magic_enum", "https://github.com/Neargye/magic_enum", "Static reflection for C++ enums"),
    "nsync":        ("nsync", "https://github.com/google/nsync", "C library of synchronization primitives"),
    "onetbb":       ("oneTBB", "https://github.com/uxlfoundation/oneTBB", "Intel's Threading Building Blocks"),
    "opencc":       ("OpenCC", "https://github.com/BYVoid/OpenCC", "Traditional/Simplified Chinese conversion"),
    "ortools":      ("OR-Tools", "https://github.com/google/or-tools", "Google's optimization suite (CP-SAT)"),
    "protobuf":     ("protobuf", "https://github.com/protocolbuffers/protobuf", "Protocol Buffers serialization"),
    "re2":          ("re2", "https://github.com/google/re2", "Fast, safe regular-expression engine"),
    "snappy":       ("snappy", "https://github.com/google/snappy", "Fast compression/decompression library"),
    "zlib":         ("zlib", "https://github.com/madler/zlib", "The zlib compression library"),
    "buildtools":   ("buildtools", "https://github.com/bazelbuild/buildtools", "Bazel BUILD formatter/linter, buildifier (Go)"),
    "doctest":      ("doctest", "https://github.com/doctest/doctest", "Single-header C++ testing framework"),
    "brotli":       ("brotli", "https://github.com/google/brotli", "Brotli compression"),
    "brotli_go":    ("brotli (Go)", "https://github.com/google/brotli", "Go bindings for brotli"),
    "grpc":         ("gRPC", "https://github.com/grpc/grpc", "High-performance RPC framework"),
    "grpc_gateway": ("grpc-gateway", "https://github.com/grpc-ecosystem/grpc-gateway", "gRPC-to-JSON reverse proxy + protoc plugins (Go)"),
    "bazel":        ("bazel", "https://github.com/bazelbuild/bazel", "The Bazel build system itself (Java/C++)"),
    "quill":        ("quill", "https://github.com/odygrd/quill", "Asynchronous low-latency C++ logging library"),
    "z3":           ("z3", "https://github.com/Z3Prover/z3", "Microsoft's Z3 SMT theorem prover"),
    "double_conversion": ("double-conversion", "https://github.com/google/double-conversion", "IEEE-754 double/string conversion (C++)"),
    "prometheus_cpp": ("prometheus-cpp", "https://github.com/jupp0r/prometheus-cpp", "Prometheus metrics client library for C++"),
    "openexr":      ("OpenEXR", "https://github.com/AcademySoftwareFoundation/openexr", "High-dynamic-range image format (C++, ASWF)"),
    "highs":        ("HiGHS", "https://github.com/ERGO-Code/HiGHS", "Linear/mixed-integer optimization solver (C++)"),
    "opentelemetry_cpp": ("opentelemetry-cpp", "https://github.com/open-telemetry/opentelemetry-cpp", "Observability API/SDK for C++ (traces/metrics/logs)"),
    "lcm":          ("LCM", "https://github.com/lcm-proj/lcm", "Lightweight Communications and Marshalling (robotics)"),
    "pcre2":        ("PCRE2", "https://github.com/PCRE2Project/pcre2", "Perl-compatible regular expressions (C)"),
    "iceoryx2":     ("iceoryx2", "https://github.com/eclipse-iceoryx/iceoryx2", "Zero-copy lock-free IPC middleware (Rust)"),
}

# Human-readable reason for the projects that don't build as they are.
FAIL_NOTE = {
    "brotli":     "ships no `MODULE.bazel` (WORKSPACE-only), so bzlmod sees no workspace",
    "brotli_go":  "same archive as brotli — no `MODULE.bazel`",
    "doctest":    "root `//:doctest` uses `includes=[\".\"]`, rejected for the main module (it's meant to be consumed as a dep)",
    "grpc":       "its `tools/bazel` wrapper downloads its own Bazel, which then can't find the host `gcc`",
}


def pass_fail(summary):
    """(pass, fail) counts from a 'X tests pass[, Y fail locally]' summary."""
    p = re.search(r"(\d+) tests? pass", summary)
    f = re.search(r"(\d+) (?:fails?|tests? fail)", summary)
    return (int(p.group(1)) if p else 0, int(f.group(1)) if f else 0)


def main():
    rows = list(csv.DictReader(open("runner/verify-results.tsv"), delimiter="\t"))
    works = [r for r in rows if r["build"] == "ok"]
    works.sort(key=lambda r: META.get(r["proj"], (r["proj"],))[0].lower())

    print("| Project | Description | Bazel | Build | Test |")
    print("|---------|-------------|:-----:|-------|------|")
    for r in works:
        proj = r["proj"]
        name, repo, desc = META.get(proj, (proj, "", ""))
        build_cmd = "`bazel run //projects/%s:build`" % proj
        if r["test"] == "ok":
            test_cmd = "`bazel run //projects/%s:test`" % proj
            p, f = pass_fail(r.get("test_summary", ""))
            if f:  # a few environment-sensitive tests fail locally
                test_cmd += " (%d/%d pass)" % (p, p + f)
        elif r["test"] == "none":
            test_cmd = "— (no upstream test target)"
        else:
            test_cmd = "— (test fails as-is)"
        print("| [%s](%s) | %s | %s | %s | %s |"
              % (name, repo, desc, r["version"], build_cmd, test_cmd))

    n_build = len(works)
    n_test = sum(1 for r in works if r["test"] == "ok")
    print()
    print("_%d projects build as they are; %d also run their upstream test suite in "
          "the image — most fully green, a few with environment-sensitive local "
          "failures noted inline (`N/M pass`)._" % (n_build, n_test))

    if "--notes" in sys.argv:
        print("\n### Doesn't build as-is\n")
        for r in rows:
            if r["build"] != "ok" and r["build"] != "n/a":
                name = META.get(r["proj"], (r["proj"],))[0]
                note = FAIL_NOTE.get(r["proj"], r["build"])
                print("- **%s** — %s" % (name, note))


if __name__ == "__main__":
    main()
