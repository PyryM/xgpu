#############################################################################
FROM oven/bun:debian as builder

RUN apt-get update && \
    apt-get install -y -qq --no-install-recommends python3-pip && \
    pip install ruff

WORKDIR /tmp
# run the bun build
COPY codegen ./codegen/
COPY bun.lockb packaging/pyproject.toml .
RUN bun codegen/generate.ts

# run ruff to automatically format and fix linter errors
RUN ruff . --fix && ruff format .


############################################
FROM scratch AS output

# rename webgoo to a module entrypoint
COPY --from=builder /tmp/webgoo.py ./__init__.py
COPY --from=builder /tmp/wgpu_native_build.py .




