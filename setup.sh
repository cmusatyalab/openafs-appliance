#!/bin/sh

sudo apt install -y \
    kpartx \
    ovmf \
    openssl \
    parted \
    python3-jinja2 \
    python3-yaml \
    qemu-utils \
    qemu-user-static \
    zerofree

[ -e vmdb2 ] || git clone git://git.liw.fi/vmdb2

[ -e openafs-appliance.crt ] || openssl req -x509 -newkey rsa:4096 -keyout openafs-appliance.key -out openafs-appliance.crt -sha256 -days 3650 -nodes -subj "/C=US/ST=Pennsylvania/L=Pittsburgh/O=CMU/OU=SCS-CSD/CN=openafs.local"
