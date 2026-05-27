<div align="center">

# Automated Data Relay Pipeline untuk SPARING KLHK

**Sistem pengiriman data pemantauan kualitas air limbah industri secara otomatis ke server SPARING Kementerian Lingkungan Hidup dan Kehutanan (KLHK) Republik Indonesia.**

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.x-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Docker](https://img.shields.io/badge/Docker-aqliserdadu%2Fklh-2496ED?logo=docker&logoColor=white)](https://hub.docker.com/r/aqliserdadu/klh)
[![MySQL](https://img.shields.io/badge/MySQL-8.x-4479A1?logo=mysql&logoColor=white)](https://www.mysql.com/)
[![Platform](https://img.shields.io/badge/Platform-Linux-FCC624?logo=linux&logoColor=black)](https://www.linux.org/)
[![Regulation](https://img.shields.io/badge/Regulasi-Permen%20LHK%20P.93%2F2018-green)](https://sparing.kemenlhk.go.id)

</div>

---

## Table of Contents

- [About the Project](#-about-the-project)
- [Built With](#-built-with)
- [System Architecture](#-system-architecture--alur-data)
- [Database Schema](#-database-schema)
- [Getting Started](#-getting-started)
  - [Prerequisites](#prerequisites)
  - [Installation (Docker)](#installation--docker-recommended)
  - [Installation (Manual)](#installation--manual)
  - [Environment Configuration](#environment-configuration)
- [Usage](#-usage)
  - [Menjalankan Script Manual](#menjalankan-script-manual)
  - [Konfigurasi Crontab](#konfigurasi-crontab)
  - [Struktur Log](#struktur-log)
- [Roadmap](#-roadmap)
- [License & Contact](#-license--contact)

---

## About the Project

Proyek ini adalah **automated data relay pipeline** yang dirancang untuk memenuhi kewajiban pelaporan regulasi **SPARING (Sistem Pemantauan Air secara Real-Time)** sesuai **Peraturan Menteri LHK No. P.93/MENLHK/SETJEN/KUM.1/8/2018** tentang pemantauan kualitas air limbah industri secara daring.

### Permasalahan yang Dipecahkan

Industri yang diwajibkan memasang alat ukur kualitas air limbah menghadapi tantangan teknis:

1. **Sensor/Datalogger** menyimpan data ke file CSV pada folder FTP lokal secara periodik — format dan header bervariasi antar merek/model.
2. Data harus dikirim ke **API server KLHK** setiap jam dalam format JSON yang di-enkapsulasi JWT, dengan jendela waktu ketat.
3. Gangguan jaringan atau respons API yang tidak normal (duplikasi, timeout) dapat menyebabkan kehilangan data pelaporan.
4. Data **kalibrasi sensor** (ditandai dengan menit ganjil) harus difilter dan tidak boleh masuk ke laporan.

### Solusi Teknis

Pipeline ini mengotomatisasi seluruh proses dari **pembacaan CSV → normalisasi → penyimpanan sementara → pengiriman JWT-authenticated → verifikasi → arsip**, dengan mekanisme retry cerdas untuk menangani duplikasi dan kegagalan jaringan.

---

## Built With

| Komponen | Teknologi | Keterangan |
|---|---|---|
| Runtime | Python 3.x | Scripting engine utama |
| Database | MySQL 8.x | Penyimpanan data sementara & arsip |
| Autentikasi API | PyJWT (HS256) | Enkapsulasi payload JWT untuk SPARING API |
| HTTP Client | requests | Komunikasi dengan KLHK SPARING API |
| Timezone | pytz | Normalisasi waktu ke WIB (Asia/Jakarta) |
| Config Management | python-dotenv | Manajemen environment variable |
| Containerization | Docker | Packaging & deployment (image: `aqliserdadu/klh`) |
| Penjadwalan | Linux Crontab | Otomasi eksekusi periodik |
| File Transfer | FTP | Penerimaan file CSV dari sensor/datalogger |

### Parameter Kualitas Air yang Dipantau

| Parameter | Satuan | Keterangan |
|---|---|---|
| `pH` | — | Derajat keasaman air limbah |
| `TSS` | mg/L | Total Suspended Solids (padatan tersuspensi) |
| `COD` | mg/L | Chemical Oxygen Demand |
| `Debit` | m³/jam | Laju alir air limbah |
| `NH3-N` | mg/L | Konsentrasi amonia-nitrogen |

---

## System Architecture / Alur Data

```
┌─────────────────────────────────────────────────────────────────────┐
│                         EDGE / LAPANGAN                             │
│                                                                     │
│   ┌──────────────┐  CSV (setiap   ┌──────────────────────┐         │
│   │   Sensor /   │  interval)     │  FTP Folder          │         │
│   │  Datalogger  │ ─────────────► │  /home/FTP/*.csv     │         │
│   └──────────────┘                └──────────┬───────────┘         │
└──────────────────────────────────────────────┼─────────────────────┘
                                               │
                    ┌─────────── setiap 1 menit ┘
                    ▼
        ┌───────────────────────┐
        │  baca.py              │  • Parse & normalisasi header CSV
        │  (CSV Processor)      │  • Filter data kalibrasi (menit ganjil)
        │                       │  • Konversi nilai ke float, handle NaN
        └───────────┬───────────┘
                    │ INSERT
                    ▼
        ┌───────────────────────┐
        │  MySQL: tabel `tmp`   │  Buffer staging — data siap kirim
        │  (Staging Buffer)     │  status: NULL / 'retry' / 'Duplikasi'
        └───────────┬───────────┘
          ┌─────────┘
          │      setiap 1 jam (apiSend.py)
          │      setiap menit 4,8,12 (retryApiSend.py)
          ▼
┌─────────────────────────────┐
│  apiSend.py /               │  • Grouping data per jam
│  retryApiSend.py            │  • Encode payload → JWT HS256
│  (API Dispatcher)           │  • POST ke SPARING KLHK API
└───────────┬─────────────────┘
            │
     ┌──────┴──────────────────────────────────┐
     │  Response sukses          Response gagal │
     ▼                                         ▼
┌─────────────┐                   ┌────────────────────┐
│ MySQL:      │ COPY + DELETE     │ status='retry'     │ → retryApiSend.py
│ tabel `data`│ ◄── dari tmp      │ atau 'Duplikasi'   │   (max MAX_DUP_RETRY)
│ (Arsip)     │                   └────────────────────┘
└─────────────┘
            │
            ▼
 ┌─────────────────────────────────────┐
 │  SPARING API — KLHK Server          │
 │  https://sparing.kemenlh.go.id      │
 └─────────────────────────────────────┘
```

### Logika Penanganan Duplikasi

Ketika API KLHK mengembalikan respons `"duplikasi"`, sistem secara otomatis:
1. Mengidentifikasi dan menghapus data duplikat dari tabel `tmp`.
2. Mengirim ulang data yang telah dibersihkan.
3. Membatasi percobaan ulang maksimum sebesar `MAX_DUP_RETRY` kali.
4. Jika batas terlampaui: menandai data sebagai `'Duplikasi'` untuk intervensi manual.

---

## Database Schema

### Tabel `tmp` (Staging Buffer)

```sql
CREATE TABLE tmp (
    id            INT AUTO_INCREMENT PRIMARY KEY,
    date          DATETIME,                    -- Timestamp interval sensor
    datetime      BIGINT       DEFAULT 0,      -- Unix timestamp (epoch)
    pH            FLOAT        DEFAULT 0,
    nh3n          FLOAT        DEFAULT 0,
    tss           FLOAT        DEFAULT 0,
    debit         FLOAT        DEFAULT 0,
    cod           FLOAT        DEFAULT 0,
    status        TEXT,                        -- NULL | 'retry' | 'terkirim' | 'Duplikasi'
    keterangan    TEXT,                        -- Pesan respons API
    dateterkirim  DATETIME                     -- Timestamp konfirmasi pengiriman
);
```

### Tabel `data` (Arsip Terkirim)

Skema identik dengan `tmp`. Data dipindahkan dari `tmp` → `data` setelah konfirmasi sukses dari API KLHK, lalu baris di `tmp` dihapus.

---

## Getting Started

### Prerequisites

| Kebutuhan | Versi Minimum | Catatan |
|---|---|---|
| Python | 3.8+ | Untuk instalasi manual |
| MySQL Server | 8.0+ | Dapat di-host di container Docker |
| Docker Engine | 20.10+ | Untuk deployment berbasis container |
| Akses FTP | — | Folder `/home/FTP` harus dapat ditulis sensor |
| Koneksi Internet | — | Akses ke `sparing.kemenlh.go.id` |

---

### Installation — Docker (Recommended)

Docker image `aqliserdadu/klh:2.0` sudah menyertakan MySQL, crontab, dan semua dependensi Python.

#### 1. Siapkan Direktori Host

```bash
# Buat direktori yang akan di-mount ke container
mkdir -p /home/$USER/FTP
mkdir -p /home/$USER/klh/config
mkdir -p /home/$USER/klh/LOG
```

#### 2. Clone Repositori (untuk konfigurasi & script)

```bash
git clone https://github.com/abakarbit/enviroflow-sparing.git /home/$USER/klh
cd /home/$USER/klh
```

#### 3. Konfigurasi Environment

```bash
# Salin template env dan isi dengan nilai yang sesuai
cp config/env config/.env
nano config/.env
```

> Lihat bagian [Environment Configuration](#environment-configuration) untuk detail setiap variabel.

#### 4. Jalankan Container

**Mode Bridge** (port terpetakan ke host, cocok untuk multi-container):

```bash
docker run -d \
  --restart=always \
  --name klh \
  -p 3306:3306 \
  -p 80:80 \
  -v /home/$USER/FTP:/home/FTP \
  -v /home/$USER/klh:/home/klh \
  -v /etc/localtime:/etc/localtime:ro \
  aqliserdadu/klh:2.0
```

**Mode Host** (performa lebih tinggi, cocok untuk deployment single-node):

```bash
docker run -d \
  --restart=always \
  --network host \
  --name klh \
  -v /home/$USER/FTP:/home/FTP \
  -v /home/$USER/klh:/home/klh \
  -v /etc/localtime:/etc/localtime:ro \
  aqliserdadu/klh:2.0
```

> **Catatan:** Pilih salah satu mode jaringan. Ganti `$USER` dengan nama folder yang sesuai di sistem Anda.

#### 5. Verifikasi Container

```bash
# Cek status container
docker ps -a --filter name=klh

# Pantau log container secara real-time
docker logs -f klh

# Masuk ke shell container untuk debugging
docker exec -it klh bash
```

---

### Installation — Manual

Gunakan metode ini jika tidak menggunakan Docker.

```bash
# 1. Clone repositori
git clone https://github.com/abakarbit/enviroflow-sparing.git
cd enviroflow-sparing

# 2. Buat virtual environment (disarankan)
python3 -m venv .venv
source .venv/bin/activate

# 3. Install dependensi Python
pip install mysql-connector-python requests PyJWT pytz python-dotenv

# 4. Konfigurasi environment
cp config/env config/.env
nano config/.env

```

---

### Environment Configuration

Buat file `config/.env` berdasarkan template `config/env`:

```bash
cp config/env config/.env
```

| Variabel | Tipe | Contoh Nilai | Keterangan |
|---|---|---|---|
| `BACACSV` | `int` | `1` | Aktifkan pembacaan CSV (`1`=aktif, `0`=nonaktif) |
| `APISEND` | `int` | `1` | Aktifkan pengiriman API (`1`=aktif, `0`=nonaktif) |
| `TIMEZONA` | `str` | `Asia/Jakarta` | Timezone pytz untuk normalisasi timestamp |
| `HOST` | `str` | `127.0.0.1` | Host MySQL server |
| `USERS` | `str` | `project` | Username koneksi MySQL |
| `PASSWORD` | `str` | `*****` | Password koneksi MySQL |
| `DATABASE` | `str` | `loger` | Nama database MySQL |
| `URL_API` | `str` | `https://sparing.kemenlh.go.id/api/send-hourly` | Endpoint pengiriman data SPARING |
| `URL_TOKEN` | `str` | `https://sparing.kemenlh.go.id/api/secret-sensor` | Endpoint pengambilan JWT secret |
| `UID` | `str` | `5f6322617c5fc71255fca135` | UID sensor terdaftar di sistem KLHK |
| `MAX_DUP_RETRY` | `int` | `3` | Maksimum percobaan ulang penanganan duplikasi |


---

## Usage

### Menjalankan Script Manual

```bash
# Membaca dan memproses file CSV dari folder FTP
python3 baca.py

# Mengirim data jam terakhir ke SPARING API
python3 apiSend.py

# Mengirim ulang data yang gagal (status='retry')
python3 retryApiSend.py
```

### Konfigurasi Crontab

Konfigurasi penjadwalan terdapat di `config/crontab`. Edit sesuai kebutuhan, lalu terapkan:

```
# Format: menit jam hari bulan hari-minggu perintah

# Baca CSV setiap 1 menit
* * * * * /path/to/python3 /home/klh/baca.py

# Kirim data ke API setiap awal jam
0 * * * * /path/to/python3 /home/klh/apiSend.py

# Retry pengiriman gagal di menit ke-4, 8, dan 12 setiap jam
4,8,12 * * * * /path/to/python3 /home/klh/retryApiSend.py
```

Untuk menonaktifkan proses tertentu tanpa menghapus entri, tambahkan `#` di awal baris:

```bash
# Contoh: menonaktifkan pembacaan CSV sementara
#* * * * * /path/to/python3 /home/klh/baca.py
```

> Dalam deployment Docker, crontab dikelola oleh image container secara otomatis berdasarkan file `config/crontab`.

### Struktur Log

Log operasional tersimpan di direktori `LOG/`:

```
LOG/
├── csvLog.txt    # Log aktivitas baca.py (pembacaan & parsing CSV)
└── apiLog.txt    # Log aktivitas apiSend.py & retryApiSend.py (pengiriman API)
```

**Format entri log:**

```
[YYYY-MM-DD HH:MM:SS] Pesan log di sini
```

**Contoh output log normal (`apiLog.txt`):**

```
[2026-05-27 08:00:01] Kirim data jam 2026-05-27 07:00:00 s/d 2026-05-27 07:58:00
[2026-05-27 08:00:03] Data berhasil dikirim ke API
[2026-05-27 08:00:03] Pesan Berhasil: {"status":true,"desc":"data berhasil disimpan"}
```

**Contoh penanganan duplikasi (`apiLog.txt`):**

```
[2026-05-27 09:00:02] Duplikasi ditemukan, memproses data duplikat...
[2026-05-27 09:00:02] Data duplikat 2026-05-27 08:30:00 telah dihapus dari database.
[2026-05-27 09:00:03] Mengambil ulang data kembali
[2026-05-27 09:00:05] Data berhasil dikirim ke API
```

---


## License & Contact

Proyek ini dilisensikan di bawah **MIT License** — lihat file [LICENSE](LICENSE) untuk detail.

### Maintainer

| | |
|---|---|
| **Author** | Abu Bakar |
| **Docker Hub** | [hub.docker.com/r/aqliserdadu/klh](https://hub.docker.com/r/aqliserdadu/klh) |
| **GitHub** | [github.com/abakarbit/enviroflow-sparing](https://github.com/abakarbit/enviroflow-sparing) |

---

<div align="center">

*Dibangun untuk kepatuhan lingkungan industri Indonesia · SPARING KLHK*

</div>
