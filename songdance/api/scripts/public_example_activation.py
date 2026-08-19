import ctypes
import os
import sys
from pathlib import Path


def exchange_directories(left: Path, right: Path) -> None:
    libc = ctypes.CDLL(None, use_errno=True)
    left_bytes = os.fsencode(left)
    right_bytes = os.fsencode(right)
    at_fdcwd = -2
    exchange_flag = 0x00000002
    if sys.platform == "darwin":
        rename_exchange = libc.renameatx_np
    elif sys.platform.startswith("linux"):
        rename_exchange = libc.renameat2
    else:
        raise RuntimeError(f"atomic directory exchange is unsupported on {sys.platform}")
    rename_exchange.argtypes = [
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_uint,
    ]
    rename_exchange.restype = ctypes.c_int
    if rename_exchange(at_fdcwd, left_bytes, at_fdcwd, right_bytes, exchange_flag) != 0:
        error_number = ctypes.get_errno()
        raise OSError(error_number, os.strerror(error_number), str(left), str(right))
