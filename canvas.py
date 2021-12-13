from PIL import Image
import requests
from io import BytesIO
import os
import re
import hashlib
import random
import sys
import traceback
from multiprocessing import Process, Lock
import time
dir = os.path.dirname(os.path.realpath(__file__))

REF_URL = 'https://raw.githubusercontent.com/Klemek/klemek/main/ref.png'
URL = 'http://challs.xmas.htsp.ro:3002/'
W = 320
H = 240

cached_targets = []
lock = Lock() 

def convert24to16(r, g, b):
    return (r >> 3, g >> 3, b >> 3)

def diff(ref, col):
    ref, col = convert24to16(*ref), convert24to16(*col)
    return sum(abs(ref[i] - col[i]) for i in range(3))

def get_next_pixel():
    global cached_targets
    headers = {
        "Cache-Control": "no-cache",
        "Pragma": "no-cache"
    }
    r = requests.get(f"{REF_URL}", headers=headers)
    ref_img = Image.open(BytesIO(r.content))
    r = requests.get(f"{URL}/canvas.png", headers=headers)
    lock.acquire()
    if r.status_code != 200:
        print(f"cannot get ref image: {r.status_code} {r.reason}")
    else:
        with open(f"{dir}/dist.png", mode='wb') as f:
            f.write(r.content)
    lock.release()
    targets = cached_targets
    total = sum(1 if ref_img.getpixel((x, y))[3] > 0 else 0 for x in range(W) for y in range(H))
    try:
        dist_img = Image.open(f"{dir}/dist.png").convert(mode='RGB')
        targets = []
        for x in range(W):
            for y in range(H):
                ref_color = ref_img.getpixel((x, y))
                dist_color = dist_img.getpixel((x * 2, y * 2))
                if ref_color[3] > 0 and diff(ref_color[:3], dist_color) > 5:
                    targets += [(x, y, ref_color[:3], dist_color)]
    except OSError:
        print("using cached targets")
    if len(targets) == 0:
        print("no pixel to update")
        return None
    else:
        cached_targets = targets
        x, y, ref_color, dist_color = random.choice(targets)
        print(f"pixel {x},{y} is {dist_color} and should be {ref_color} (1 of {len(targets)}/{total})({(total-len(targets))/total:.2%})")
        return x, y, f"{ref_color[0]:02x}{ref_color[1]:02x}{ref_color[2]:02x}".upper()

def get_challenge():
    body = {
        "action":"get_work"
    }
    r = requests.post(f"{URL}/api", data=body)
    if r.status_code == 200:
        data = r.content.decode("utf-8")
        res = re.search(r"Your salt is (\w+). Find a string that starts with this salt and whose md5 hash starts with: (\w+)", data)
        print(f"got challenge: salt={res[1]} md5={res[2]}")
        return res[1], res[2], r.cookies['PHPSESSID']
    else:
        print(f"cannot get challenge: {r.status_code} {r.reason}")
        return None


charset = 'abcdefghijklmnopqrstuvwxyz0123456789_'


def inc(p):
    if p[-1] != '_':
        return p[:-1] + charset[charset.index(p[-1]) + 1]
    elif len(p) == 1:
        return 'aa'
    else:
        return inc(p[:-1]) + 'a'


def solve_challenge(challenge):
    salt, md5, _ = challenge
    current = 'a'
    i = 0
    t0 = time.time()
    while True:
        hash = hashlib.md5((salt+current).encode('ascii')).hexdigest()
        i += 1
        if hash.startswith(md5):
            dt = time.time() - t0
            print(f"solved challenge: {current} {i:,} {dt:.3f}s {i/dt:,.3f}/s")
            return current
        current = inc(current)


def paint(pixel_data, challenge, answer):
    x, y, color = pixel_data
    body = {
        "action": "paint",
        "work": answer,
        "x": x,
        "y": y,
        "color": color,
        "team": 360
    }
    r = requests.post(f"{URL}/api", data=body, cookies={"PHPSESSID": challenge[2]})
    if r.status_code == 200:
        print(r.content)
    else:
        print(f"cannot update pixel: {r.status_code} {r.reason}")


def work():
    while True:
        try:
            challenge = get_challenge()
            if challenge is None:
                continue
            answer = solve_challenge(challenge)
            pixel_data = get_next_pixel()
            if pixel_data is None:
                continue
            paint(pixel_data, challenge, answer)
        except KeyboardInterrupt:
            sys.exit(0)
        except Exception as e:
            traceback.print_exc()


if __name__ == '__main__':
    for p in range(8):
        Process(target=work).start()