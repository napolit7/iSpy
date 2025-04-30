# iSpy

**iSpy** is a forensic tool for extracting and recovering data from jailbroken iPhones. It currently supports **iOS 15.x and below** and enables forensic analysis of SQLite databases, media files, and other remnants of deleted user data. Compatible with Windows, but can be modified to work with MacOS or Linux by removing references to USB proxy and instead using usbmuxd.

---

## Features

- Extracts data from key iOS paths (Messages, Contacts, Attachments, DCIM, etc.)
- Recovers deleted SQLite entries (e.g., messages, contacts) by parsing database internals
- Attempts recovery of deleted photos/videos via raw disk image analysis (planned)
- Works on jailbroken iOS devices (tested with unc0ver on iOS 14.8)

---

## Requirements

- Jailbroken iPhone (iOS 15.x or lower)
- SSH access to the device (e.g., via `OpenSSH` or `dropbear`)
- Python 3.7+
- `paramiko` for SCP/SFTP
- iproxy.exe from libimobile suite (or any other SSH over USB proxy) for USB features

Install Python dependencies:
```bash
pip install paramiko
```
---

## Usage
![image](https://github.com/user-attachments/assets/eccade12-c0d3-4d6b-a6d5-dba0632548b1)

---

## Disclaimer

This tool is intended for educational and lawful forensic purposes only. Use on devices you own or are authorized to examine.
