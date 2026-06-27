# The MINIMG image: a minimal, *toolchain-free* base for hermetic museum builds.
#
# Unlike //runner/image (the front-door "ordinary CI machine"), this image ships
# NO C/C++ toolchain — no build-essential, no gcc/g++/make. Projects built in it
# carry the HERMETIC_LLVM overlay, which supplies clang/libc++/CRT over the BCR,
# so the compiler rides in with the build instead of the image. What remains are
# the generic build-time tools the non-toolchain heavyweights still shell out to
# (python3 → protobuf/rules_python, git → ortools, curl → grpc, zip → bazel) plus
# TLS roots. The inner Bazel binary is bind-mounted in by //tools/buildrunner.
#
# Built + loaded as the docker tag the MINIMG environment references:
#   docker build -f runner/image/minimal.Dockerfile -t museum-minimg:latest .
# (A rules_distroless-native, fully-pinned variant is the productization
# follow-up; this Dockerfile keeps the environment reproducible meanwhile.)
FROM debian:bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates python3 python-is-python3 git curl zip unzip xz-utils \
 && rm -rf /var/lib/apt/lists/* \
 && mkdir -p /work /home/runner && chmod 0777 /work /home/runner
# Deliberately NO build-essential: the hermetic LLVM toolchain provides the
# compiler. Verify with `command -v gcc` returning nothing.
