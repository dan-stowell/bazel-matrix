"""Checks the system CA store of the image this runs on, and TLS with it.

Run by canary/tls_probe.sh with the image's own /usr/bin/python3 (stdlib
only). Each check is one JUnit testcase in $XML_OUTPUT_FILE; the log gets a
summary. CANARY_EXPECT=trusted (default) expects the baseline store;
distrusted expects the baseline minus the eMudhra/emSign roots. See
canary/README.md.

Results: PASS; FAIL; NETERR (DNS, connect, timeout or a transient TLS/HTTP
error after one retry: says nothing about the store, but also fails the
test, as every check is needed for evidence either way).
"""

import base64
import concurrent.futures
import hashlib
import os
import platform
import pwd
import re
import shutil
import signal
import socket
import ssl
import subprocess
import sys
import tempfile
import threading
import time
from xml.sax.saxutils import escape, quoteattr

HERE = os.path.dirname(os.path.abspath(__file__))
BUNDLE = "/etc/ssl/certs/ca-certificates.crt"
CAPATH = "/etc/ssl/certs"
TOOLS = ["curl", "openssl", "git"]
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
# Serves the emSign chain canary/emudhra_chain.pem was captured from.
EMUDHRA_HOST = "www.internet2.edu"
# Inside the fixture leaf's validity (2026-09-17 .. 2027-04-04): 2026-11-01Z.
FIXTURE_TIME = 1793491200
# Variables that redirect or disable verification for some client.
CA_ENV = ["SSL_CERT_FILE", "SSL_CERT_DIR", "CURL_CA_BUNDLE", "REQUESTS_CA_BUNDLE", "GIT_SSL_NO_VERIFY",
          "GIT_SSL_CAINFO", "GIT_SSL_CAPATH", "OPENSSL_CONF", "SSLKEYLOGFILE"]
TIMEOUT = 20  # per network operation
DEADLINE = 200  # seconds for the whole probe; the test (size medium) gets 300
START = time.time()

results = []  # (name, status, message, output)
lock = threading.RLock()  # also taken by the signal handler
xml_path = os.environ.get("XML_OUTPUT_FILE", "/dev/null")
curl_sim_flags = []  # set by simulate()


def record(name, status, message, output=""):
    with lock:
        results.append((name, status, message, output))
        print("%-7s %s: %s" % (status, name, message), flush=True)


def run(cmd, timeout=TIMEOUT * 2, **kw):
    """(exit code, output); -1 on timeout, -2 when it can't start."""
    try:
        p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout,
                           universal_newlines=True, **kw)
        return p.returncode, p.stdout
    except subprocess.TimeoutExpired as e:
        return -1, "timeout after %ds" % timeout
    except OSError as e:
        return -2, str(e)


def last_line(out):
    lines = out.strip().splitlines()
    return lines[-1] if lines else ""


# ---- trust store ---------------------------------------------------------

PEM_RE = re.compile(r"-----BEGIN (TRUSTED )?CERTIFICATE-----(.*?)-----END (?:TRUSTED )?CERTIFICATE-----", re.S)


def der_len(der):
    """Length of the first DER TLV (the certificate in a TRUSTED CERTIFICATE,
    which is the certificate followed by OpenSSL's trust settings)."""
    n = der[1]
    if n < 0x80:
        return 2 + n
    k = n & 0x7F
    return 2 + k + int.from_bytes(der[2:2 + k], "big")


def certs_in(text):
    """[(key, pem)]: key is the SHA-256 of the certificate's DER, plus
    "+trust:<sha256 of the trust settings>" for a TRUSTED CERTIFICATE, so
    extra trust settings show up as a different cert."""
    out = []
    for m in PEM_RE.finditer(text):
        der = base64.b64decode("".join(m.group(2).split()))
        n = der_len(der)
        key = hashlib.sha256(der[:n]).hexdigest()
        if m.group(1):
            key += "+trust:" + hashlib.sha256(der[n:]).hexdigest()[:16]
        out.append((key, m.group(0)))
    return out


def subject(pem):
    _, out = run(["openssl", "x509", "-noout", "-subject", "-nameopt", "RFC2253"], input=pem)
    return out.strip().replace("subject=", "", 1)


def bundle_certs(path):
    with open(path) as f:
        return dict(certs_in(f.read()))


def capath_name(name):
    """"ok" for a hashed name (`1234abcd.0`), "noncanonical" for one OpenSSL
    wouldn't look up (`1234abcd.00`), else None."""
    if re.match(r"^[0-9a-f]{8}\.(0|[1-9][0-9]*)$", name):
        return "ok"
    if re.match(r"^[0-9a-f]{8}\.[0-9]+$", name):
        return "noncanonical"
    return None


def capath_certs(path):
    """({key: pem}, [problems]): problems are hashed names whose cert's
    subject hash differs (per one `openssl rehash` of a copy), files with
    other than one cert, and gaps in the collision indices."""
    certs, problems, indices, names = {}, [], {}, []
    tmp = tempfile.mkdtemp()
    for name in sorted(os.listdir(path)):
        kind = capath_name(name)
        if kind == "noncanonical":
            problems.append("%s: not a canonical hash.N name" % name)
        if kind != "ok":
            continue
        indices.setdefault(name[:8], []).append(int(name[9:]))
        with open(os.path.join(path, name)) as f:
            found = certs_in(f.read())
        if len(found) != 1:
            problems.append("%s: %d certs" % (name, len(found)))
        for key, pem in found:
            certs[key] = pem
        if found:
            with open(os.path.join(tmp, "f%d.pem" % len(names)), "w") as f:
                f.write(found[0][1] + "\n")
            names.append(name)
    code, out = run(["openssl", "rehash", "-v", tmp])
    shutil.rmtree(tmp)
    linked = dict(re.findall(r"^link f(\d+)\.pem -> ([0-9a-f]{8})\.\d+$", out, re.M))
    for i, name in enumerate(names):
        h = linked.get(str(i))
        if h is None:
            problems.append("%s: openssl rehash didn't link it (duplicate?)" % name)
        elif h != name[:8]:
            problems.append("%s: subject hash is %s" % (name, h))
    if code != 0:
        problems.append("openssl rehash exit %d: %s" % (code, last_line(out)))
    for h, idx in sorted(indices.items()):
        if sorted(idx) != list(range(len(idx))):
            problems.append("%s: collision indices %s not 0..n-1" % (h, sorted(idx)))
    return certs, problems


def read_fps(path):
    """{key: subject} from a `<key> <subject>` file."""
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


def dump():
    """Prints the store as canary/roots/<release>.txt and its eMudhra roots."""
    certs = bundle_certs(BUNDLE)
    lines = sorted("%s %s" % (fp, subject(p)) for fp, p in certs.items())
    print("# canary/roots/%s.txt (%d certs)" % (release(), len(lines)))
    print("=== BEGIN ROOTS")
    print("\n".join(lines))
    print("=== END ROOTS")
    print("=== BEGIN EMUDHRA")
    print("\n".join(l for l in lines if re.search(r"emsign|emudhra", l.split(" ", 1)[1], re.I)))
    print("=== END EMUDHRA")
    capath, problems = capath_certs(CAPATH)
    print("CApath %d certs, bundle %d; equal: %s; problems: %s" % (
        len(capath), len(certs), set(capath) == set(certs), problems))


def check_integrity(expect, store):
    """trusted: the bundle is exactly the baseline. distrusted: the diff vs
    the baseline is informational (candidates may ship a newer
    ca-certificates); emudhra/store_absent is what counts."""
    rel = release()
    roots_file = os.path.join(HERE, "roots", rel + ".txt")
    bundle = bundle_certs(store["file"])
    capath, problems = capath_certs(store["dir"])
    if expect == "distrusted":
        check_emudhra_absent(bundle, capath)
    if not os.path.exists(roots_file):
        record("trust_store/bundle", "FAIL" if expect == "trusted" else "PASS",
               "no canary/roots/%s.txt for this release" % rel)
    else:
        baseline = read_fps(roots_file)
        names = dict(baseline)
        names.update({fp: subject(p) for fp, p in bundle.items() if fp not in names})
        missing, added = sorted(set(baseline) - set(bundle)), sorted(set(bundle) - set(baseline))
        text = "\n".join(["removed %s %s" % (fp, names.get(fp, "")) for fp in missing] +
                         ["added %s %s" % (fp, names.get(fp, "")) for fp in added])
        what = "canary/roots/%s.txt" % rel
        if not (missing or added):
            record("trust_store/bundle", "PASS", "%d certs match %s" % (len(baseline), what))
        elif expect == "trusted":
            record("trust_store/bundle", "FAIL", "vs %s: %d missing, %d added (want %d, have %d)" % (
                what, len(missing), len(added), len(baseline), len(bundle)), text)
        else:
            record("trust_store/bundle", "PASS", "informational: vs %s %d removed, %d added (%d -> %d): %s" % (
                what, len(missing), len(added), len(baseline), len(bundle),
                "; ".join(l.split(" ", 1)[0] + " " + cn(l.split(" ", 2)[2]) for l in text.splitlines())), text)

    only_c, only_b = sorted(set(capath) - set(bundle)), sorted(set(bundle) - set(capath))
    problems += ["only in CApath: %s" % fp for fp in only_c] + ["only in bundle: %s" % fp for fp in only_b]
    if problems:
        record("trust_store/capath", "FAIL", "%d problems; first: %s" % (len(problems), problems[0]),
               "\n".join(problems))
    else:
        record("trust_store/capath", "PASS", "%d hashed certs, names and indices valid, same set as the bundle"
               % len(capath))


def cn(subj):
    m = re.search(r"CN=([^,]*)", subj)
    return m.group(1) if m else subj


EMUDHRA_RE = re.compile(r"O ?= ?eMudhra|CN ?= ?[^,\n]*emSign")


def mentions_emudhra(pem):
    """Cheap prefilter: the DER has "eMudhra" or "emSign" somewhere."""
    der = base64.b64decode("".join(PEM_RE.search(pem).group(2).split()))
    return b"eMudhra" in der or b"emSign" in der


def check_emudhra_absent(bundle, capath):
    """No eMudhra root in bundle or CApath: by emudhra.txt fingerprint, or by
    subject or issuer (O=eMudhra..., CN=emSign...), so a re-issued one counts."""
    known = read_fps(os.path.join(HERE, "emudhra.txt"))
    found = []
    for where, certs in (("bundle", bundle), ("capath", capath)):
        for fp, pem in sorted(certs.items()):
            hit = fp.split("+")[0] in known
            if hit or mentions_emudhra(pem):
                _, names = run(["openssl", "x509", "-noout", "-subject", "-issuer"], input=pem)
                if hit or EMUDHRA_RE.search(names):
                    found.append("%s: %s %s" % (where, fp[:16], " ".join(names.split())))
    if found:
        record("emudhra/store_absent", "FAIL", "%d eMudhra certs still trusted: %s" % (
            len(found), "; ".join(found)), "\n".join(found))
    else:
        record("emudhra/store_absent", "PASS", "no eMudhra/emSign root in bundle (%d) or CApath (%d)" % (
            len(bundle), len(capath)))


def check_fixture(expect, store):
    """Verifies the checked-in eMudhra-issued chain offline at a fixed time.
    The chain is leaf <- OVG2C <- emSign Root TLS CA - G1 (cross-signed by
    emSign Root CA - G1); without the eMudhra roots, OpenSSL must stop at
    depth 2 for want of its issuer (error 20, unable to get local issuer)."""
    with open(os.path.join(HERE, "emudhra_chain.pem")) as f:
        certs = [p for _, p in certs_in(f.read())]
    tmp = tempfile.mkdtemp()
    leaf, inter = os.path.join(tmp, "leaf.pem"), os.path.join(tmp, "inter.pem")
    with open(leaf, "w") as f:
        f.write(certs[0] + "\n")
    with open(inter, "w") as f:
        f.write("\n".join(certs[1:]) + "\n")
    # -no-CAstore: OpenSSL 3's default store is /etc/ssl/certs too.
    code, out = run(["openssl", "verify", "-attime", str(FIXTURE_TIME), "-purpose", "sslserver",
                     "-CAfile", store["file"], "-no-CApath", "-no-CAstore", "-untrusted", inter, leaf])
    shutil.rmtree(tmp)
    print("openssl verify: " + " | ".join(out.strip().splitlines()))
    ok = code == 0 and ": OK" in out
    name = "emudhra/fixture"
    if expect == "trusted":
        if ok:
            record(name, "PASS", "eMudhra chain verifies", out)
        else:
            record(name, "FAIL", "eMudhra chain should verify on a baseline: " + last_line(out), out)
        return
    expected = (re.search(r"CN ?= ?emSign Root TLS CA - G1\s*\n.*error 20 at 2 depth lookup", out) and
                "emSign Root CA - G1" in subject_issuer(certs[2]))
    if ok:
        record(name, "FAIL", "eMudhra chain still verifies (root or a cross-sign still trusted)", out)
    elif expected:
        record(name, "PASS", "rejected: error 20 at depth 2, issuer emSign Root CA - G1 not trusted", out)
    else:
        record(name, "FAIL", "rejected, but not as expected (error 20 at depth 2): " + last_line(out), out)


def subject_issuer(pem):
    _, out = run(["openssl", "x509", "-noout", "-issuer"], input=pem)
    return out


# ---- environment -----------------------------------------------------------

# config/-K: another file, which isn't followed (it fails instead).
CURLRC_BAD = r"(?im)^\s*(-k\b|-K\b|(--)?(proxy-)?(insecure|cacert|capath|ca-native|ssl-no-revoke|config)\b)"


def curlrc_candidates():
    """The places curl looks for its config file, as in curl's
    tool_findfile.c: $CURL_HOME, $XDG_CONFIG_HOME, $HOME, the passwd home,
    each for .curlrc (XDG also curlrc)."""
    dirs = [os.environ.get("CURL_HOME"), os.environ.get("XDG_CONFIG_HOME"), os.environ.get("HOME"),
            pwd.getpwuid(os.getuid()).pw_dir]
    out = []
    for d in dirs:
        if d:
            out.append(os.path.join(d, ".curlrc"))
    for d in (os.environ.get("XDG_CONFIG_HOME"), os.path.join(os.environ.get("HOME", "/"), ".config")):
        if d:
            out += [os.path.join(d, "curlrc"), os.path.join(d, ".curlrc")]
    return sorted(set(out))


def cnf_line(line):
    """("include", path), ("bad", line) for a verify-location directive
    (also prefixed, as in `1.VerifyCAFile`), or (None, None)."""
    inc = re.match(r"\s*\.include\s*=?\s*(\S+)", line)
    if inc:
        return "include", inc.group(1).strip("\"'")
    if re.match(r"(?i)\s*([^\s=]*\.)?((Verify|Chain|Request)CA(File|Path|Store)|VerifyMode)\s*=", line):
        return "bad", line.strip()
    return None, None


def scan_openssl_cnf(path, base, seen):
    """Verify-location directives in an openssl.cnf and the files and
    directories it .includes."""
    path = os.path.join(base, path)
    if path in seen:
        return []
    seen.add(path)
    if os.path.isdir(path):
        return sum((scan_openssl_cnf(os.path.join(path, n), base, seen)
                    for n in sorted(os.listdir(path)) if n.endswith((".cnf", ".conf"))), [])
    problems = []
    try:
        with open(path) as f:
            for line in f:
                kind, value = cnf_line(line)
                if kind == "include":
                    problems += scan_openssl_cnf(value, os.environ.get("OPENSSL_CONF_INCLUDE", base), seen)
                elif kind == "bad":
                    problems.append("%s: %s" % (path, value))
    except OSError as e:
        problems.append("%s: %s" % (path, e))
    return problems


def check_env():
    """Fails when the environment or config redirects or disables
    verification, so the checks below test the store clients really load."""
    problems = []
    for v in CA_ENV:
        if v in os.environ:
            problems.append("env %s=%s" % (v, os.environ[v]))
    paths = ssl.get_default_verify_paths()
    if os.path.realpath(paths.openssl_capath) != CAPATH:
        problems.append("python ssl default capath %s -> %s" % (paths.openssl_capath,
                                                                os.path.realpath(paths.openssl_capath)))
    if os.path.realpath(paths.openssl_cafile) != BUNDLE and os.path.exists(paths.openssl_cafile):
        problems.append("python ssl default cafile %s -> %s" % (paths.openssl_cafile,
                                                                os.path.realpath(paths.openssl_cafile)))
    code, out = run(["git", "config", "--list", "--show-origin"])
    for line in out.splitlines():
        if re.search(r"(?i)\s(http\.(.*\.)?ssl(verify|cainfo|capath|backend)|url\..*\.insteadof)=", line):
            problems.append("git config: " + line)
    for p in curlrc_candidates():
        if os.path.isfile(p):
            with open(p, errors="replace") as f:
                text = f.read()
            if re.search(CURLRC_BAD, text):
                problems.append("%s: %s" % (p, " | ".join(l for l in text.splitlines() if re.search(CURLRC_BAD, l))))
            else:
                print("note: %s exists (curl runs with -q here)" % p)
    _, d = run(["openssl", "version", "-d"])
    m = re.search(r'"(.*)"', d)
    openssldir = m.group(1) if m else "/usr/lib/ssl"
    problems += scan_openssl_cnf(os.path.join(openssldir, "openssl.cnf"), openssldir, set())
    if problems:
        record("env", "FAIL", "%d settings redirect or disable verification; first: %s" % (
            len(problems), problems[0]), "\n".join(problems))
    else:
        record("env", "PASS", "no CA env vars, git or curl overrides; python default paths %s, %s" % (
            paths.openssl_cafile, paths.openssl_capath))


# ---- online --------------------------------------------------------------
# Each check returns (status, message, output), status one of OK, CERT
# (certificate rejected), NETERR, or ERROR (anything else: fails).

def retried(check):
    r = check()
    if r[0] == "NETERR":
        time.sleep(2)
        r = check()
    return r


def py_check(host):
    def check():
        ctx = ssl.create_default_context()
        try:
            with socket.create_connection((host, 443), timeout=TIMEOUT) as s:
                with ctx.wrap_socket(s, server_hostname=host) as t:
                    return "OK", "verified, %s" % t.version(), ""
        except ssl.SSLCertVerificationError as e:
            return "CERT", "cert verify error: %s" % e.verify_message, str(e)
        except (ssl.SSLEOFError, ssl.SSLZeroReturnError) as e:
            return "NETERR", "transient TLS: %r" % e, ""
        except ssl.SSLError as e:
            return "ERROR", "TLS error: %s" % e, str(e)
        except OSError as e:  # DNS, connect, reset, timeout
            return "NETERR", "network: %r" % e, ""
    return retried(check)


CURL_NET = {5: "proxy", 6: "dns", 7: "connect", 16: "http2", 28: "timeout", 35: "TLS connect",
            52: "empty reply", 55: "send", 56: "recv", 92: "http2 stream"}
CURL_CERT = {60: "peer cert verify", 51: "hostname", 83: "issuer"}


def curl_classify(code, out):
    """(status, message) for curl's exit code and output (stderr, then the
    `-w "%{http_code} %{url_effective}"` line)."""
    tail = re.sub(r"\?\S*", "", " ".join(out.split()))[:300]
    if code == 0:
        return "OK", "verified, " + tail
    if code in CURL_CERT:
        return "CERT", "curl %d (%s): %s" % (code, CURL_CERT[code], tail)
    if code in CURL_NET or code == -1:
        return "NETERR", "curl %d (%s): %s" % (code, CURL_NET.get(code, "timeout"), tail)
    http = re.search(r"(?m)^(\d{3}) \S+$", out)
    if code == 22 and http and (http.group(1) == "429" or http.group(1).startswith("5")):
        return "NETERR", "HTTP %s (server side): %s" % (http.group(1), tail)
    return "ERROR", "curl %d: %s" % (code, tail)  # incl. 77/58: CA/client cert setup


def curl_check(url, extra=()):
    def check():
        code, out = run(["curl", "-q", "-sS", "-o", "/dev/null", "--max-time", str(TIMEOUT), "-w",
                         "%{http_code} %{url_effective}\n"] + list(extra) + curl_sim_flags + [url])
        return curl_classify(code, out) + (out,)
    return retried(check)


def git_classify(code, out, tls_only=False):
    """(status, message) for `git ls-remote`; tls_only: any failure after the
    TLS handshake is OK (the URL is not a git repo)."""
    if code == 0:
        return "OK", "ls-remote OK " + out[:12]
    if re.search(r"(?i)SSL certificate problem|certificate verification failed|certificate verify|"
                 r"issuer certificate|self.signed|certificate has expired", out):
        return "CERT", last_line(out)
    if code == -1 or re.search(r"(?i)could not resolve|failed to connect|timed out|connection refused|"
                               r"unreachable|connection reset|gnutls_handshake\(\) failed|"
                               r"Operation too slow|HTTP/2 stream", out):
        return "NETERR", last_line(out)
    if tls_only and re.search(r"(?i)not found|not valid|HTTP \d{3}|repository|unexpected|bad line", out):
        return "OK", "TLS verified (then: %s)" % last_line(out)
    return "ERROR", "git exit %d: %s" % (code, last_line(out)[-300:])


def git_check(url, tls_only=False):
    def check():
        env = dict(os.environ, GIT_TERMINAL_PROMPT="0")
        code, out = run(["git", "-c", "http.lowSpeedLimit=1000", "-c", "http.lowSpeedTime=%d" % TIMEOUT,
                         "ls-remote", url, "HEAD"], env=env)
        return git_classify(code, out, tls_only) + (out,)
    return retried(check)


def expect(want):
    """A function recording a check's result against the wanted status."""
    def judge(name, r):
        status, msg, out = r
        if status == want:
            record(name, "PASS", msg if want == "OK" else "rejected as expected: " + msg, out)
        elif status == "NETERR":
            record(name, "NETERR", msg, out)
        else:
            record(name, "FAIL", "want %s, got %s: %s" % (want, status, msg), out)
    return judge


# ---- main ----------------------------------------------------------------

def simulate(tmp):
    """Points every client at a copy of the system store without the
    eMudhra roots: a stand-in for a candidate image."""
    emudhra = read_fps(os.path.join(HERE, "emudhra.txt"))
    keep = [p for fp, p in bundle_certs(BUNDLE).items() if fp not in emudhra]
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
    for v in ("SSL_CERT_FILE", "GIT_SSL_CAINFO"):
        os.environ[v] = f
    for v in ("SSL_CERT_DIR", "GIT_SSL_CAPATH"):
        os.environ[v] = d
    # curl takes one of CURL_CA_BUNDLE, SSL_CERT_DIR, SSL_CERT_FILE and keeps
    # its compiled-in default for the other of CA file and CA path, which
    # still trusts eMudhra: give it both explicitly.
    curl_sim_flags[:] = ["--cacert", f, "--capath", d]
    return {"file": f, "dir": d}


def write_junit():
    with lock:
        rs = list(results)
    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<testsuites><testsuite name="tls_probe" tests="%d" failures="%d" errors="%d">' % (
                 len(rs), sum(r[1] == "FAIL" for r in rs), sum(r[1] == "NETERR" for r in rs))]
    for name, status, msg, out in rs:
        lines.append('<testcase classname="tls_probe" name=%s>' % quoteattr(name))
        if status == "FAIL":
            lines.append('<failure message=%s>%s</failure>' % (quoteattr(msg), escape(out or msg)))
        elif status == "NETERR":
            lines.append('<error type="network" message=%s>%s</error>' % (quoteattr(msg), escape(out or msg)))
        lines.append('<system-out>%s</system-out></testcase>' % escape("%s: %s\n%s" % (status, msg, out)))
    lines.append("</testsuite></testsuites>")
    with open(xml_path, "w") as f:
        f.write("\n".join(lines) + "\n")


def finish(simulated):
    """Writes JUnit and the summary; the exit code."""
    write_junit()
    counts = {s: sum(r[1] == s for r in results) for s in ("PASS", "FAIL", "NETERR")}
    print("\n=== tls_probe summary (CANARY_EXPECT=%s%s): %d checks, %d PASS, %d FAIL, %d NETERR, %.0fs" % (
        os.environ.get("CANARY_EXPECT", "trusted"), ", simulated" if simulated else "", len(results),
        counts["PASS"], counts["FAIL"], counts["NETERR"], time.time() - START))
    for name, status, msg, _ in results:
        if status != "PASS":
            print("  %-7s %s: %s" % (status, name, msg))
    sys.stdout.flush()
    if counts["NETERR"] and not counts["FAIL"]:
        print("  (fails on network errors only: no evidence either way about the CA store)")
    return 1 if counts["FAIL"] or counts["NETERR"] else 0


def on_sigterm(signum, frame):
    what = "the probe's %ds deadline" % (DEADLINE + 20) if signum == signal.SIGALRM else "signal %d" % signum
    try:
        record("deadline", "FAIL", "stopped by %s before finishing" % what)
        finish(os.environ.get("CANARY_SIMULATE_DISTRUST") == "1")
    finally:
        os._exit(1)


def main():
    if os.environ.get("CANARY_DUMP") == "1":
        dump()
        return 0
    want = os.environ.get("CANARY_EXPECT", "trusted")
    if want not in ("trusted", "distrusted"):
        sys.exit("CANARY_EXPECT must be trusted or distrusted, not %r" % want)
    signal.signal(signal.SIGTERM, on_sigterm)
    signal.signal(signal.SIGALRM, on_sigterm)
    signal.alarm(DEADLINE + 20)  # backstop for setup and offline checks too
    print("tls_probe: Ubuntu %s, %s, CANARY_EXPECT=%s, host %s" % (
        release(), platform.machine(), want, socket.gethostname()))

    missing = [t for t in TOOLS if not shutil.which(t)]
    record("tools", "FAIL" if missing else "PASS",
           "missing: " + " ".join(missing) if missing else "found " + " ".join(shutil.which(t) for t in TOOLS))
    if missing:
        return finish(False)
    check_env()

    tmp = tempfile.mkdtemp()
    simulated = os.environ.get("CANARY_SIMULATE_DISTRUST") == "1"
    store = {"file": BUNDLE, "dir": CAPATH}
    if simulated:
        store = simulate(tmp)
        print("SIMULATED candidate: SSL_CERT_*, GIT_SSL_*, curl --cacert/--capath -> store without emudhra.txt at %s" % tmp)

    check_integrity(want, store)
    check_fixture(want, store)

    ok, cert = expect("OK"), expect("CERT")
    emudhra = ok if want == "trusted" else cert
    jobs = []  # (name, judge, check, args)
    for host in HOSTS:
        jobs.append(("host/%s/python" % host, ok, py_check, (host,)))
        jobs.append(("host/%s/curl" % host, ok, curl_check, ("https://%s/" % host,)))
    jobs.append(("git_ls_remote", ok, git_check, (GIT_REPO,)))
    jobs.append(("github_release_asset", ok, curl_check, (RELEASE_ASSET, ["-fL", "-r", "0-1023"])))
    for host in CONTROLS:
        jobs.append(("control/%s/python" % host, cert, py_check, (host,)))
        jobs.append(("control/%s/curl" % host, cert, curl_check, ("https://%s/" % host,)))
        jobs.append(("control/%s/git" % host, cert, git_check, ("https://%s/" % host,)))
    jobs.append(("emudhra/online/%s/python" % EMUDHRA_HOST, emudhra, py_check, (EMUDHRA_HOST,)))
    jobs.append(("emudhra/online/%s/curl" % EMUDHRA_HOST, emudhra, curl_check, ("https://%s/" % EMUDHRA_HOST,)))
    jobs.append(("emudhra/online/%s/git" % EMUDHRA_HOST, emudhra, git_check, ("https://%s/" % EMUDHRA_HOST, True)))

    pool = concurrent.futures.ThreadPoolExecutor(max_workers=8)
    futures = [pool.submit(check, *args) for _, _, check, args in jobs]
    concurrent.futures.wait(futures, timeout=max(1, DEADLINE - (time.time() - START)))
    for (name, judge, _, _), fut in zip(jobs, futures):
        if fut.done():
            judge(name, fut.result())
        else:
            record(name, "FAIL", "didn't finish within the probe's %ds deadline" % DEADLINE)
    pool.shutdown(wait=False, cancel_futures=True)
    shutil.rmtree(tmp, ignore_errors=True)
    code = finish(simulated)
    os._exit(code)  # don't wait for checks still running past the deadline


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        import traceback
        record("probe", "FAIL", "probe crashed", traceback.format_exc())
        write_junit()
        raise
