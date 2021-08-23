#!/bin/bash
set -e
set -x

t="$(mktemp -d)"
tar -czf "$t/late_command.tar.gz" late_command
for variant in buster bullseye unstable; do
    for bootmethod in bios uefi; do
        name="baremetal_template_debian_${variant}_${bootmethod}"
        if [ "$bootmethod" = "uefi" ]; then
            bootargs=" --boot uefi"
        else
            bootargs=""
        fi
        rm -f "$name.img"
        virt-install \
            --connect "qemu:///session" \
            --name "$name" \
            --ram "2048" \
            --disk "size=4,path=$name.img,format=raw,bus=scsi,discard=unmap,cache=unsafe" \
            --controller "type=scsi,model=virtio-scsi" \
            --initrd-inject "preseed.cfg" \
            --initrd-inject "$t/late_command.tar.gz" \
            --location "http://deb.debian.org/debian/dists/$variant/main/installer-amd64/" \
            --os-variant "debian10" \
            --virt-type "kvm" \
            --network "user,model=virtio" \
            --controller "usb,model=none" \
            --graphics "none" \
            --transient \
            $bootargs \
            --extra-args "auto=true hostname=debian domain= console=ttyS0,115200n8 serial net.ifnames=0"
        virt-sparsify $name.img $name.sparse.img
        lzop < $name.sparse.img > $name.img.lzo
        rm -f $name.sparse.img
    done
done
rm "$t/late_command.tar.gz"
rmdir "$t"
