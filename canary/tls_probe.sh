#!/bin/bash
# Runs canary/tls_probe.py with the image's own python3 (not a hermetic one):
# the point is to test the image. See canary/README.md.
exec /usr/bin/python3 -I "$(dirname "$0")/tls_probe.py"
