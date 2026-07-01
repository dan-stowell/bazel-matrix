load("//kiss:defs.bzl", "CIIMG", "LOCAL", "RBE", "bcr_module_source", "build_spec", "project_spec", "test_spec")
# toml++ — header-only TOML parser/serializer for C++ (marzer/tomlplusplus). A
# "BCR module" project running its own @tomlplusplus//... targets. LOCAL + CIIMG
# use the ambient host/CI-image gcc; RBE uses hermetic LLVM. BCR 3.4.0.
TOMLPLUSPLUS_PROJECT = project_spec(
    name = "tomlplusplus",
    source = bcr_module_source(
        module = "tomlplusplus",
        version = "3.4.0",
    ),
    environments = [LOCAL, CIIMG, RBE],
    build = build_spec(targets = ["@tomlplusplus"], flags = ["-c", "opt"]),
    test = test_spec(targets = ["@tomlplusplus//..."], flags = ["-c", "opt"]),
)
