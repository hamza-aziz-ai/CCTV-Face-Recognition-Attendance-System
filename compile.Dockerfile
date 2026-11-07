# The app code compiled with Nuitka for the dedicated tier's -rt images (D-033 step 4). Compiled once per commit and
# architecture on the same Python image the services run on, so the extension modules match it. The result is a build
# context for the service Dockerfiles: docker build -o type=local,dest=compiled -f compile.Dockerfile .
# then docker build -f main.Dockerfile compiled/
FROM python:3.14-slim-trixie@sha256:cd89c30eda26ee911a4611b18680086e0ea42e6f5f8cbe653d07fa7958c9cec8 AS build
RUN apt-get update && apt-get install -y --no-install-recommends gcc libc6-dev patchelf && rm -rf /var/lib/apt/lists/*
# Nuitka is AGPLv3; its runtime exception (LICENSE-RUNTIME.txt) lets the compiled modules ship under our terms
RUN python3 -m pip install --no-cache-dir nuitka==4.3.4
WORKDIR /repo
COPY requirements.txt requirements.txt
COPY deploy/compile_tree.py deploy/compile_tree.py
COPY src/ src/
COPY Custom-ROI-Provisioning/ Custom-ROI-Provisioning/
RUN python3 deploy/compile_tree.py /out

FROM scratch
COPY --from=build /out/ /
