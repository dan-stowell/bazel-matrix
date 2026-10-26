"""Checks the system CA store of the image this runs on, and TLS with it.

Run by canary/tls_probe.sh with the image's own /usr/bin/python3 (stdlib
only). Each check is one JUnit testcase in $XML_OUTPUT_FILE; the log gets a
summary. CANARY_EXPECT=trusted (default) expects the baseline store;
distrusted expects the baseline minus the eMudhra/emSign roots. See
canary/README.md.

Results: PASS; FAIL (the store or verification is wrong: counts); NETERR
(DNS, connect, timeout after one retry: says nothing about the store, so it
doesn't fail the test unless no host check got through at all).
"""

import os
import re
import shutil
import socket
import ssl
import subprocess
import sys
import tempfile
import time
import urllib.request
from xml.sax.saxutils import escape, quoteattr

HERE = os.path.dirname(os.path.abspath(__file__))
BUNDLE = "/etc/ssl/certs/ca-certificates.crt"
CAPATH = "/etc/ssl/certs"
TOOLS = ["/usr/bin/python3", "curl", "openssl", "git"]
# Hosts builds hit (BCR, GitHub, language registries, BuildBuddy).
HOSTS = [
    "github.com",
    "objects.githubusercontent.com",
    "bcr.bazel.build",
    "mirror.bazel.build",
    "storage.googleapis.com",
    "pypi.org",
    "files.pythonhosted.org",
    "registry.npmjs.org",
    "repo1.maven.org",
    "static.crates.io",
    "proxy.golang.org",
    "buildbuddy.buildbuddy.io",
]
GIT_REPO = "https://github.com/bazelbuild/bazel-skylib"
RELEASE_ASSET = "https://github.com/bazelbuild/bazelisk/releases/download/v1.25.0/bazelisk-linux-amd64"
# Must fail certificate verification on any image.
CONTROLS = ["expired.badssl.com", "untrusted-root.badssl.com"]
# Served with an emSign chain (canary/emudhra_chain.pem was captured from it).
EMUDHRA_HOST = "www.internet2.edu"
# Inside the fixture leaf's validity (2026-09-17 .. 2027-04-04): 2026-11-01Z.
FIXTURE_TIME = 1793491200
TIMEOUT = 20

results = []  # (name, status, message, output)


def record(name, status, message, output=""):
    results.append((name, status, message, output))
    print("%-7s %s: %s" % (status, name, message), flush=True)


def run(cmd, **kw):
    try:
        p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=TIMEOUT * 3,
                           universal_newlines=True, **kw)
        return p.returncode, p.stdout
    except subprocess.TimeoutExpired as e:
        return -1, "timeout: %s" % (e.output or "")
    except OSError as e:
        return -2, str(e)


def retried(check):
    """Runs check() -> (status, message, output), again once on NETERR."""
    r = check()
    if r[0] == "NETERR":
        time.sleep(2)
        r = check()
    return r


# ---- trust store ---------------------------------------------------------

def pem_certs(text):
    return re.findall(r"-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----", text, re.S)


def fingerprint(pem):
    import hashlib
    return hashlib.sha256(ssl.PEM_cert_to_DER_cert(pem)).hexdigest()


def subject(pem):
    _, out = run(["openssl", "x509", "-noout", "-subject", "-nameopt", "RFC2253"], input=pem)
    return out.strip().replace("subject=", "", 1)


def bundle_fps(path):
    with open(path) as f:
        return {fingerprint(p): p for p in pem_certs(f.read())}


def capath_fps(path):
    fps = {}
    for name in sorted(os.listdir(path)):
        if re.match(r"^[0-9a-f]{8}\.[0-9]+$", name):
            with open(os.path.join(path, name)) as f:
                for p in pem_certs(f.read()):
                    fps[fingerprint(p)] = p
    return fps


def read_fps(path):
    """{fingerprint: subject} from a `<sha256> <subject>` file."""
    out = {}
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                fp, _, subj = line.partition(" ")
                out[fp] = subj
    return out


def release():
    with open("/etc/os-release") as f:
        m = re.search(r'^VERSION_ID="?([^"\n]*)', f.read(), re.M)
    return m.group(1) if m else "unknown"


def is_emudhra(subj):
    return bool(re.search(r"emsign|emudhra", subj, re.I))


def dump():
    """Prints the store as canary/roots/<release>.txt and its eMudhra roots."""
    fps = bundle_fps(BUNDLE)
    lines = sorted("%s %s" % (fp, subject(p)) for fp, p in fps.items())
    print("# canary/roots/%s.txt (%d certs)" % (release(), len(lines)))
    print("=== BEGIN ROOTS")
    print("\n".join(lines))
    print("=== END ROOTS")
    print("=== BEGIN EMUDHRA")
    print("\n".join(l for l in lines if is_emudhra(l.split(" ", 1)[1])))
    print("=== END EMUDHRA")
    capath = capath_fps(CAPATH)
    print("CApath %d certs, bundle %d; equal: %s" % (len(capath), len(fps), set(capath) == set(fps)))


def diff_text(want, have, names):
    missing = sorted(set(want) - set(have))
    added = sorted(set(have) - set(want))
    parts = ["missing %s %s" % (fp[:16], names.get(fp, "")) for fp in missing]
    parts += ["added %s %s" % (fp[:16], names.get(fp, "")) for fp in added]
    return missing, added, "\n".join(parts)


def check_integrity(expect, ca):
    rel = release()
    roots_file = os.path.join(HERE, "roots", rel + ".txt")
    if not os.path.exists(roots_file):
        record("trust_store/baseline", "FAIL", "no canary/roots/%s.txt for this release" % rel)
        return
    baseline = read_fps(roots_file)
    emudhra = read_fps(os.path.join(HERE, "emudhra.txt"))
    want = dict(baseline)
    if expect == "distrusted":
        for fp in emudhra:
            want.pop(fp, None)
    for name, have_p in (("bundle", bundle_fps(ca["file"])), ("capath", capath_fps(ca["dir"]))):
        names = dict(baseline)
        names.update({fp: subject(p) for fp, p in have_p.items() if fp not in names})
        missing, added, text = diff_text(want, have_p, names)
        label = "trust_store/%s_vs_%s" % (name, "baseline" if expect == "trusted" else "baseline_minus_emudhra")
        if missing or added:
            record(label, "FAIL", "%d missing, %d added (want %d, have %d)" % (
                len(missing), len(added), len(want), len(have_p)), text)
        else:
            record(label, "PASS", "%d certs match canary/roots/%s.txt%s" % (
                len(want), rel, " minus emudhra.txt" if expect == "distrusted" else ""))
    present = [fp for fp in emudhra if fp in bundle_fps(ca["file"])]
    record("trust_store/emudhra_roots_present", "PASS",
           "%d of %d eMudhra roots in bundle (informational)" % (len(present), len(emudhra)))


def check_fixture(expect, ca):
    """Verifies the checked-in eMudhra-issued chain offline at a fixed time."""
    chain = os.path.join(HERE, "emudhra_chain.pem")
    with open(chain) as f:
        certs = pem_certs(f.read())
    tmp = tempfile.mkdtemp()
    leaf, inter = os.path.join(tmp, "leaf.pem"), os.path.join(tmp, "inter.pem")
    with open(leaf, "w") as f:
        f.write(certs[0] + "\n")
    with open(inter, "w") as f:
        f.write("\n".join(certs[1:]) + "\n")
    # -no-CAstore: OpenSSL 3's default store is /etc/ssl/certs too.
    for name, flags in (("bundle", ["-CAfile", ca["file"], "-no-CApath", "-no-CAstore"]),
                        ("capath", ["-CApath", ca["dir"], "-no-CAfile", "-no-CAstore"])):
        code, out = run(["openssl", "verify", "-attime", str(FIXTURE_TIME), "-purpose", "sslserver"] + flags +
                        ["-untrusted", inter, leaf])
        label = "emudhra_fixture/%s" % name
        ok = code == 0 and ": OK" in out
        untrusted = re.search(r"error (2|20|19) at", out)  # unable to get (local) issuer / self-signed in chain
        if expect == "trusted":
            if ok:
                record(label, "PASS", "eMudhra chain verifies", out)
            else:
                record(label, "FAIL", "eMudhra chain should verify on a baseline: " + out.strip().splitlines()[-1], out)
        elif ok:
            record(label, "FAIL", "eMudhra chain still verifies (root or a cross-sign still trusted)", out)
        elif untrusted:
            record(label, "PASS", "eMudhra chain rejected: untrusted issuer", out)
        else:
            record(label, "FAIL", "eMudhra chain rejected for another reason", out)
    shutil.rmtree(tmp)


# ---- online --------------------------------------------------------------

NET_PY = (socket.gaierror, socket.timeout, ConnectionError, TimeoutError)


def py_check(host, ca):
    def check():
        ctx = (ssl.create_default_context(cafile=ca["file"], capath=ca["dir"]) if ca.get("override")
               else ssl.create_default_context())
        try:
            with socket.create_connection((host, 443), timeout=TIMEOUT) as s:
                with ctx.wrap_socket(s, server_hostname=host) as t:
                    return "OK", "verified, %s" % t.version(), ""
        except ssl.SSLCertVerificationError as e:
            return "CERT", "cert verify error: %s" % e.verify_message, str(e)
        except ssl.SSLError as e:
            return "TLS", "TLS error: %s" % e, str(e)
        except NET_PY as e:
            return "NETERR", "network: %r" % e, ""
        except OSError as e:
            return "NETERR", "network: %r" % e, ""
    return retried(check)


CURL_NET = {5: "proxy", 6: "dns", 7: "connect", 28: "timeout", 52: "empty reply", 55: "send", 56: "recv"}
CURL_CERT = {60: "peer cert verify", 77: "CA file", 51: "hostname", 58: "client cert", 83: "issuer"}


def curl_check(url, ca, extra=()):
    def check():
        flags = ["--cacert", ca["file"], "--capath", ca["dir"]] if ca.get("override") else []
        code, out = run(["curl", "-sS", "-o", "/dev/null", "--max-time", str(TIMEOUT), "-w",
                         "%{http_code} %{url_effective}\n"] + list(extra) + flags + [url])
        if code == 0:
            return "OK", "verified, " + out.strip().splitlines()[-1].split("?")[0], out
        if code in CURL_CERT:
            return "CERT", "curl %d (%s): %s" % (code, CURL_CERT[code], out.strip()), out
        if code in CURL_NET or code < 0:
            return "NETERR", "curl %d (%s): %s" % (code, CURL_NET.get(code, "timeout"), out.strip()), out
        return "TLS", "curl %d: %s" % (code, out.strip()), out
    return retried(check)


def openssl_check(host, ca):
    def check():
        flags = ["-CAfile", ca["file"], "-CApath", ca["dir"], "-no-CAstore"] if ca.get("override") else []
        code, out = run(["openssl", "s_client", "-connect", host + ":443", "-servername", host,
                         "-verify_return_error", "-verify_hostname", host] + flags, input="")
        m = re.search(r"Verify return code: (\d+) \(([^)]*)\)", out)
        if code == 0 and m and m.group(1) == "0":
            return "OK", "verified", out[-2000:]
        err = re.search(r"verify error:num=(\d+):(.*)", out)
        if err or (m and m.group(1) != "0"):
            return "CERT", "verify error %s" % ((err and err.group(0)) or m.group(0)), out[-2000:]
        if re.search(r"(?i)connect:errno|BIO_connect|BIO_lookup|Name or service not known|"
                     r"Connection refused|timed out|getaddrinfo|Network is unreachable", out) or code < 0:
            return "NETERR", "network: " + out.strip().splitlines()[-1] if out.strip() else "network", out[-2000:]
        return "TLS", "openssl exit %d" % code, out[-2000:]
    return retried(check)


def git_check(ca):
    def check():
        env = dict(os.environ, GIT_TERMINAL_PROMPT="0")
        if ca.get("override"):
            env["GIT_SSL_CAINFO"] = ca["file"]
            env["GIT_SSL_CAPATH"] = ca["dir"]
        code, out = run(["git", "-c", "http.lowSpeedTime=%d" % TIMEOUT, "ls-remote", GIT_REPO, "HEAD"], env=env)
        if code == 0 and re.match(r"^[0-9a-f]{40}\s+HEAD", out):
            return "OK", "ls-remote HEAD " + out[:12], out
        if re.search(r"SSL certificate problem|server certificate verification failed|certificate verify", out):
            return "CERT", out.strip().splitlines()[-1], out
        if re.search(r"(?i)could not resolve|failed to connect|timed out|connection refused|unreachable", out):
            return "NETERR", out.strip().splitlines()[-1], out
        return "TLS", "git exit %d: %s" % (code, out.strip()[-300:]), out
    return retried(check)


def expect_ok(name, r):
    status, msg, out = r
    record(name, {"OK": "PASS", "NETERR": "NETERR"}.get(status, "FAIL"), msg, out)


def expect_cert_error(name, r):
    status, msg, out = r
    if status == "CERT":
        record(name, "PASS", "rejected as expected: " + msg, out)
    elif status == "NETERR":
        record(name, "NETERR", msg, out)
    else:
        record(name, "FAIL", "should fail certificate verification, got %s: %s" % (status, msg), out)


# ---- main ----------------------------------------------------------------

def simulated_store(tmp):
    """A copy of the system store without the eMudhra roots: a stand-in for a
    candidate image (CANARY_SIMULATE_DISTRUST=1)."""
    emudhra = read_fps(os.path.join(HERE, "emudhra.txt"))
    keep = [p for fp, p in bundle_fps(BUNDLE).items() if fp not in emudhra]
    d = os.path.join(tmp, "certs")
    os.mkdir(d)
    for i, p in enumerate(keep):
        with open(os.path.join(d, "c%03d.pem" % i), "w") as f:
            f.write(p + "\n")
    code, out = run(["openssl", "rehash", d])
    if code != 0:
        sys.exit("openssl rehash: " + out)
    f = os.path.join(tmp, "ca-certificates.crt")
    with open(f, "w") as out_f:
        out_f.write("\n".join(keep) + "\n")
    return {"file": f, "dir": d, "override": True}


def write_junit(path):
    fails = sum(r[1] == "FAIL" for r in results)
    errors = sum(r[1] == "NETERR" for r in results)
    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<testsuites><testsuite name="tls_probe" tests="%d" failures="%d" errors="%d">' % (
                 len(results), fails, errors)]
    for name, status, msg, out in results:
        lines.append('<testcase classname="tls_probe" name=%s>' % quoteattr(name))
        if status == "FAIL":
            lines.append('<failure message=%s>%s</failure>' % (quoteattr(msg), escape(out or msg)))
        elif status == "NETERR":
            lines.append('<error type="network" message=%s>%s</error>' % (quoteattr(msg), escape(out or msg)))
        lines.append('<system-out>%s</system-out></testcase>' % escape("%s: %s\n%s" % (status, msg, out)))
    lines.append("</testsuite></testsuites>")
    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")


def main():
    if os.environ.get("CANARY_DUMP") == "1":
        dump()
        return 0
    expect = os.environ.get("CANARY_EXPECT", "trusted")
    if expect not in ("trusted", "distrusted"):
        sys.exit("CANARY_EXPECT must be trusted or distrusted, not %r" % expect)
    print("tls_probe: Ubuntu %s, CANARY_EXPECT=%s, host %s" % (release(), expect, socket.gethostname()))

    missing = [t for t in TOOLS if not shutil.which(t)]
    record("tools", "FAIL" if missing else "PASS",
           "missing: " + " ".join(missing) if missing else "found " + " ".join(shutil.which(t) for t in TOOLS))
    if missing:
        write_junit(os.environ.get("XML_OUTPUT_FILE", "/dev/null"))
        return 1

    tmp = tempfile.mkdtemp()
    ca = {"file": BUNDLE, "dir": CAPATH}
    if os.environ.get("CANARY_SIMULATE_DISTRUST") == "1":
        ca = simulated_store(tmp)
        print("SIMULATED candidate: store copy without emudhra.txt roots at %s" % tmp)

    check_integrity(expect, ca)
    check_fixture(expect, ca)
    for host in HOSTS:
        expect_ok("host/%s/python" % host, py_check(host, ca))
        expect_ok("host/%s/curl" % host, curl_check("https://%s/" % host, ca))
        expect_ok("host/%s/openssl" % host, openssl_check(host, ca))
    expect_ok("git_ls_remote", git_check(ca))
    expect_ok("github_release_asset", curl_check(RELEASE_ASSET, ca, ["-fL", "-r", "0-1023"]))
    for host in CONTROLS:
        expect_cert_error("control/%s/python" % host, py_check(host, ca))
        expect_cert_error("control/%s/curl" % host, curl_check("https://%s/" % host, ca))
    status, msg, _ = py_check(EMUDHRA_HOST, ca)
    record("emudhra_online/%s" % EMUDHRA_HOST, "PASS", "informational: %s: %s" % (status, msg))
    shutil.rmtree(tmp)

    host_results = [r for r in results if r[0].startswith("host/")]
    if host_results and all(r[1] == "NETERR" for r in host_results):
        record("connectivity", "FAIL", "every host check failed on the network; nothing verified")

    write_junit(os.environ.get("XML_OUTPUT_FILE", "/dev/null"))
    counts = {s: sum(r[1] == s for r in results) for s in ("PASS", "FAIL", "NETERR")}
    print("\n=== tls_probe summary (CANARY_EXPECT=%s%s): %d checks, %d PASS, %d FAIL, %d NETERR" % (
        expect, ", simulated" if ca.get("override") else "", len(results),
        counts["PASS"], counts["FAIL"], counts["NETERR"]))
    for name, status, msg, _ in results:
        if status != "PASS":
            print("  %-7s %s: %s" % (status, name, msg))
    return 1 if counts["FAIL"] else 0


if __name__ == "__main__":
    sys.exit(main())
