#!/bin/bash
set -x
set -e

sudo apt install isc-dhcp-server tftpd-hpa syslinux-common pxelinux ffmpeg tcpdump pulseaudio-utils python3-pip ser2net socat vlan uuid-runtime python3-flask curl lzop syslinux-efi etherwake
sudo systemctl disable --now tftpd-hpa
sudo systemctl disable --now ser2net
#pip3 install --user librosa

sudo dd of=/etc/network/interfaces <<EOF
# This file describes the network interfaces available on your system
# and how to activate them. For more information, see interfaces(5).

source /etc/network/interfaces.d/*

# The loopback network interface
auto lo
iface lo inet loopback
EOF

sudo dd of=/etc/network/interfaces.d/baremetal <<EOF
auto vlan1
iface vlan1 inet static
 vlan-raw-device enp3s0
 address 192.168.1.1
 netmask 255.255.255.0

auto vlan2
iface vlan2 inet dhcp
 vlan-raw-device enp3s0

auto vlan3
iface vlan3 inet static
 vlan-raw-device enp3s0
 address 10.44.13.1
 netmask 255.255.255.0

auto vlan4
iface vlan4 inet manual
 vlan-raw-device enp3s0

auto vlan5
iface vlan5 inet manual
 vlan-raw-device enp3s0
EOF
sudo ifup vlan2 || true
sudo ifup vlan1 || true
sudo ifup vlan3 || true


for i in 4 5; do
    if sudo ip netns exec ns_vlan$i true 2> /dev/null; then
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
    sudo systemd-run -p Restart=on-failure --unit vlan${i}_dhcp ip netns exec ns_vlan${i} /usr/sbin/dhcpd -4 -f -cf $(pwd)/dhcpd.conf -lf /srv/baremetal/vlan${i}/dhcp/leases -pf /srv/baremetal/vlan${i}/dhcp/pid vlan${i}

    # TFTP
    sudo mkdir -p /srv/baremetal/vlan${i}/tftp/pxelinux.cfg
    sudo cp /usr/lib/PXELINUX/lpxelinux.0 /srv/baremetal/vlan${i}/tftp
    sudo cp /usr/lib/SYSLINUX.EFI/efi64/syslinux.efi /srv/baremetal/vlan${i}/tftp
    sudo cp /usr/lib/syslinux/modules/bios/ldlinux.c32 /srv/baremetal/vlan${i}/tftp
    sudo cp /usr/lib/syslinux/modules/efi64/ldlinux.e64 /srv/baremetal/vlan${i}/tftp
    # Allow symlink to be created as normal user to enable/disable PXE boot efficiently
    sudo chown "$USER" /srv/baremetal/vlan${i}/tftp
    sudo cp pxelinux_default /srv/baremetal/vlan${i}/tftp/pxelinux.cfg/default
    sudo systemd-run -p Restart=on-failure --unit vlan${i}_tftp ip netns exec ns_vlan${i} /usr/sbin/in.tftpd --foreground --user tftp --address 10.44.12.1:69 --secure /srv/baremetal/vlan${i}/tftp

    # HTTP
    sudo mkdir -p /srv/baremetal/vlan${i}/http/baremetal
    sudo cp /boot/vmlinuz-$(uname -r) /srv/baremetal/vlan${i}/http/baremetal/vmlinuz
    sudo cp baremetal.sh /srv/baremetal/vlan${i}/http/baremetal
    # Allow normal user to add a disk image here
    sudo chown "$USER" /srv/baremetal/vlan${i}/http/baremetal
    sudo /usr/sbin/mkinitramfs -d initramfs-tools.baremetal -o /srv/baremetal/vlan${i}/http/baremetal/initrd.img $(uname -r)
    sudo systemd-run -p Restart=on-failure --unit vlan${i}_http ip netns exec ns_vlan${i} python3 -m http.server --directory /srv/baremetal/vlan${i}/http 80

    # log
    sudo systemd-run -p Restart=on-failure --unit vlan${i}_log ip netns exec ns_vlan${i} socat TCP-LISTEN:2500,fork,reuseaddr EXEC:'nsenter -t 1 -n socat -v - TCP-CONNECT\:localhost\:250'${i}
    
    # control
    sudo systemd-run -p Restart=on-failure --unit vlan${i}_control socat TCP-LISTEN:900${i},fork,reuseaddr EXEC:'ip netns exec ns_vlan'${i}' socat - TCP-CONNECT\:10.44.12.2\:9000'

    # serial
    case "${i}" in
	4)
	    sudo ln -sf "serial/by-path/pci-0000:00:14.0-usb-0:2.3:1.0-port0" /dev/serial_vlan${i}
	    ;;
	5)
	    sudo ln -sf "serial/by-path/pci-0000:00:14.0-usb-0:3.2:1.0-port0" /dev/serial_vlan${i}
	    ;;
    esac
    sudo systemd-run -p Restart=on-failure --unit vlan${i}_serial ser2net -n -C "210${i}:raw:600:/dev/serial_vlan${i}:115200 8DATABITS NONE 1STOPBIT"
done
