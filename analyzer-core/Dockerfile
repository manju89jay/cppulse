# --------------------------------------------------------------------------
# cppulse analyzer-core -- multi-stage Docker build
# --------------------------------------------------------------------------
FROM ubuntu:24.04 AS builder

ENV DEBIAN_FRONTEND=noninteractive

# Install build tools and all C++ dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    cmake \
    libclang-19-dev \
    nlohmann-json3-dev \
    libspdlog-dev \
    libcli11-dev \
    libgtest-dev \
    libgmock-dev \
    && rm -rf /var/lib/apt/lists/*

# Keep the analyzer and its Linux supervisor source in their repository layout.
WORKDIR /src
COPY analyzer-core/CMakeLists.txt analyzer-core/
COPY analyzer-core/src/ analyzer-core/src/
COPY analyzer-core/tests/ analyzer-core/tests/
COPY tools/frozen_container_supervisor.cpp tools/
RUN cmake -S analyzer-core -B build && cmake --build build \
    && ctest --test-dir build --output-on-failure

# --------------------------------------------------------------------------
# Runtime stage
# --------------------------------------------------------------------------
FROM ubuntu:24.04

RUN apt-get update && apt-get install -y --no-install-recommends \
    libclang1-19 \
    libclang-common-19-dev \
    g++ \
    libspdlog-dev \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /src/build/cppulse-analyzer /usr/local/bin/cppulse-analyzer
COPY analyzer-core/docker-entrypoint.sh /usr/local/bin/cppulse-analyzer-entrypoint
RUN chmod +x /usr/local/bin/cppulse-analyzer-entrypoint

ENTRYPOINT ["/usr/local/bin/cppulse-analyzer-entrypoint"]
