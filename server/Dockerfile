# syntax=docker/dockerfile:1.7
FROM python:3.12-slim

# The released PBA image that enrolment builds machine images from, and the
# image builder, both from cakescats/sedutil-pba and checked by hash.
# Update these four lines to the release you roll out (v1.20.0-cakes.2 or
# later: earlier PBAs don't show the QR code).
ARG PBA_IMAGE_URL=https://github.com/cakescats/sedutil-pba/releases/download/v1.20.0-cakes.2/cakes-pba-1.20.0-cakes.2-default.img.gz
ARG PBA_IMAGE_SHA256=47a051b26858af213a619bab08a30132b9453124fe76d6e2fa827437fceef931
ARG BUILDER_URL=https://raw.githubusercontent.com/cakescats/sedutil-pba/098281205d0a3a2b3a7ecbb571dfad5b7cc1700e/tools/cakes-builder.py
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
