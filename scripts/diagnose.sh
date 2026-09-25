#!/bin/bash
set -u
echo 'AirNode service health'
systemctl --no-pager --full status airnode-api airnode-control airnode-receiver
echo 'USB devices'
lsusb
echo 'Network addresses'
ip -brief address
echo 'Receiver journal'
journalctl -u airnode-receiver -n 40 --no-pager
echo 'Loopback API health'
curl --fail http://127.0.0.1:8080/api/health
echo
