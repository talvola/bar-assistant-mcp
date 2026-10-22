FROM python:3.12-slim AS base

WORKDIR /app

# Install the package
COPY pyproject.toml README.md ./
COPY src/ src/
# python:3.12 images ship pip 25.0.1, whose vendored certifi trusts the
# compromised emSign ECC Root CA - G3; upgrade pip before installing anything.
RUN pip install --no-cache-dir --upgrade "pip>=26.2.2" && \
    pip install --no-cache-dir .

# HTTP transport mode
ENV BAR_ASSISTANT_URL=""
ENV BAR_ASSISTANT_BAR_ID="1"
ENV MCP_ISSUER_URL=""

EXPOSE 8100

CMD ["bar-assistant-mcp", "--transport", "streamable-http"]
