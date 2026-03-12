FROM python:3.12-slim AS base

WORKDIR /app

# Install the package
COPY pyproject.toml README.md ./
COPY src/ src/
RUN pip install --no-cache-dir .

# HTTP transport mode
ENV BAR_ASSISTANT_URL=""
ENV BAR_ASSISTANT_BAR_ID="1"
ENV MCP_ISSUER_URL=""

EXPOSE 8100

CMD ["bar-assistant-mcp", "--transport", "streamable-http"]
