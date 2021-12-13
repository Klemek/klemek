from PIL import Image
import requests
from io import BytesIO
import os
import os.path
import re
import hashlib
import random
import sys
import traceback
from multiprocessing import Process, RLock, RawValue, RawArray
from ctypes import c_int
import time
dir = os.path.dirname(os.path.realpath(__file__))

REF_URL = 'https://raw.githubusercontent.com/Klemek/klemek/main/ref.png'
URL = 'http://challs.xmas.htsp.ro:3002/'
W = 320
H = 240
TIMEOUT = 10
TARGET_LENS = 10000
CHALLENGE_FILE = f"{dir}/challenges.csv"
PIXEL_THRESHOLD = 1

class Data:
    def __init__(self) -> None:
        self.img_lock = RLock()
        self.targets_cursor = RawValue(c_int, 0)
        self.targets_cursor = 0
        self.cached_targets = [RawArray(c_int, TARGET_LENS) for _ in range(5)]
        self.t0_lock = RLock()
        self.t0 = RawValue(c_int, 0)
        self.challenge_lock = RLock()
    
    def is_time(self):
        with self.t0_lock:
            t1 = int(time.time())
            if t1 - self.t0.value > TIMEOUT:
                self.t0.value = t1
                return True
            return False

    
    def get_random_cached_target(self):
        with self.img_lock:
            size = self.targets_cursor
            if size >= PIXEL_THRESHOLD:
                index = random.randint(0, size - 1)
                x = self.cached_targets[0][index]
                y = self.cached_targets[1][index]
                r = self.cached_targets[2][index]
                g = self.cached_targets[3][index]
                b = self.cached_targets[4][index]
                for i in range(5):
                    self.cached_targets[i][index] = self.cached_targets[i][size - 1]
                self.targets_cursor = size - 1
                return (x, y, f"{r:02x}{g:02x}{b:02x}".upper()), size - 1
        return None, 0

    def save_targets(self, targets):
        with self.img_lock:
            self.targets_cursor = len(targets)
            if self.targets_cursor > 0:
                self.cached_targets[0][:self.targets_cursor] = [x for x,_,_ in targets]
                self.cached_targets[1][:self.targets_cursor] = [y for _,y,_ in targets]
                self.cached_targets[2][:self.targets_cursor] = [c[0] for _,_,c in targets]
                self.cached_targets[3][:self.targets_cursor] = [c[1] for _,_,c in targets]
                self.cached_targets[4][:self.targets_cursor] = [c[2] for _,_,c in targets]
    
    def get_stored_challenge(self):
        if os.path.exists(CHALLENGE_FILE):
            with self.challenge_lock:
                lines = []
                with open(CHALLENGE_FILE) as f:
                    lines = f.readlines()
                if len(lines) > 0:
                    with open(CHALLENGE_FILE, mode='w') as f:
                        f.writelines(lines[1:])
                    data = lines[0].strip().split(',')
                    return data[:3], data[3], len(lines) - 1
        return None, None, 0

    def store_challenge(self, challenge, answer):
        with self.challenge_lock:
            with open(CHALLENGE_FILE, mode='a') as f:
                f.write('\n' + ','.join(challenge + (answer,)))
            with open(CHALLENGE_FILE) as f:
                return len(f.readlines())


def convert24to16(r, g, b):
    return (r >> 3, g >> 3, b >> 3)

def diff(ref, col):
    ref, col = convert24to16(*ref), convert24to16(*col)
    return sum(abs(ref[i] - col[i]) for i in range(3))

def get_next_pixel(data):
    headers = {
        "Cache-Control": "no-cache",
        "Pragma": "no-cache"
    }
    r = requests.get(f"{REF_URL}", headers=headers)
    ref_img = Image.open(BytesIO(r.content))
    total = sum(1 if ref_img.getpixel((x, y))[3] > 0 else 0 for x in range(W) for y in range(H))
    if data.is_time():
        r = requests.get(f"{URL}/canvas.png", headers=headers)
        if r.status_code == 200:
            try:
                dist_img = Image.open(BytesIO(r.content)).convert(mode='RGB')
                targets = []
                for x in range(W):
                    for y in range(H):
                        ref_color = ref_img.getpixel((x, y))
                        dist_color = dist_img.getpixel((x * 2, y * 2))
                        if ref_color[3] > 0 and diff(ref_color[:3], dist_color) > 5:
                            targets += [(x, y, ref_color[:3])]
                data.save_targets(targets)
            except OSError:
                pass
    target, remaining = data.get_random_cached_target()
    if target is None:
        print(f"[{os.getpid()}] no enough pixel to update")
        return None
    else:
        x, y, color = target
        print(f"[{os.getpid()}] pixel to update : {x},{y} => {color} (remaining {remaining}/{total}) ({(total-remaining)/total:.2%} done)")
        return target

def get_challenge():
    body = {
        "action":"get_work"
    }
    r = requests.post(f"{URL}/api", data=body)
    if r.status_code == 200:
        data = r.content.decode("utf-8")
        res = re.search(r"Your salt is (\w+). Find a string that starts with this salt and whose md5 hash starts with: (\w+)", data)
        print(f"[{os.getpid()}] got challenge: salt={res[1]} md5={res[2]}")
        return res[1], res[2], r.cookies['PHPSESSID']
    else:
        print(f"[{os.getpid()}] cannot get challenge: {r.status_code} {r.reason}")
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
    h0 = hashlib.md5(salt.encode('ascii'))
    i = 0
    t0 = time.time()
    h = h0.copy()
    while not h.hexdigest().startswith(md5):
        h = h0.copy()
        current = inc(current)
        h.update(current.encode('ascii'))
        i += 1
    dt = time.time() - t0
    print(f"[{os.getpid()}] solved challenge: {current} count={i:,} time={dt:.3f}s speed={i/dt:,.3f}/s")
    return current
        


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
        print(f"[{os.getpid()}] {r.content.decode('utf-8')}")
    else:
        print(f"[{os.getpid()}] cannot update pixel: {r.status_code} {r.reason}")


def work(data):
    while True:
        try:
            challenge = None
            answer = None
            pixel_data = get_next_pixel(data)
            if pixel_data:
                challenge, answer, remaining = data.get_stored_challenge()
                if challenge is not None:
                    print(f"[{os.getpid()}] using cached challenge, remaining={remaining}")
            if challenge is None:
                challenge = get_challenge()
                if challenge is None:
                    continue
                answer = solve_challenge(challenge)
            if pixel_data is None:
                total =data.store_challenge(challenge, answer)
                print(f"[{os.getpid()}] caching challenge, total={total}")
            else:
                paint(pixel_data, challenge, answer)
        except KeyboardInterrupt:
            sys.exit(0)
        except Exception as e:
            traceback.print_exc()


if __name__ == '__main__':
    n_threads = int(os.environ['N']) if 'N' in os.environ else 8
    data = Data()
    processes = [Process(target=work, args=(data,)) for _ in range(n_threads)]
    for p in processes:
        p.start()