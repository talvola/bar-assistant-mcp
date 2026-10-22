FROM python:3.12-slim AS base

WORKDIR /app

# Install the package
COPY pyproject.toml README.md ./
COPY src/ src/
# python:3.12 images ship pip 25.0.1, whose vendored certifi trusts the
# compromised emSign ECC Root CA - G3. apt verifies packages by GPG signature,
# not TLS, so it can safely fetch the fixed ca-certificates (Oct 2026) first;
# PIP_CERT then makes every pip call, including the pip upgrade, use that store.
# Both stores are checked for the root, so a stale one fails the build.
ENV PIP_CERT=/etc/ssl/certs/ca-certificates.crt
RUN apt-get update && \
    apt-get install -y --no-install-recommends ca-certificates && \
    rm -rf /var/lib/apt/lists/* && \
    python -c "import ssl,sys; f=sys.argv[1]; bad=[c for c in ssl.create_default_context(cafile=f).get_ca_certs() if 'emSign ECC Root CA - G3' in str(c['subject'])]; sys.exit(f + ' still trusts emSign ECC Root CA - G3' if bad else 0)" $PIP_CERT
RUN pip install --no-cache-dir --upgrade "pip>=26.2.2" && \
    pip install --no-cache-dir . && \
    python -c "import certifi,ssl,sys; f=certifi.where(); bad=[c for c in ssl.create_default_context(cafile=f).get_ca_certs() if 'emSign ECC Root CA - G3' in str(c['subject'])]; sys.exit(f + ' still trusts emSign ECC Root CA - G3' if bad else 0)"

# HTTP transport mode
ENV BAR_ASSISTANT_URL=""
ENV BAR_ASSISTANT_BAR_ID="1"
ENV MCP_ISSUER_URL=""

EXPOSE 8100

CMD ["bar-assistant-mcp", "--transport", "streamable-http"]
