#!/bin/bash

sudo apt install isc-dhcp-server tftpd-hpa syslinux-common pxelinux ffmpeg tcpdump pulseaudio-utils python3-pip
pip3 install --user librosa

for i in 4 5; do
    if sudo ip netns exec ns_vlan$i true; then
	# Already configured
	continue
    fi
    sudo ip netns add ns_vlan${i}
    sudo ip link set vlan${i} netns ns_vlan${i}
    sudo ip netns exec ns_vlan${i} ip addr add 10.44.12.1/24 dev vlan${i}
    sudo ip netns exec ns_vlan${i} ip link set vlan${i} up
    sudo ip netns exec ns_vlan${i} ip link set lo up

    # DHCP
    sudo mkdir -p /srv/baremetal/vlan${i}/dhcp
    sudo touch /srv/baremetal/vlan${i}/dhcp/leases
    sudo systemd-run --unit vlan${i}_dhcp ip netns exec ns_vlan${i} /usr/sbin/dhcpd -4 -f -cf $(pwd)/dhcpd.conf -lf /srv/baremetal/vlan${i}/dhcp/leases -pf /srv/baremetal/vlan${i}/dhcp/pid vlan${i}

    # TFTP
    sudo mkdir -p /srv/baremetal/vlan${i}/tftp/pxelinux.cfg
    sudo cp /usr/lib/PXELINUX/lpxelinux.0 /srv/baremetal/vlan${i}/tftp/lpxelinux.0.real
    sudo cp /usr/lib/syslinux/modules/bios/ldlinux.c32 /srv/baremetal/vlan${i}/tftp
    # Allow symlink to be created as normal user to enable/disable PXE boot efficiently
    sudo chown "$USER" /srv/baremetal/vlan${i}/tftp
    sudo cp pxelinux_default /srv/baremetal/vlan${i}/tftp/pxelinux.cfg/default
    sudo systemd-run --unit vlan${i}_tftp ip netns exec ns_vlan${i} /usr/sbin/in.tftpd --foreground --user tftp --address 10.44.12.1:69 --secure /srv/baremetal/vlan${i}/tftp

    # HTTP
    sudo mkdir -p /srv/baremetal/vlan${i}/http/baremetal
    sudo cp /boot/vmlinuz-$(uname -r) /srv/baremetal/vlan${i}/http/baremetal/vmlinuz
    sudo cp baremetal.sh /srv/baremetal/vlan${i}/http/baremetal
    # Allow normal user to add a disk image here
    sudo chown "$USER" /srv/baremetal/vlan${i}/http/baremetal
    sudo /usr/sbin/mkinitramfs -d initramfs-tools.baremetal -o /srv/baremetal/vlan${i}/http/baremetal/initrd.img $(uname -r)
    sudo systemd-run --unit vlan${i}_http ip netns exec ns_vlan${i} python3 -m http.server --directory /srv/baremetal/vlan${i}/http 80

    # log
    sudo systemd-run --unit vlan${i}_log ip netns exec ns_vlan${i} socat TCP-LISTEN:2500,fork,reuseaddr EXEC:'nsenter -t 1 -n socat -v - TCP-CONNECT\:localhost\:250'${i}
    
    # control
    sudo systemd-run --unit vlan${i}_control socat TCP-LISTEN:900${i},fork,reuseaddr EXEC:'ip netns exec ns_vlan'${i}' socat - TCP-CONNECT\:10.44.12.2\:9000'

    # serial
    case "${i}" in
	4)
	    sudo ln -sf "serial/by-path/pci-0000:00:14.0-usb-0:2:1.0-port0" /dev/serial_vlan${i}
	    ;;
	5)
	    sudo ln -sf "serial/by-path/pci-0000:00:14.0-usb-0:2:1.0-port0" /dev/serial_vlan${i}
	    ;;
    esac
    sudo systemd-run --unit vlan${i}_serial ser2net -n -C "210${i}:raw:600:/dev/serial_vlan${i}:115200 8DATABITS NONE 1STOPBIT"
done
