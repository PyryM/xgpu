#############################################################################
FROM oven/bun:debian as builder

RUN apt-get update && \
    apt-get install -y -qq --no-install-recommends python3-pip && \
    pip install ruff

WORKDIR /tmp
# run the bun build
COPY codegen ./codegen/
COPY pyproject.toml .
RUN bun codegen/generate.ts

# run ruff to automatically format and fix linter errors
RUN ruff . --fix


############################################
FROM scratch AS output

COPY --from=builder /tmp/webgoo.py /tmp/wgpu_native_build.py .


