#!/bin/bash
# Runs canary/tls_probe.py with the image's own python3 (not a hermetic one):
# the point is to test the image. See canary/README.md.
if [[ ! -x /usr/bin/python3 ]]; then
  echo "FAIL tools: /usr/bin/python3 missing on this image"
  [[ -n "${XML_OUTPUT_FILE:-}" ]] && cat >"$XML_OUTPUT_FILE" <<'XML'
<?xml version="1.0" encoding="UTF-8"?>
<testsuites><testsuite name="tls_probe" tests="1" failures="1"><testcase classname="tls_probe" name="tools"><failure message="/usr/bin/python3 missing"/></testcase></testsuite></testsuites>
XML
  exit 1
fi
exec /usr/bin/python3 -I "$(dirname "$0")/tls_probe.py"
