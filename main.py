import sqlite3
import paramiko
import datetime
import re
import os
import shutil
import string
import subprocess
import argparse
import stat
from wcwidth import wcswidth

def execute_query(db, query):
    conn = sqlite3.connect(db)
    cursor = conn.cursor()
    cursor.execute(query)
    rows = cursor.fetchall()
    conn.close()
    return rows

def get_data(sftp, fpath, query):
    fname = fpath.split("/")[-1]
    sftp.get(fpath, fname)
    rows = execute_query(fname, query)
    sftp.get(fpath + "-shm", fname + "-shm")
    sftp.get(fpath + "-wal", fname + "-wal")
    rows2 = execute_query(fname, query)
    return [row + (row not in rows2,) for row in rows]

def fit_in_line(text):
    max_size = shutil.get_terminal_size().columns
    text_size = wcswidth(text)
    if text_size > max_size:
        while wcswidth(text + "...") > max_size:
            text = text[:-1]
        return text + "..."
    else:
        return text + " " * (max_size - text_size)

def enumerate_files(sftp, rpath):
    count = 0
    for entry in sftp.listdir_attr(rpath):
        entry_path = rpath + "/" + entry.filename
        if stat.S_ISDIR(entry.st_mode):
            count += enumerate_files(sftp, entry_path)
        else:
            count += 1
    return count

def copy_with_progress_helper(sftp, rpath, lpath, progress):
    os.makedirs(lpath, exist_ok=True)
    copied = 0
    for entry in sftp.listdir_attr(rpath):
        rentry = rpath + "/" + entry.filename
        lentry = os.path.join(lpath, entry.filename)
        if stat.S_ISDIR(entry.st_mode):
            copied += copy_with_progress_helper(sftp, rentry, lentry, progress)
        else:
            sftp.get(rentry, lentry)
            copied += 1
            progress[0] += 1
            fname = rentry.split("/")[-1]
            print(fit_in_line(f"Copied {progress[0]}/{progress[1]}: {fname}"), end='\r', flush=True)
    return copied

def copy_with_progress(sftp, rpath, lpath):
    print("Enumerating files...", end='\r')
    copy_with_progress_helper(sftp, rpath, lpath, [0, enumerate_files(sftp, rpath)])

def ios_date(timestamp):
    return (datetime.datetime(2001, 1, 1) + datetime.timedelta(seconds=timestamp)).strftime("%Y-%m-%d %H:%M:%S")

def clean_number(raw_data):
    if raw_data is None:
        return None
    m = re.sub(r"\D", "", raw_data)
    if len(m) == 10:
        return "+1" + m
    elif len(m) == 11:
        return "+" + m
    return raw_data

parser = argparse.ArgumentParser(add_help=False)
parser.add_argument('-u', type=int, help='Port number to use as proxy over USB connection')
parser.add_argument('-p', type=str, help='Path to a proxy for SSH over USB (if using USB connection)')
parser.add_argument('-h', type=str, help='Hostname if using SSH remotely')
parser.add_argument('-o', type=str, help='Output directory')
parser.add_argument('--help', action='help', help='Show this help message and exit')

args = parser.parse_args()
WORKDIR = args.o
USB = args.u
PROXY = args.p
HOSTNAME = args.h
USERNAME = "root"
PASSWORD = "alpine"

if (USB is None and HOSTNAME is None) or (USB is not None and HOSTNAME is not None) or (PROXY is None and USB is not None):
    parser.print_help()
    exit()

if WORKDIR is None:
    WORKDIR = "."
else:
    os.makedirs(WORKDIR, exist_ok=True)

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

if USB:
    proc = subprocess.Popen([PROXY, str(args.u), "22"])
    client.connect("localhost", USB, USERNAME, PASSWORD)
else:
    client.connect(HOSTNAME, 22, USERNAME, PASSWORD)

os.chdir(WORKDIR)

print("\033[32mConnected to device\033[0m")

sftp = client.open_sftp()
print("\033[33mCopying SMS/iMessage conversations...\033[0m")
sms_rows = get_data(sftp, "/private/var/mobile/Library/SMS/sms.db", "SELECT h.id, m.text, m.date, cmj.chat_id, c.display_name, c.style, m.is_from_me, m.cache_has_attachments, a.filename, a.transfer_name \
                FROM message m \
                LEFT JOIN handle h ON h.ROWID = m.handle_id \
                JOIN chat_message_join cmj ON cmj.message_id = m.ROWID \
                JOIN chat c ON c.ROWID = cmj.chat_id \
                LEFT JOIN message_attachment_join maj ON maj.message_id = m.ROWID \
                LEFT JOIN attachment a ON a.ROWID = maj.attachment_id")
print("\033[32mDone!\033[0m")

print("\033[33mCopying contacts...\033[0m")
rows = get_data(sftp, "/private/var/mobile/Library/AddressBook/AddressBook.sqlitedb", "SELECT p.first, p.last, p.CreationDate, p.ModificationDate, m.value AS phone_number FROM ABPerson p JOIN ABMultiValue m ON p.ROWID = m.record_id")
print("\033[32mDone!\033[0m")

print("\033[33mCopying cached message attachments...\033[0m")
copy_with_progress(sftp, "/private/var/mobile/Library/SMS/Attachments", "Attachments")
print(f"\033[32m{fit_in_line('Done!')}\033[0m")

sftp.close()
client.close()
if USB:
    proc.terminate()

print("\033[33mDumping contact info...\033[0m")

contacts = {}
num_to_name = {}
for contact in rows:
    first, last, created, modified, num, deleted = contact[0], contact[1], ios_date(contact[2]), ios_date(contact[3]), clean_number(contact[4]), contact[5]
    if last is not None:
        num_to_name[num] = first + " " + last
        if first + " " + last not in contacts:
            contacts[first + " " + last] = {'methods': [], 'created': created, 'modified': modified}
        if num is not None:
            if not deleted:
                contacts[first + " " + last]['methods'].append(num)
            else:
                contacts[first + " " + last]['methods'].append(num + " (DELETED)")
    else:
        num_to_name[num] = first
        if first not in contacts:
            contacts[first] = {'methods': [], 'created': created, 'modified': modified}
        if num is not None:
            if not deleted:
                contacts[first]['methods'].append(num)
            else:
                contacts[first]['methods'].append(num + " (DELETED)")

with open("contacts_dump.txt", "w") as f:
    for contact in contacts:
        f.write(contact + ":\n")
        f.write("\tMethods of contact:\n")
        for m in contacts[contact]['methods']:
            f.write("\t\t" + m + "\n")
        f.write("\tDate added:\n")
        f.write("\t\t "+ contacts[contact]['created'] + "\n")
        f.write("\tLast modified:\n")
        f.write("\t\t "+ contacts[contact]['modified'] + "\n\n")

print("\033[32mDone!\033[0m")

print("\033[33mDumping iMessage/SMS conversations...\033[0m")

chats = {}
for msg in sms_rows:
    num, text, date, chat_id, group_name, style, from_me, attachment, cached_attachment_name, given_attachment_name, deleted = msg[0], msg[1], ios_date(msg[2] / 1000000000), msg[3], msg[4], msg[5], bool(msg[6]), msg[7], msg[8], msg[9], msg[10]

    if num in num_to_name and num is not None:
        name = num_to_name[num]
    elif num is not None:
        name = num
    else:
        name = "Protagonist"
    
    has_attachment = False
    if attachment and text is not None:
        cached_attachment_name = cached_attachment_name[14:]
        has_attachment = True
        if text[0] not in string.printable:
            text = (text[1:] + " (" + given_attachment_name + ")").strip()

    # 45 is for individual DMs and 43 is for group DMs (style)
    if style == 45:
        if name not in chats:
            chats[name] = {"type": "DM", "messages": [{"content": text, "date": date, "has_attachment": has_attachment, "img_location": cached_attachment_name, "img_name": given_attachment_name, "from_me": from_me, "deleted": deleted}]}
        else:
            chats[name]["messages"].append({"content": text, "date": date, "has_attachment": has_attachment, "img_location": cached_attachment_name, "img_name": given_attachment_name, "from_me": from_me, "deleted": deleted})
    elif style == 43:
        if group_name != '':
            gc = group_name
        else:
            gc = "unnamed_group_" + str(chat_id)

        if gc not in chats:
            chats[gc] = {"type": "GC", "participants": [name], "messages": [{"content": text, "date": date, "has_attachment": has_attachment, "img_location": cached_attachment_name, "img_name": given_attachment_name, "from_me": from_me, "sender": name, "deleted": deleted}]}
        else:
            chats[gc]["messages"].append({"content": text, "date": date, "has_attachment": has_attachment, "img_location": cached_attachment_name, "img_name": given_attachment_name, "from_me": from_me, "sender": name, "deleted": deleted})
            if name not in chats[gc]["participants"]:
                chats[gc]["participants"].append(name)      

os.mkdir("convos")
os.chdir("convos")
for c in chats:
    os.mkdir(c)
    os.chdir(c)
    os.mkdir("attachments")
    chats[c]["messages"] = sorted(chats[c]["messages"], key=lambda x: x["date"])
    with open("messages.txt", "w", encoding="utf-8") as f:
        if chats[c]["type"] == "GC":
            f.write("Participants:\n")
            for p in chats[c]["participants"]:
                f.write(p + "\n")
            f.write("\n")

        for m in chats[c]["messages"]:
            if m["content"] is not None:
                if m["deleted"]:
                    f.write("(DELETED) ")
                if m["from_me"]:
                    f.write("Protagonist (" + m["date"] + "): " + m["content"] + "\n")
                else:
                    if chats[c]["type"] == "DM":
                        f.write(c + " (" + m["date"] + "): " + m["content"] + "\n")
                    else:
                        f.write(m["sender"] + " (" + m["date"] + "): " + m["content"] + "\n")

                if m["has_attachment"]:
                    try:
                        shutil.move("../../" + m["img_location"], "attachments/" + m["img_name"])
                    except:
                        pass
    os.chdir("..")

print("\033[32mDone!\033[0m")

print("\033[33mCleaning up...\033[0m")
shutil.rmtree("../Attachments")
os.chdir("..")
os.remove("AddressBook.sqlitedb")
os.remove("sms.db")

print("\033[32mDone!\033[0m")