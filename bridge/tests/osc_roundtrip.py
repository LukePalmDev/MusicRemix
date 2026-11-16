"""OSC round-trip test against Ardour (port 3819). Replies arrive on port 8000
(the session's OSC 'remote-port', address-only mode)."""
import socket, threading, time
from pythonosc.osc_message_builder import OscMessageBuilder
from pythonosc.osc_message import OscMessage

recv = []
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.bind(("127.0.0.1", 8000))
sock.settimeout(0.3)

def listen(stop):
    while not stop.is_set():
        try:
            data, _ = sock.recvfrom(65536)
            m = OscMessage(data); recv.append((m.address, m.params))
        except socket.timeout:
            pass
        except Exception as e:
            recv.append(("<decode-error>", [str(e)]))

def send(addr, *args):
    b = OscMessageBuilder(address=addr)
    for a in args: b.add_arg(a)
    sock.sendto(b.build().dgram, ("127.0.0.1", 3819))

stop = threading.Event(); t = threading.Thread(target=listen, args=(stop,)); t.start()
send("/set_surface", 0, 159, 7, 0, 0)        # bank all, strip types, feedback buttons+values+ssid
time.sleep(0.5)
send("/strip/list")
time.sleep(1.0)
send("/strip/gain", 2, -2.5)                  # strip 2 = Test Piano (OSC strips are 1-based)
time.sleep(0.5)
stop.set(); t.join()
names = [p for a, p in recv if a == "/strip/name" or a == "/strip/list" or a.startswith("/strip/")]
print("messages received:", len(recv))
for a, p in recv[:25]:
    print(" ", a, p)
