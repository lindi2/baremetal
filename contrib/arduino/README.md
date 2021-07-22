# Introduction

This page describes how you can use an Arduino to control both AC
power and press the power button of the device.

# Hardware

The following pieces of hardware were used in this setup:

- Arduino Uno R3
- Arduino ethernet shield (WS1500, pins 10, 11, 12, 13)
- Arduino 4-channel relay shield (pins 4, 5, 6, 7)
- Arduino protoshield with a 433 MHz transmitter (pin 9)
- Remote control power sockets that can be controlled over 433 MHz transmissions

Connect all of your test devices to the power sockets and then wire
cables from their power buttons to the relay shield relays so that you
can automatically press the power button.

# Software

## Building

To build the software install the Arduino development environment and
load the 433 MHz library from the `rc_switch` directory. Then compile
and upload the `http_relay_arduino` program.

## Capturing codes

Note that you probably need to also build a setup where you can
receive signals sent by your normal transmitter to be able to know the
codes that your power sockets understand. You can use a 433 MHz
receiver and the `rc_switch` library for this. The file
`everflourish_transmitter_capture.txt` contains all codes understood
by the Everflourish system.

## Using the API

The software will make Arduino listen on port 80 at 10.44.13.2. The
following two HTTP APIs are supported:

| Endpoint                                     | Description                                         |
| --------------------------------------------- ---------------------------------------------------- |
| POST /press?relay=A&duration=B               | Activate relay A for B seconds and then release it. |
| POST /transmit?code=000101010001010101010111 | Send the code 000101010001010101010111 over 433 MHz |


