#!/usr/bin/env python3
import subprocess
import random
import sys

def random_mac():
    # Locally administered, unicast MAC
    mac = [
        0x02,  # local + unicast
        random.randint(0x00, 0x7f),
        random.randint(0x00, 0xff),
        random.randint(0x00, 0xff),
        random.randint(0x00, 0xff),
        random.randint(0x00, 0xff),
    ]
    return ":".join(f"{x:02x}" for x in mac)

def run(cmd):
    subprocess.run(cmd, check=True)

def main():
    if len(sys.argv) != 2:
        print("Usage: sudo python3 mac_changer.py <interface>")
        print("Example: sudo python3 mac_changer.py wlan0")
        sys.exit(1)

    iface = sys.argv[1]
    new_mac = random_mac()

    print(f"[+] Changing MAC for {iface} → {new_mac}")

    try:
        run(["ip", "link", "set", iface, "down"])
        run(["ip", "link", "set", iface, "address", new_mac])
        run(["ip", "link", "set", iface, "up"])
    except subprocess.CalledProcessError:
        print("[-] Failed. Are you running as root? Is the interface name correct?")
        sys.exit(1)

    print("[✓] MAC address changed successfully!")
    run(["ip", "link", "show", iface])

if __name__ == "__main__":
    main()
