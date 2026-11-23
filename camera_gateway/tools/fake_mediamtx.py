"""FAKE stand-in for MediaMTX, for OFFLINE Stage 2 runner dry runs only (MediaMTX itself
must not be started during preparation). It binds ONLY 127.0.0.1:<port> (TCP), accepts
and closes connections, and runs until killed, so the runner's port-free, listener and
cleanup checks are exercised for real. It is not an RTSP server.
"""
import socket
import sys


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8554
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", port))
    s.listen(8)
    while True:
        c, _ = s.accept()
        c.close()


if __name__ == "__main__":
    sys.exit(main())
