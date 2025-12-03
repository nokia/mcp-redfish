# Copyright 2025 Nokia
# Licensed under the BSD 3-Clause License.
# SPDX-License-Identifier: BSD-3-Clause

FROM python:3.13-slim
RUN pip install --upgrade uv

WORKDIR /app
COPY . /app

# Install dependencies and activate virtual environment
RUN uv sync --locked

# Add virtual environment to PATH
ENV PATH="/app/.venv/bin:$PATH"

CMD ["uv", "run", "python", "-m", "src.main"]
