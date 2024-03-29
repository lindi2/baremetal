#!/bin/bash
set -x
set -e

echo "Make sure the installation is as identical to manual install as possible"
DEBIAN_FRONTEND=noninteractive apt-get install -y debconf-utils
echo "keyboard-configuration keyboard-configuration/layoutcode string fi" | debconf-set-selections
echo "keyboard-configuration keyboard-configuration/variant select Finnish" | debconf-set-selections
echo "keyboard-configuration keyboard-configuration/xkb-keymap select fi" | debconf-set-selections
echo "Make sure grub upgrades will work on real hardware"
echo grub-pc grub-pc/install_devices string /dev/sda | debconf-set-selections
DEBIAN_FRONTEND=noninteractive apt-get install -y console-setup console-setup-linux eject kbd keyboard-configuration usb.ids usbutils xkb-data
apt-mark auto usb.ids console-setup-linux xkb-data kbd 
if ! grep -q LANGUAGE /etc/default/locale; then
    echo "$0: locale: Fixing LANGUAGE"
    update-locale 'LANGUAGE="en_US:en"'
fi
apt-get remove -y debconf-utils
apt-get clean

if grep -q "variant=unstable" /proc/cmdline; then
    echo "Upgrade to Debian unstable"
    echo "deb http://deb.debian.org/debian/ sid main" > /etc/apt/sources.list
    apt-get update
    apt-get -y dist-upgrade
fi

echo "Reconfigure grub2"
sed -i "s@GRUB_CMDLINE_LINUX_DEFAULT=.*@GRUB_CMDLINE_LINUX_DEFAULT=\"quiet net.ifnames=0 console=ttyS0,115200 console=tty0\"@" /etc/default/grub
update-grub2

echo "Install reporting service"
cp baremetal-agent-downloader /usr/local/bin/
cp baremetal-agent-downloader.service /etc/systemd/system/
systemctl enable baremetal-agent-downloader.service

echo "Minimize image size"
apt-get -y install apt-show-versions
apt-get -y purge bind9-host discover-data openssh-client python2 python2.7 python2.7-minimal
rm -fr /lib/modules/*/kernel/{sound,drivers/media,drivers/isdn}
apt-get autoremove -y
set +x
for i in $(find /lib/modules -name "*.ko"); do
    if [ "$(file "$i"|grep ELF)" != "" ]; then
        xz -v -1 $i
        mv $i.xz $i
    fi
done
set -x
update-initramfs -k all -u
apt-get clean
fstrim -a
