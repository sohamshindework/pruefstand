FROM python:3.12-slim AS build
WORKDIR /build
COPY pyproject.toml README.md LICENSE NOTICE ./
COPY src ./src
RUN pip wheel --no-cache-dir --no-deps --wheel-dir /wheels .

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY --from=build /wheels /wheels
RUN pip install --no-cache-dir /wheels/*.whl && rm -rf /wheels \
    && useradd --uid 10001 --create-home --shell /usr/sbin/nologin lab \
    && mkdir /output && chown lab:lab /output
USER 10001:10001
WORKDIR /output
ENTRYPOINT ["pruefstand"]
CMD ["demo", "--out", "/output"]
