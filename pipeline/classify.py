"""Heuristics to distinguish projects from Bazel rulesets and tooling."""

from . import model

_TOOLING_OWNERS = {
    "aspect-build",
    "bazel-contrib",
    "bazelbuild",
}

_RULESET_HINTS = ("rules_", "_rules", "-rules", "rules-")
_TOOLING_HINTS = (
    "bazel_",
    "_bazel",
    "bazel-",
    "-bazel",
    "buildifier",
    "buildtools",
    "gazelle",
    "skylib",
    "stardoc",
    "toolchain",
)
_KNOWN_TOOLING = {
    "apple_support",
    "bazel_features",
    "bazel_skylib",
    "platforms",
    "stardoc",
}

_KNOWN_TOOLCHAINS = {
    "hermetic_cc_toolchain",
    "toolchains_llvm",
    "toolchains_protoc",
}


def is_ruleset_module(module_name, owner=""):
    category, _ = classify_bcr(module_name, owner)
    return category == model.CATEGORY_RULESET


def is_toolchain_module(module_name):
    """Return whether a BCR module primarily distributes a toolchain."""
    name = (module_name or "").lower()
    return (
        name in _KNOWN_TOOLCHAINS
        or name.startswith("toolchain_")
        or name.startswith("toolchains_")
        or name.endswith("_toolchain")
        or name.endswith("_toolchains")
    )


def classify_bcr(module_name, owner):
    name = module_name.lower()
    own = (owner or "").lower()

    if name in _KNOWN_TOOLING:
        return model.CATEGORY_TOOLING, "known Bazel tooling module '{}'".format(module_name)
    for hint in _RULESET_HINTS:
        if hint in name:
            return model.CATEGORY_RULESET, "module name contains '{}'".format(hint)
    for hint in _TOOLING_HINTS:
        if hint in name:
            return model.CATEGORY_TOOLING, "module name contains '{}'".format(hint)
    if own in _TOOLING_OWNERS:
        return model.CATEGORY_TOOLING, "published by Bazel tooling org '{}'".format(owner)
    return model.CATEGORY_PROJECT, "BCR module not matching ruleset/tooling heuristics"
