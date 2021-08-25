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
modprobe efivarfs
mount -t efivarfs none /sys/firmware/efi/efivars
echo "log baremetal initrd: efibootmgr: $(efibootmgr -v)" | nc 10.44.12.1 2500
efibootmgr -v | microcom -t 1000 -s 115200 /dev/ttyS0
if [ -e /sys/firmware/efi/efivars ]; then
    for i in $(efibootmgr | grep -i "^boot....\*.*ipv6"|cut -b 5-8); do
	echo "log baremetal initrd: disabling IPv6 network boot option $i" | nc 10.44.12.1 2500
	efibootmgr --inactive --bootnum "$i"
    done
    efibootmgr -v | microcom -t 1000 -s 115200 /dev/ttyS0
    umount /sys/firmware/efi/efivars
fi
echo "baremetal initrd: Signaling exit and waiting for commands"
echo netboot_exit $rc | nc 10.44.12.1 2500
nc -l -p 9000 | /bin/sh


