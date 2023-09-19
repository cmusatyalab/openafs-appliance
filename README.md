# OpenAFS Appliance

Collection of scripts to assist in building a Virtual Machine image that
provides a SMB/CIFS server share to access the Andrew File System (AFS) through
an OpenAFS client that is installed and running in the VM.

The resulting Virtual Machine image has been tested with both QEMU/KVM on Linux
(.qcow image) and VMWare Workstation 17 Pro on Windows (.vmdk image).


## Usage

Set up a basic virtual machine using the qcow or vmdk disk image. Networking
can be configured as a NAT if you only plan to use the resulting VM from the
local system.

Once the virtual machine is started, it will announce its availability through
MDNS/Zeroconf broadcasts as 'openafs.local'. With a web-browser you can
navigate to 'http://openafs.local' which should give you a webpage to
authenticate.

There are at least 2 accounts in play, the local "SMB" user account that is
created on the appliance which is how your local client authenticates with the
installed Samba (SMB/CIFS) server and a Kerberos realm account which is how you
authenticate with your local AFS cell.

You can change the SMB password at anytime by re-authenticating with your valid
Kerberos credentials. Any time you authenticate a ticket granting ticket will
be stored inside the appliance and this will be used by the SMB server to
obtain tokens for the AFS cell.


## Building an image

### Requirements

- Debian/Ubuntu based system
    (we rely on vmdb2/debootstrap to handle the image creation)

- vmdb2 >= 0.20
- ansible >= 2.9
- sudo permissions (to partition, loopback mount and build the VM image)

### Rebuild Samba server packages

Need to apply `fake_perms_fix_symlinks.patch` so that symlinks do not get
clobbered by the `vfs_fake_perms` plugin module. I have pre-built packages and
put them at 'http://coda.cs.cmu.edu/~jaharkes/samba-rebuild/' but to do a local
rebuild you need to build on "Debian stable (bookworm)" or get a root login on
a previously built openafs-appliance image in which case you may have to use
qemu-img to increase the size of the disk image to 8GB.

```
    echo "deb-src http://deb.debian.org/debian bookworm main" >> /etc/apt/sources.list
    apt update && apt install devscripts
    apt-get build-dep samba && apt-get source samba
    cd samba-*
    export QUILT_PATCHES=debian/patches
    export QUILT_REFRESH_ARGS="-p ab --no-timestamps --no-index"
    export DEBEMAIL="Your user <your@email>"
    quilt import (path to)/fake_perms_fix_symlinks.patch
    dch -n "Fix vfs_fake_perms to only change mode bits of directory and file objects."
    debuild -uc -us
```

You should end up with a bunch of `*.deb` files in the parent directory.
Collect them into their own directory and in that directory run
`dpkg-scanpackages . | gzip > Packages.gz` to turn it into a minimal
apt-installable repo.


### Build steps

Run `./setup.sh` which will pull the latest source for vmdb2 and installs
several utilities that vmdb2 depends on. I've found that in addition, the
default ansible on my system was too old and I had to install a current
version with `pipx install` as root (since vmdb2 runs the ansible install
script as the root user). This only needs to be done once.

Look at `openafs-appliance.vmdb` and update the `extra_vars` defined in the
'generic configuration and fixups' step near the end of the file for your own
Kerberos realm, AFS cell, if you want to include Coda and optionally point at
your own rebuilt Samba package repo. To see available options and defaults
look at the top of the openafs-appliance.yml file.

Run `./build.sh` to bootstrap and build the actual appliance image.
The base system will be cached in openafs-appliance.tgz, so after the initial
build any re-runs will not redownload the packages for the base image and only
the ansible configuration steps will be repeated.

If you add or remove a core package dependency in the .vmdb file or want to
update to the latest security fixes, remove `openafs-appliance.tgz` before
running build.sh.
