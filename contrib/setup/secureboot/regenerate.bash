#!/bin/bash

openssl req -config ./openssl.cnf \
        -new -x509 -newkey rsa:2048 \
        -nodes -days 36500 -outform DER \
        -keyout "MOK.key.pem" \
        -out "MOK.cert.der"

openssl x509 -in MOK.cert.der -inform der -outform pem -out MOK.cert.pem

