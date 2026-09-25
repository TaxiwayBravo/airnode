import os
from .config import read, receiver_args

if __name__ == "__main__":
    args = receiver_args(read("/etc/airnode/config.json"))
    os.execv(args[0], args)
