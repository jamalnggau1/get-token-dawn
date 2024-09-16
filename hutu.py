import ast
import json
import re
import requests
import random
import time
import datetime
import urllib3
from PIL import Image, ImageOps
import base64
from io import BytesIO
import ddddocr
from loguru import logger

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

KeepAliveURL = "https://www.aeropres.in/chromeapi/dawn/v1/userreward/keepalive"
GetPointURL = "https://www.aeropres.in/api/atom/v1/userreferral/getpoint"
LoginURL = "https://www.aeropres.in//chromeapi/dawn/v1/user/login/v2"
PuzzleID = "https://www.aeropres.in/chromeapi/dawn/v1/puzzle/get-puzzle"

# Proxy configuration
proxies_list = [
    'http://xw50sxu0wbeq6vh:5xhgatxce08tjxf@51.159.85.23:6060',
    # Tambahkan proxy lain di sini jika perlu
]

# Membuat sesi permintaan dengan proxy
session = requests.Session()

def update_proxy():
    proxy = random.choice(proxies_list)
    session.proxies.update({
        'http': proxy,
        'https': proxy
    })
    logger.info(f'Menggunakan proxy: {proxy}')

update_proxy()

# Menetapkan header permintaan umum
headers = {
    "Content-Type": "application/json",
    "Origin": "chrome-extension://fpdkjdnhkakefebpekbdhillbhonfjjp",
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Priority": "u=1, i",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "cross-site",
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36"
}

# Function untuk mendapatkan Puzzle ID
def GetPuzzleID():
    try:
        r = session.get(PuzzleID, headers=headers, verify=False).json()
        puzzid = r['puzzle_id']
        return puzzid
    except Exception as e:
        logger.error(f'[x] Error saat mengambil PuzzleID: {e}')
        return None

# Memeriksa validitas CAPTCHA
def IsValidExpression(expression):
    pattern = r'^[A-Za-z0-9]{6}$'  # Pola CAPTCHA alfanumerik
    return bool(re.match(pattern, expression))

# Menyimpan gambar CAPTCHA yang gagal dikenali untuk analisis lebih lanjut
def save_captcha_image(image_data, count):
    with open(f"failed_captcha_{count}.png", "wb") as f:
        f.write(base64.b64decode(image_data))

# Pengenalan CAPTCHA
def RemixCaptacha(base64_image, attempt):
    try:
        image_data = base64.b64decode(base64_image)
        image = Image.open(BytesIO(image_data))

        # Konversi gambar ke grayscale
        image = image.convert('L')

        # Terapkan kontras otomatis
        image = ImageOps.autocontrast(image)

        # Terapkan thresholding untuk menghasilkan gambar biner (hitam-putih)
        threshold_value = image.getextrema()[1] // 2  # Nilai dinamis berdasarkan gambar
        binary_image = image.point(lambda p: p > threshold_value and 255)

        # Buat gambar baru yang bersih
        new_image = Image.new('L', binary_image.size, 'white')
        width, height = binary_image.size
        for x in range(width):
            for y in range(height):
                pixel = binary_image.getpixel((x, y))
                if pixel == 0:  # Hanya pixel hitam yang dipertahankan
                    new_image.putpixel((x, y), 0)

        # Lakukan OCR
        ocr = ddddocr.DdddOcr(show_ad=False)
        result = ocr.classification(new_image)
        
        logger.debug(f'[1] Hasil OCR CAPTCHA: {result}, valid: {IsValidExpression(result)}')

        if IsValidExpression(result):
            return result
        else:
            save_captcha_image(base64_image, attempt)
            logger.error(f'[x] CAPTCHA tidak valid, menyimpan gambar untuk analisis.')
            return None
    except Exception as e:
        logger.error(f'[x] Error pada RemixCaptacha: {e}')
        return None

# Fungsi untuk memeriksa validitas token
def is_token_valid(token):
    return token is not None and len(token) > 0

def login(USERNAME, PASSWORD):
    puzzid = GetPuzzleID()
    if not puzzid:
        return None
    
    current_time = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='milliseconds').replace("+00:00", "Z")
    data = {
        "username": USERNAME,
        "password": PASSWORD,
        "logindata": {
            "_v": "1.0.7",
            "datetime": current_time
        },
        "puzzle_id": puzzid,
        "ans": "0"
    }

    # CAPTCHA recognition
    for attempt in range(5):  # Coba hingga 5 kali
        try:
            refresh_image = session.get(f'https://www.aeropres.in/chromeapi/dawn/v1/puzzle/get-puzzle-image?puzzle_id={puzzid}', headers=headers, verify=False).json()
            code = RemixCaptacha(refresh_image['imgBase64'], attempt)

            if code:
                logger.success(f'[√] Berhasil mendapatkan hasil CAPTCHA {code}')
                data['ans'] = str(code)
                login_data = json.dumps(data)
                logger.info(f'[2] Data login: {login_data}')
                r = session.post(LoginURL, data=login_data, headers=headers, verify=False).json()
                logger.debug(r)
                token = r['data']['token']
                if is_token_valid(token):
                    logger.success(f'[√] Berhasil mendapatkan AuthToken {token}')
                    # Menyimpan token ke file
                    with open('token.txt', 'w') as f:
                        f.write(token)
                    return token
                else:
                    logger.error(f'[x] Token tidak valid diterima.')
        except Exception as e:
            logger.error(f'[x] Error saat login: {e}')
    logger.error('[x] Gagal login setelah beberapa kali percobaan.')
    return None

def KeepAlive(USERNAME, TOKEN):
    data = {"username": USERNAME, "extensionid": "fpdkjdnhkakefebpekbdhillbhonfjjp", "numberoftabs": 0, "_v": "1.0.7"}
    json_data = json.dumps(data)
    headers['authorization'] = "Bearer " + str(TOKEN)
    try:
        r = session.post(KeepAliveURL, data=json_data, headers=headers, verify=False).json()
        logger.info(f'[3] Menjaga koneksi tetap aktif... {r}')
    except Exception as e:
        logger.error(f'[x] Error saat KeepAlive: {e}')

def GetPoint(TOKEN):
    headers['authorization'] = "Bearer " + str(TOKEN)
    try:
        # Rotasi proxy setiap kali mengambil poin
        update_proxy()
        r = session.get(GetPointURL, headers=headers, verify=False).json()
        logger.success(f'[√] Berhasil mendapatkan Point {r}')
    except Exception as e:
        logger.error(f'[x] Error saat mendapatkan poin: {e}')

def main(USERNAME, PASSWORD):
    TOKEN = ''
    while True:  # Terus coba login hingga berhasil
        if not is_token_valid(TOKEN):
            TOKEN = login(USERNAME, PASSWORD)
            if not TOKEN:
                logger.error('[x] Gagal login, mencoba kembali dalam 5 detik...')
                time.sleep(5)  # Tunda sebelum mencoba login lagi
                continue

        count = 0
        max_count = 200
        while True:
            try:
                KeepAlive(USERNAME, TOKEN)
                GetPoint(TOKEN)
                count += 1

                # Menambahkan jeda 30-60 detik antara pengambilan poin
                delay = random.randint(30, 60)
                logger.info(f'Menunggu {delay} detik sebelum mengambil poin berikutnya...')
                time.sleep(delay)

                if count >= max_count:
                    logger.debug(f'[√] Memperbarui Token...')
                    TOKEN = login(USERNAME, PASSWORD)
                    count = 0
            except Exception as e:
                logger.error(e)
                logger.error('[x] Terjadi kesalahan, mencoba kembali dalam 5 detik...')
                time.sleep(5)  # Tunda sebelum mencoba kembali

if __name__ == '__main__':
    try:
        with open('password.txt', 'r') as f:
            username, password = f.readline().strip().split(':')
        main(username, password)
    except FileNotFoundError:
        logger.error('[x] File password.txt tidak ditemukan.')
    except ValueError:
        logger.error('[x] Format file password salah, harus dalam format username:password.')
