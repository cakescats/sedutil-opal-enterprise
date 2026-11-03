# syntax=docker/dockerfile:1.7
FROM python:3.12-slim

# The released PBA image that enrolment builds machine images from, and the
# image builder, both from cakescats/sedutil-pba and checked by hash.
# The PBA shows the QR code from release v1.20.0-cakes.2 on; update these
# four lines to the release you roll out.
ARG PBA_IMAGE_URL=https://github.com/cakescats/sedutil-pba/releases/download/v1.20.0-cakes.1/cakes-pba-1.20.0-cakes.1+g39e8ed9-default.img.gz
ARG PBA_IMAGE_SHA256=ce5f208401123d8b6a908ad4ac6d05fbeddbfd8c2cb602867df5744e6b5e4659
ARG BUILDER_URL=https://raw.githubusercontent.com/cakescats/sedutil-pba/e8b543b1ad3ff0f96230d3801336735d9ea7a821/tools/cakes-builder.py
ARG BUILDER_SHA256=4e3a111018e927f600270aea82cbc30d42d0e3addde6e75c5de91c121dde3002

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
ADD --checksum=sha256:${PBA_IMAGE_SHA256} ${PBA_IMAGE_URL} /opt/cakes/base.img.gz
ADD --checksum=sha256:${BUILDER_SHA256} ${BUILDER_URL} /opt/cakes/cakes-builder.py
COPY app.py unlock.py manage.py ./
RUN useradd -m unlock && mkdir /data && chown unlock /data && chmod 644 /opt/cakes/*
USER unlock
ENV UNLOCK_DB=/data/unlock.db BASE_IMAGE=/opt/cakes/base.img.gz BUILDER=/opt/cakes/cakes-builder.py
EXPOSE 8000
CMD ["gunicorn", "-b", "0.0.0.0:8000", "-w", "2", "app:app"]
