"""Small reconnecting Beast TCP relay; one systemd instance per destination."""
import logging
import socket
import sys
import time
from .config import read

def run(name):
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    while True:
        config = read("/etc/airnode/config.json")
        target = next((f for f in config["feeders"] if f["id"] == name and f["enabled"]), None)
        if not target:
            return
        try:
            with socket.create_connection(("127.0.0.1", 30005), 10) as source, socket.create_connection((target["host"], target["port"]), 10) as dest:
                logging.info("Connected to %s:%s", target["host"], target["port"])
                source.settimeout(90)
                dest.settimeout(15)
                while chunk := source.recv(65536):
                    dest.sendall(chunk)
                logging.warning("Receiver stream closed")
        except OSError as exc:
            logging.warning("Connection unavailable: %s", exc)
        time.sleep(10)

if __name__ == "__main__":
    run(sys.argv[1])
