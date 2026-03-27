# cppulse GitHub Action — all-in-one analysis image
# Contains: cppulse-analyzer (C++), git-miner, predictor, report-engine (Python)

# ── Stage 1: Build the C++ analyzer ────────────────────────────
FROM ubuntu:24.04 AS cpp-builder

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential cmake \
    libclang-dev llvm-dev \
    nlohmann-json3-dev libspdlog-dev libcli11-dev \
    libgtest-dev libgmock-dev \
    && rm -rf /var/lib/apt/lists/*

COPY analyzer-core/ /build/analyzer-core/
WORKDIR /build/analyzer-core
RUN cmake -B build -DCMAKE_BUILD_TYPE=Release && cmake --build build -j$(nproc)

# ── Stage 2: Runtime image with Python + C++ binary ────────────
FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-pip python3-venv \
    git \
    libclang1 \
    libpango-1.0-0 libpangocairo-1.0-0 libgdk-pixbuf-2.0-0 \
    libffi-dev libcairo2 \
    jq \
    && rm -rf /var/lib/apt/lists/*

# Copy analyzer binary
COPY --from=cpp-builder /build/analyzer-core/build/cppulse-analyzer /usr/local/bin/

# Install Python components
COPY git-miner/requirements.txt /tmp/git-miner-requirements.txt
COPY predictor/requirements.txt /tmp/predictor-requirements.txt
COPY report-engine/requirements.txt /tmp/report-engine-requirements.txt

RUN pip install --no-cache-dir --break-system-packages \
    -r /tmp/git-miner-requirements.txt \
    -r /tmp/predictor-requirements.txt \
    -r /tmp/report-engine-requirements.txt

# Copy Python source
COPY git-miner/src/ /app/git-miner/src/
COPY predictor/src/ /app/predictor/src/
COPY report-engine/src/ /app/report-engine/src/
COPY docs/schemas/ /app/schemas/

# Copy action scripts
COPY .github/actions/cppulse/entrypoint.sh /app/entrypoint.sh
COPY .github/actions/cppulse/post_comment.py /app/post_comment.py
COPY .github/actions/cppulse/diff_findings.py /app/diff_findings.py
RUN chmod +x /app/entrypoint.sh

WORKDIR /app
ENTRYPOINT ["/app/entrypoint.sh"]
