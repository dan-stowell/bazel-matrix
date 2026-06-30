#!/usr/bin/env python3
import os
import sys
import zipfile


def _entries(paths, recursive, junk_paths):
    for path in paths:
        if os.path.isdir(path):
            if not recursive:
                continue
            for root, _, files in os.walk(path):
                for name in files:
                    src = os.path.join(root, name)
                    arcname = os.path.basename(src) if junk_paths else src
                    yield src, arcname.lstrip("./")
        elif os.path.isfile(path):
            arcname = os.path.basename(path) if junk_paths else path
            yield path, arcname.lstrip("./")


def main(argv):
    options = []
    while argv and argv[0].startswith("-"):
        options.append(argv.pop(0))
    if not argv:
        print("zip.py: missing archive path", file=sys.stderr)
        return 2

    archive = argv.pop(0)
    option_text = "".join(options)
    recursive = "r" in option_text
    junk_paths = "j" in option_text
    compression = zipfile.ZIP_STORED if "0" in option_text else zipfile.ZIP_DEFLATED

    paths = list(argv)
    if "@" in option_text or "@" in paths:
        paths = [path for path in paths if path != "@"]
        paths.extend(line.strip() for line in sys.stdin if line.strip())

    seen = set()
    with zipfile.ZipFile(archive, "w", compression=compression) as zf:
        for src, arcname in sorted(_entries(paths, recursive, junk_paths), key=lambda item: item[1]):
            if arcname in seen:
                continue
            seen.add(arcname)
            info = zipfile.ZipInfo(arcname)
            info.date_time = (1980, 1, 1, 0, 0, 0)
            info.compress_type = compression
            with open(src, "rb") as f:
                zf.writestr(info, f.read())
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
