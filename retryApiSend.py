import time
import mysql.connector
from datetime import datetime
from collections import defaultdict
import pytz
import requests
import json
import jwt
import os
from dotenv import load_dotenv

# Tentukan path file .env di subfolder 'config'
env_path = "/home/klh/config/.env"  # Menunjukkan file .env dalam subfolder 'config'

# Memuat variabel lingkungan dari file .env
load_dotenv(dotenv_path=env_path)

APISEND = int(os.getenv('APISEND'))

HOST = os.getenv('HOST')
USER = os.getenv('USERS')
PASSWORD = os.getenv('PASSWORD')
DATABASE = os.getenv('DATABASE')
TIMEZONA = os.getenv('TIMEZONA')

API_ENDPOINT = os.getenv('URL_API')  # Ganti dengan URL API Anda
API_JWT = os.getenv('URL_TOKEN')
UID = os.getenv('UID')

MAX_DUP_RETRY = int(os.getenv('MAX_DUP_RETRY'))   # batasan terjadi perulangan script duplikasi agar tidak terus menerus
duplicate_attempt=0
# Konfigurasi koneksi database MySQL
MYSQL_CONFIG = {
    'host': HOST,         # ganti dengan host MySQL Anda
    'user': USER,         # ganti dengan username MySQL Anda
    'password': PASSWORD, # ganti dengan password MySQL Anda
    'database': DATABASE  # ganti dengan nama database MySQL Anda
}

# Timezone
tz = pytz.timezone(TIMEZONA)


# Konfigurasi endpoint API, folder data, dan path database
def write_log(message):
    folder = "/home/klh/LOG/apiLog.txt"
    timestamp = datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S")
    with open(folder, "a") as log_file:
        log_file.write(f"[{timestamp}] {message}\n")

def get_jwt_token():
    try:
        # Kirim permintaan GET ke API untuk mendapatkan token
        response = requests.get(API_JWT)

        # Cek jika response sukses (status code 200)
        if response.status_code == 200:
            # Misalnya token ada di dalam JSON response seperti: {"token": "your_token_value"}
            jwt_token = response.text.strip()

            if jwt_token:
                print(f"Token JWT berhasil didapatkan: {jwt_token}")
                return jwt_token
            else:
                print("Token tidak ditemukan dalam response.")
                write_log("Token tidak ditemukan dalam response.")
                return None
        else:
            print(f"Gagal mendapatkan token, status code: {response.status_code}")
            write_log(f"Gagal mendapatkan token, status code: {response.status_code}")
            return None
    except requests.exceptions.RequestException as e:
        print(f"Terjadi error saat menghubungi API: {e}")
        write_log(f"Terjadi error saat menghubungi API: {e}")
        return None


def ambil_data():
    now = datetime.now(tz)
    print(now)
    conn = None
    cursor = None
    try:
        # Menggunakan context manager untuk koneksi dan cursor
        conn = mysql.connector.connect(**MYSQL_CONFIG)
        cursor = conn.cursor()

        # Eksekusi query untuk mengambil data dari tabel
        cursor.execute("SELECT date, datetime, pH, tss, cod, debit, nh3n FROM tmp WHERE status='retry' AND date < %s", [now])
        rows = cursor.fetchall()
        

        if not rows:
            print("Tidak ada data yang perlu dikirim.")
            write_log("Tidak ada data yang perlu dikirim.")
            return  # Tidak ada data yang ditemukan


        # Dictionary untuk menyimpan data yang dikelompokkan berdasarkan jam
        grouped_data = defaultdict(list)

        #Proses setiap baris data untuk mengelompokkan berdasarkan tanggal dan jam
        for row in rows:
            timestamp = row[0]  # timestamp ada di kolom pertama, sesuaikan dengan struktur query Anda
            # Dapatkan tanggal dalam format YYYY-MM-DD dan jam (hour)
            date_str = timestamp.strftime('%Y-%m-%d')  # Mengambil tanggal dalam format YYYY-MM-DD
            hour = timestamp.hour  # Ambil jam dari timestamp
            
            # Gabungkan tanggal dan jam sebagai kunci
            key = f"{date_str} {hour}:00"
            
            # Tambahkan data ke dalam kelompok berdasarkan kunci (tanggal + jam)
            grouped_data[key].append(row)

        # Tampilkan hasil pengelompokan dengan rentang waktu
        
        for key, data in grouped_data.items():
            # Ambil waktu awal dan waktu akhir untuk setiap grup
            start_time = min(entry[0] for entry in data)  # Ambil timestamp terkecil (awal)
            end_time = max(entry[0] for entry in data)    # Ambil timestamp terbesar (akhir)
            
            # Format rentang waktu dalam format yang diinginkan
            start = start_time.strftime('%Y-%m-%d %H:%M:%S')
            end = end_time.strftime('%Y-%m-%d %H:%M:%S')
            
            # Menyusun dictionary untuk grup tersebut
            group =[
                    {
                        "datetime": entry[1],
                        "pH": entry[2],
                        "tss": entry[3],
                        "cod": entry[4],
                        "debit": entry[5],
                        "nh3n": entry[6]
                    }
                    for entry in data
                ]
                        
            send_data_to_api(group, start, end,duplicate_attempt)

    except mysql.connector.Error as db_err:
        print(f"[{datetime.now()}] Error pada koneksi database: {db_err}")
        write_log(f"Error pada koneksi database: {db_err}")
    except Exception as e:
        print(f"[{datetime.now()}] Terjadi kesalahan: {e}")
        write_log(f"Terjadi kesalahan: {e}")
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

def send_data_to_api(data, start, end,duplicate_attempt):
    
    print(f"Kirim data retry jam {start} s/d {end}")
    write_log(f"Kirim data retry jam {start} s/d {end}")
    
    conn = None
    cursor = None
    try:
        # Membuka koneksi dan cursor
        conn = mysql.connector.connect(**MYSQL_CONFIG)
        cursor = conn.cursor()

        if not data:
            print("Tidak ada data yang perlu dikirim.")
            write_log("Tidak ada data yang perlu dikirim.")
            return  # Tidak ada data yang ditemukan

        json_data = data

        payload = {
            "uid": UID,  # Ganti 'kode' dengan nilai UID yang sesuai
            "data": json_data
        }

        jwtHeader = {
            "alg": "HS256",
            "typ": "JWT"
        }

        keyToken = get_jwt_token()
        if not keyToken:
            print("Tidak dapat melanjutkan, token JWT tidak ditemukan.")
            write_log("Tidak dapat melanjutkan, token JWT tidak ditemukan.")
            return

        enc = jwt.encode(payload, keyToken, algorithm='HS256', headers=jwtHeader)
        print("Payload JWT:", json.dumps(payload, default=str, indent=4))
        print("Encoded JWT:", enc)

        headers = {'Authorization': f'Bearer {keyToken}', 'Content-Type': 'application/json'}
        response = requests.post(API_ENDPOINT, json={"token": enc}, headers=headers)

        response_data = response.json()

        if response_data["status"]:
            print("Data berhasil dikirim ke API")
            write_log("Data berhasil dikirim ke API")
            print(f"Pesan Berhasil: {response.text}")
            write_log(f"Pesan Berhasil: {response.text}")

            datekirim = datetime.now(tz)
            # Update waktu kirim jika berhasil
            cursor.execute("UPDATE tmp SET dateterkirim=%s, status='terkirim', keterangan='sukses' WHERE date >=%s AND date <=%s", [datekirim, start, end])

            # Salin data
            cursor.execute("INSERT INTO data (date, datetime, pH, tss, cod, debit, nh3n, status, keterangan, dateterkirim) SELECT date, datetime, pH, tss, cod, debit, nh3n, status, keterangan, dateterkirim FROM tmp WHERE date >=%s AND date <=%s", [start, end])

            # Hapus data yang sudah disalin
            cursor.execute("DELETE FROM tmp WHERE date >=%s AND date <=%s", [start, end])

            conn.commit()
        else:
            print(f"Gagal mengirim data, status: {response_data['desc']}")
            write_log(f"Gagal mengirim data, status: {response_data['desc']}")
            write_log(f"Pesan error: {response.text}")

            if "duplikasi" in response_data["desc"].lower():
                print("Duplikasi ditemukan, memproses data duplikat...")
                write_log("Duplikasi ditemukan, memproses data duplikat...")
                
                duplicate_attempt += 1
                if duplicate_attempt >= MAX_DUP_RETRY:
                    print(f"Duplikasi terdeteksi {duplicate_attempt} kali, menghentikan percobaan...")
                    write_log(f"Duplikasi terdeteksi {duplicate_attempt} kali, menghentikan percobaan...")
                    try:
                        # Membuka koneksi dan cursor untuk update status
                        with mysql.connector.connect(**MYSQL_CONFIG) as conn:
                            with conn.cursor() as cursor:
                                cursor.execute("UPDATE tmp SET status='Duplikasi', keterangan='Duplikasi tidak teratasi, lakukan manual check' WHERE date >=%s AND date <=%s", [start, end])
                                conn.commit()
                    except mysql.connector.Error as db_err:
                        write_log(f"Error saat mencoba update status duplikasi di database: {db_err}")
                    finally:
                        if cursor:
                            cursor.close()
                        if conn:
                            conn.close()    
                    return           #keluar

                for timestamp in response_data["data"]:
                    cursor.execute("SELECT 1 FROM tmp WHERE date = %s", [timestamp])
                    existing_record = cursor.fetchone()

                    if existing_record:
                        cursor.execute("DELETE FROM tmp WHERE date = %s", [timestamp])
                        write_log(f"Data duplikat {timestamp} telah dihapus dari database.")
                        print(f"Data duplikat {timestamp} telah dihapus dari database.")

                conn.commit()
                write_log(f"Data duplikat telah dihapus dari database.")
                print(f"Data duplikat telah dihapus dari database.")

                
                print(f"Mengambil ulang data kembali")
                write_log(f"Mengambil ulang data kembali")
                
                
                # Mengirim ulang data jika duplikasi
                #mengambil data baru setelah duplikasi di hapus
                cursor.execute("SELECT datetime, ph, tss, cod, debit, nh3n FROM tmp  WHERE date >=%s AND date <=%s", [start, end])
                rows = cursor.fetchall()
                conn.commit()
                
                if not rows:
                    print("Tidak ada data yang perlu dikirim, setelah penghapusan duplikasi")
                    write_log("Tidak ada data yang perlu dikirim, setelah penghapusan duplikasi")
                    return  # Tidak ada data yang ditemukan, keluar dari send api

                # Ambil nama kolom dari hasil query
                
                columns = [desc[0] for desc in cursor.description]

                # Konversi hasil query ke dalam format JSON
                json_data = [dict(zip(columns, row)) for row in rows]
                        
        
                send_data_to_api(json_data, start, end, duplicate_attempt)
   
            else:
                cursor.execute("UPDATE tmp SET status='retry', keterangan=%s WHERE date >=%s AND date <=%s", [response.text, start, end])
                conn.commit()

    except mysql.connector.Error as db_err:
        print(f"[{datetime.now()}] Error pada koneksi database: {db_err}")
        write_log(f"Error pada koneksi database: {db_err}")
    except Exception as e:
        print(f"[{datetime.now()}] Terjadi kesalahan: {e}")
        write_log(f"Terjadi kesalahan: {e}")
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


if __name__ == "__main__":
    
    if APISEND == 1:
        ambil_data()
    else:
        write_log("Kirim Data Sedang Tidak Aktif")
