# Introduction

In theory you should get a working setup with the following commands:

```
git clone https://github.com/lindi2/baremetal
(cd baremetal/contrib/setup && ./setup.bash)
editor baremetal/setup/switch/zyxel.password
mkdir queue
baremetal/server/baremetal_queue_processor.py --queue-dir queue --config baremetal/contrib/setup/server.config --target-state target-state --prepare-image /srv/baremetal/templates/baremetal_template_debian_bullseye_bios.img.lzo --machine bios
baremetal/server/baremetal_queue_processor.py --queue-dir queue --config baremetal/contrib/setup/server.config --target-state target-state --prepare-image /srv/baremetal/templates/baremetal_template_debian_bullseye_uefi.img.lzo --machine uefi
uuidgen > .baremetal_apikeys
gunicorn3 --bind  127.0.0.1:3000 --pythonpath baremetal/server -k flask_sockets.worker 'baremetal_queue_server:app(api_keys=".baremetal_apikeys", queue_dir="queue", config="baremetal/contrib/setup/server.config")'
```

You should be able to test this with:

```
time baremetal/client/baremetal_queue_client.py -u http://10.0.5.102:3000 -o tpm1_bios.tar --machine thinkpad_r400 --api-key .baremetal_apikeys --template debian_unstable_bios
time baremetal/client/baremetal_queue_client.py -u http://10.0.5.102:3000 -o tpm2_uefi.tar --machine elitedesk_800 --api-key .baremetal_apikeys --template debian_unstable_uefi
```
