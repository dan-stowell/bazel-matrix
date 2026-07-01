load("//kiss:defs.bzl", "CIIMG", "LOCAL", "RBE", "bcr_module_source", "build_spec", "project_spec", "test_spec")
# GLM — OpenGL Mathematics, header-only C++ math library for graphics (g-truc).
# A "BCR module" project running its own @glm//... targets. LOCAL + CIIMG use the
# ambient host/CI-image gcc; RBE uses hermetic LLVM. Pinned to BCR 1.0.3.
GLM_PROJECT = project_spec(
    name = "glm",
    source = bcr_module_source(
        module = "glm",
        version = "1.0.3",
    ),
    environments = [LOCAL, CIIMG, RBE],
    build = build_spec(targets = ["@glm//:glm"], flags = ["-c", "opt"]),
    test = test_spec(targets = ["@glm//..."], flags = ["-c", "opt"]),
)
