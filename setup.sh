#!/bin/sh

sudo apt install -y \
    kpartx \
    ovmf \
    parted \
    python3-jinja2 \
    python3-yaml \
    qemu-utils \
    qemu-user-static \
    zerofree

[ -e vmdb2 ] || git clone git://git.liw.fi/vmdb2
