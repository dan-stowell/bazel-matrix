"""Extract one file from a Debian package.

A .deb is an ar archive whose data.tar.{xz,gz,zst} member holds the
filesystem tree. Python's stdlib has no ar reader, but the format is a
trivial sequence of 60-byte headers, and tarfile handles the inner
compression, so this stays dependency-free and hermetic.

Usage: extract_deb.py <deb> <member path inside data.tar> <output file>
"""
import io
import sys
import tarfile


def ar_members(data):
    if data[:8] != b"!<arch>\n":
        raise ValueError("not an ar archive")
    off = 8
    while off + 60 <= len(data):
        name = data[off:off + 16].decode().strip()
        size = int(data[off + 48:off + 58].decode().strip())
        body = data[off + 60:off + 60 + size]
        yield name, body
        off += 60 + size + (size % 2)


def main():
    deb, member, out = sys.argv[1:4]
    data = open(deb, "rb").read()
    for name, body in ar_members(data):
        if not name.startswith("data.tar"):
            continue
        with tarfile.open(fileobj=io.BytesIO(body)) as tar:
            src = tar.extractfile("./" + member.lstrip("/"))
            with open(out, "wb") as dst:
                dst.write(src.read())
            return
    raise SystemExit("no data.tar member found in {}".format(deb))


if __name__ == "__main__":
    main()
