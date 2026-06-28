"""The `client` axis: which build client runs a project's actions.

A museum goal is a point in `command x environment x client x platform`:

* environment (//builds:environments.bzl) = *where* actions execute (host,
  container, RBE, ...).
* client (this file) = *what* drives the build. Today every client is a pinned
  Bazel release (//tools/fetch), so a client is effectively a Bazel version —
  but the axis is named, not a bare version string, so non-Bazel clients (a
  different build tool, a patched Bazel, ...) can join later without reshaping
  the grid.

A project declares the clients it supports (`museum_project(clients = [...])`);
the goal grid crosses them, emitting `<command>_<env>_<client>_<platform>`.
"""

def client(name, bazel_version):
    """A build client. `kind` is always "bazel" today (a pinned Bazel release)."""
    return struct(name = name, kind = "bazel", bazel_version = bazel_version)

# name -> client. To add one, register its inner Bazel in //tools/fetch too.
# Names follow the Bazel major line (bazel9 = the pinned 9.x, bazel8 = 8.x); a
# future second 9.x would be bazel9_2 etc.
CLIENTS = {
    "bazel9": client("bazel9", "9.1.1"),
    "bazel8": client("bazel8", "8.7.0"),
}

DEFAULT_CLIENT = "bazel9"

# Back-compat: map a raw inner Bazel version (the legacy `bazel_version=` arg) to
# a client name, so existing projects need no edits — they keep passing
# bazel_version and get the matching single client.
_VERSION_TO_CLIENT = {c.bazel_version: name for name, c in CLIENTS.items()}

def clients_for(bazel_version, clients):
    """Resolve a project's list of client structs.

    If `clients` (a list of names) is given, use them in order (the first is the
    project's default client). Otherwise derive a single client from the legacy
    `bazel_version`.
    """
    if clients:
        out = []
        for n in clients:
            if n not in CLIENTS:
                fail("unknown client %r; known: %s" % (n, sorted(CLIENTS)))
            out.append(CLIENTS[n])
        return out
    name = _VERSION_TO_CLIENT.get(bazel_version)
    if not name:
        fail("no client registered for bazel_version %r; add it to //builds:clients.bzl" % bazel_version)
    return [CLIENTS[name]]
