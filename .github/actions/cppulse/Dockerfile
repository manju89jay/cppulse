# Development source definition only; Docker execution is not qualified.
# This adapter checks a supplied local store. It does not collect, analyze,
# checkout refs, request credentials, post comments or upload artifacts.
FROM python:3.12-slim-bookworm
COPY pyproject.toml README.md LICENSE /opt/cppulse-source/
COPY python/ /opt/cppulse-source/python/
RUN python -m venv /opt/cppulse-env \
    && /opt/cppulse-env/bin/python -m pip install --no-cache-dir /opt/cppulse-source
ENV PATH="/opt/cppulse-env/bin:${PATH}"
COPY .github/actions/cppulse/entrypoint.sh /opt/cppulse/entrypoint.sh
RUN chmod +x /opt/cppulse/entrypoint.sh
WORKDIR /github/workspace
ENTRYPOINT ["/opt/cppulse/entrypoint.sh"]
