# --------------------------------------------------------------------------
# cppulse analyzer-core -- multi-stage Docker build
# --------------------------------------------------------------------------
FROM ubuntu:24.04 AS builder

ENV DEBIAN_FRONTEND=noninteractive

# Install build tools and all C++ dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    cmake \
    libclang-dev \
    llvm-dev \
    nlohmann-json3-dev \
    libspdlog-dev \
    libcli11-dev \
    libgtest-dev \
    libgmock-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy CMakeLists.txt first for better layer caching
WORKDIR /src
COPY CMakeLists.txt .

# Copy source and build
COPY . .
RUN cmake -B build && cmake --build build \
    && cd build && ctest --output-on-failure

# --------------------------------------------------------------------------
# Runtime stage
# --------------------------------------------------------------------------
FROM ubuntu:24.04

RUN apt-get update && apt-get install -y --no-install-recommends \
    libclang1 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /src/build/cppulse-analyzer /usr/local/bin/cppulse-analyzer

ENTRYPOINT ["/usr/local/bin/cppulse-analyzer"]
