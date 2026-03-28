FROM ubuntu:24.04 AS builder
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential cmake libspdlog-dev libcli11-dev libgtest-dev libgmock-dev \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /src
COPY . .
RUN cmake -B build && cmake --build build && cd build && ctest --output-on-failure

FROM ubuntu:24.04
RUN apt-get update && apt-get install -y --no-install-recommends python3 && rm -rf /var/lib/apt/lists/*
COPY --from=builder /src/build/cppulse /usr/local/bin/cppulse
ENTRYPOINT ["/usr/local/bin/cppulse"]
