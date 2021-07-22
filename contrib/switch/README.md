# Introduction

A Zyxel GS1200-8 switch is used in this project since it is cheap,
compact and supports VLANs.

# Configuration

The configuration file `zyxel_gs1200-8_cfg.bin` setups the switch so
that ports 1-7 are in VLANs 1-7 and port 8 includes all VLANs as
tagged. VLAN 1 is for management and listens on http://192.168.1.3.

# Setup

The current hardware setup is as follows:

| Port | Description  |
|------|--------------|
|  2   | Internet     |
|  3   | Arduino      |
|  4   | First target |
|  5   | Second target|

# Link status

You can use the `zyxel_gs1200-8_get_link_status.py` program to query
the link status of a port. This is needed to reliably detect that the
target system has booted up as the the 433 MHz power sockets are not
100% reliable due to limited range and interference.

