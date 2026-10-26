"""Unit tests for tls_probe.py's output parsing (no network, no store)."""

import base64
import hashlib
import unittest

import tls_probe

URL = "https://release-assets.githubusercontent.com/x/y?sig=abc"


class CurlClassifyTest(unittest.TestCase):
    def test_http_429_after_curl_22_line(self):
        # curl -fL -sS: stderr first, then the -w line.
        out = "curl: (22) The requested URL returned error: 429\n429 %s\n" % URL
        self.assertEqual(tls_probe.curl_classify(22, out)[0], "NETERR")

    def test_http_503(self):
        out = "curl: (22) The requested URL returned error: 503\n503 %s\n" % URL
        self.assertEqual(tls_probe.curl_classify(22, out)[0], "NETERR")

    def test_http_404_fails(self):
        out = "curl: (22) The requested URL returned error: 404\n404 %s\n" % URL
        self.assertEqual(tls_probe.curl_classify(22, out)[0], "ERROR")

    def test_cert(self):
        out = "curl: (60) SSL certificate problem: certificate has expired\n000 https://expired.badssl.com/\n"
        self.assertEqual(tls_probe.curl_classify(60, out)[0], "CERT")

    def test_ca_file_setup_is_not_a_rejection(self):
        for code in (77, 58):
            self.assertEqual(tls_probe.curl_classify(code, "curl: (%d) x\n000 u\n" % code)[0], "ERROR")

    def test_network(self):
        self.assertEqual(tls_probe.curl_classify(6, "curl: (6) Could not resolve host\n")[0], "NETERR")
        self.assertEqual(tls_probe.curl_classify(35, "curl: (35) OpenSSL SSL_connect: reset\n")[0], "NETERR")
        self.assertEqual(tls_probe.curl_classify(-1, "timeout after 40s")[0], "NETERR")

    def test_ok_drops_query(self):
        status, msg = tls_probe.curl_classify(0, "206 %s\n" % URL)
        self.assertEqual(status, "OK")
        self.assertNotIn("sig=", msg)


class GitClassifyTest(unittest.TestCase):
    def test_cert_gnutls(self):
        out = ("fatal: unable to access 'https://expired.badssl.com/': server certificate verification "
               "failed. CAfile: none CRLfile: none\n")
        self.assertEqual(tls_probe.git_classify(128, out)[0], "CERT")

    def test_timeout(self):
        self.assertEqual(tls_probe.git_classify(-1, "timeout after 40s")[0], "NETERR")

    def test_tls_only(self):
        out = "fatal: repository 'https://www.internet2.edu/' not found\n"
        self.assertEqual(tls_probe.git_classify(128, out, tls_only=True)[0], "OK")
        self.assertEqual(tls_probe.git_classify(128, out)[0], "ERROR")


class CertsInTest(unittest.TestCase):
    def test_trusted_certificate_key_includes_trust(self):
        cert = bytes([0x30, 0x03, 0x02, 0x01, 0x05])  # any DER TLV
        aux = bytes([0x30, 0x02, 0x05, 0x00])

        def pem(kind, der):
            return "-----BEGIN %s-----\n%s\n-----END %s-----\n" % (kind, base64.b64encode(der).decode(), kind)

        plain = tls_probe.certs_in(pem("CERTIFICATE", cert))
        trusted = tls_probe.certs_in(pem("TRUSTED CERTIFICATE", cert + aux))
        fp = hashlib.sha256(cert).hexdigest()
        self.assertEqual(plain[0][0], fp)
        self.assertTrue(trusted[0][0].startswith(fp + "+trust:"))


class CurlrcTest(unittest.TestCase):
    def test_bad_directives(self):
        for line in ("insecure", "--insecure", "-k", "cacert = /x", "capath /x", "proxy-insecure"):
            self.assertRegex(line, tls_probe.CURLRC_BAD)
        self.assertNotRegex("user-agent = x", tls_probe.CURLRC_BAD)


if __name__ == "__main__":
    unittest.main()
