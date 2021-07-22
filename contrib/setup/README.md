# Introduction

In theory you should get a working setup with the following commands:

```
git clone https://github.com/lindi2/baremetal
(cd baremetal/contrib/setup && ./setup.bash)
editor baremetal/setup/switch/zyxel.password
mkdir queue
baremetal/server/baremetal_queue_processor.py --queue-dir queue --config baremetal/contrib/setup/server.config --machine thinkpad_r400
baremetal/server/baremetal_queue_processor.py --queue-dir queue --config baremetal/contrib/setup/server.config --machine elitedesk_800
uuidgen > .baremetal_apikeys
baremetal/server/baremetal_queue_server.py --listen-address 10.0.5.102 --api-keys .baremetal_apikeys --queue-dir queue --listen-port 3000 --config baremetal/contrib/setup/server.config
```

You should be able to test this with:

```
time baremetal/client/baremetal_queue_client.py -u http://10.0.5.102:3000 -o tpm1_bios.tar --machine thinkpad_r400 --api-key .baremetal_apikeys tboot-test-image-bios.img.lzo
time baremetal/client/baremetal_queue_client.py -u http://10.0.5.102:3000 -o tpm2_uefi.tar --machine elitedesk_800 --api-key .baremetal_apikeys tboot-test-image-uefi.img.lzo
```
