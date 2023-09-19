#!/bin/sh
#
# SPDX-FileCopyrightText: 2023 Carnegie Mellon University
# SPDX-License-Identifier: GPL-2.0-only
#
set -ex

#VMDB2=$(which vmdb2)
VMDB2=vmdb2/vmdb2

rm -f openafs-appliance.img

sudo "$VMDB2" -v \
    --rootfs-tarball openafs-appliance.tgz \
    --log openafs-appliance.log \
    --output openafs-appliance.img \
    openafs-appliance.vmdb

qemu-img convert -cp -O qcow2 openafs-appliance.img openafs-appliance.qcow2
qemu-img convert -p -O vmdk openafs-appliance.img openafs-appliance.vmdk
