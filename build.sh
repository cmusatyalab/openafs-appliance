#!/bin/sh

set -ex

rm -f openafs-appliance.img

sudo `which vmdb2` -v \
    --rootfs-tarball openafs-appliance.tgz \
    --log openafs-appliance.log \
    --output openafs-appliance.img \
    openafs-appliance.vmdb

#qemu-img convert -cp -O qcow2 openafs-appliance.img openafs-appliance.qcow2
