#!/bin/sh
set -x
set -o pipefail

echo "log baremetal initrd: Starting image download" | nc 10.44.12.1 2500
time wget -U baremetal -O - http://10.44.12.1/baremetal/baremetal.img.lzo | lzop -d -c > /dev/sda
rc="$?"
echo "log baremetal initrd: Syncing and dropping caches" | nc 10.44.12.1 2500
echo "log baremetal initrd: Testing serial console" | nc 10.44.12.1 2500
echo "baremetal initrd: testing serial console at 115200" | microcom -t 1000 -s 115200 /dev/ttyS0
sync
echo 3 > /proc/sys/vm/drop_caches
sync
sync
echo "baremetal initrd: Signaling exit and waiting for commands"
echo netboot_exit $rc | nc 10.44.12.1 2500
nc -l -p 9000 | /bin/sh


