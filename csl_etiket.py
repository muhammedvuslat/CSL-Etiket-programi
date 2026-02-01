import customtkinter as ctk
import sqlite3
import qrcode
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import mm
from PIL import Image, ImageTk
from tkinter import filedialog, messagebox
import uuid
import random
import string
from datetime import datetime
import os
import hashlib
import threading
import tempfile
import shutil
import time
import sys
import subprocess

# Rol çevirisi
ROL_DISPLAY = {
    'admin': 'Admin',
    'takim_lideri': 'Takım Lideri',
    'vardiya_amiri': 'Vardiya Amiri',
    'kontrol_elemeni': 'Kontrol Elemanı'
}

ROL_REVERSE = {
    'Admin': 'admin',
    'Takım Lideri': 'takim_lideri',
    'Vardiya Amiri': 'vardiya_amiri',
    'Kontrol Elemanı': 'kontrol_elemeni'
}

# Veritabanı bağlantısı
# İlk kez program dizininde açıp ayarlardan DB yolunu oku
initial_db_path = os.path.abspath('personel.db')
conn = sqlite3.connect(initial_db_path, check_same_thread=False)
cursor = conn.cursor()

# Tablo oluşturma
cursor.execute('''
CREATE TABLE IF NOT EXISTS personel (
    id INTEGER PRIMARY KEY,
    ad TEXT,
    soyad TEXT,
    vardiya TEXT,
    uuid TEXT UNIQUE,
    olusturma_tarihi TEXT
)
''')
cursor.execute('''
CREATE TABLE IF NOT EXISTS etiket (
    id INTEGER PRIMARY KEY,
    personel_id INTEGER,
    uuid TEXT UNIQUE,
    olusturma_tarihi TEXT,
    basan_kullanici_id INTEGER,
    FOREIGN KEY (personel_id) REFERENCES personel (id),
    FOREIGN KEY (basan_kullanici_id) REFERENCES kullanicilar (id)
)
''')
cursor.execute('''
CREATE TABLE IF NOT EXISTS kullanicilar (
    id INTEGER PRIMARY KEY,
    kullanici_adi TEXT UNIQUE,
    sifre TEXT,
    rol TEXT,
    olusturma_tarihi TEXT
)
''')
cursor.execute('''
CREATE TABLE IF NOT EXISTS personel_atama (
    id INTEGER PRIMARY KEY,
    vardiya_amiri_id INTEGER,
    personel_id INTEGER UNIQUE,
    atama_tarihi TEXT,
    FOREIGN KEY (vardiya_amiri_id) REFERENCES kullanicilar (id),
    FOREIGN KEY (personel_id) REFERENCES personel (id)
)
''')

# Etiket tablosuna basan_kullanici_id kolonu ekle (eğer yoksa)
try:
    cursor.execute("ALTER TABLE etiket ADD COLUMN basan_kullanici_id INTEGER")
    conn.commit()
except:
    pass

conn.commit()

# Veritabanı optimizasyonları - Index'ler ekle
try:
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_personel_ad_soyad ON personel(ad, soyad)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_kullanici_adi ON kullanicilar(kullanici_adi)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_etiket_uuid ON etiket(uuid)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_personel_atama_vardiya ON personel_atama(vardiya_amiri_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_personel_atama_personel ON personel_atama(personel_id)")
    conn.commit()
except Exception as e:
    pass

# Ayarlar tablosu (key-value)
cursor.execute('''
CREATE TABLE IF NOT EXISTS ayarlar (
    anahtar TEXT PRIMARY KEY,
    deger TEXT
)
''')
conn.commit()

# Varsayılan ayarlar
def get_setting(key, default=None):
    cursor.execute("SELECT deger FROM ayarlar WHERE anahtar = ?", (key,))
    r = cursor.fetchone()
    if r:
        return r[0]
    return default

def set_setting(key, value):
    cursor.execute("INSERT OR REPLACE INTO ayarlar (anahtar, deger) VALUES (?, ?)", (key, str(value)))
    conn.commit()

# Ayarlardan kaydedilmiş DB yolunu kontrol et; eğer varsa ve mevcut ise, ona taşı
saved_db_path = get_setting('db_path')
db_path = initial_db_path
if saved_db_path and os.path.exists(saved_db_path) and saved_db_path != initial_db_path:
    try:
        conn.close()
        conn = sqlite3.connect(saved_db_path, check_same_thread=False)
        cursor = conn.cursor()
        db_path = saved_db_path
    except Exception as e:
        # Eski DB'ye geri dön
        conn.close()
        conn = sqlite3.connect(initial_db_path, check_same_thread=False)
        cursor = conn.cursor()
        db_path = initial_db_path

# Oturum zaman aşımı (saniye) - default 5 dakika
db_session_timeout = int(get_setting('session_timeout_seconds', 300))

# Global session takip
session_last_activity = None
session_monitor_thread = None
session_monitor_running = False

def touch_session():
    global session_last_activity
    session_last_activity = datetime.now()

def session_monitor():
    global session_monitor_running
    session_monitor_running = True
    while session_monitor_running:
        try:
            if 'current_user' in globals() and current_user and current_user.get('id'):
                if session_last_activity:
                    elapsed = (datetime.now() - session_last_activity).total_seconds()
                    timeout = int(get_setting('session_timeout_seconds', db_session_timeout))
                    if elapsed > timeout:
                        # Oturum kapat
                        try:
                            root.after(0, lambda: messagebox.showinfo('Oturum Süresi Doldu', 'Oturumunuz süresi dolduğu için kapatıldı.'))
                            root.after(0, logout)
                        except Exception:
                            pass
            time.sleep(5)
        except Exception:
            time.sleep(5)

# Başlangıçta monitor'u başlat
def start_session_monitor():
    global session_monitor_thread
    if session_monitor_thread and session_monitor_thread.is_alive():
        return
    session_monitor_thread = threading.Thread(target=session_monitor, daemon=True)
    session_monitor_thread.start()

# Varsayılan admin hesabı oluştur
def create_default_admin():
    cursor.execute("SELECT id FROM kullanicilar WHERE kullanici_adi = 'admin'")
    if not cursor.fetchone():
        hashed_password = hashlib.sha256('admin123'.encode()).hexdigest()
        tarih = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("INSERT INTO kullanicilar (kullanici_adi, sifre, rol, olusturma_tarihi) VALUES (?, ?, ?, ?)",
                       ('admin', hashed_password, 'admin', tarih))
        conn.commit()

create_default_admin()


# Global kullanıcı bilgisi
current_user = {
    'id': None,
    'kullanici_adi': None,
    'rol': None
}

# Start session monitor now that current_user exists
# session monitor will be started after GUI (root) oluşturuldu

# Ana pencere
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")

root = ctk.CTk()
root.title("CSL Etiket Programı")
root.geometry("800x700")

# Şimdi session monitor'u başlat
start_session_monitor()

# Frame'ler
login_frame = ctk.CTkFrame(root)
menu_frame = ctk.CTkFrame(root)
personel_frame = ctk.CTkFrame(root)
bas_frame = ctk.CTkFrame(root)
kontrol_frame = ctk.CTkFrame(root)
ayarlar_frame = ctk.CTkFrame(root)
kullanici_yonetimi_frame = ctk.CTkFrame(root)
vardiya_amiri_yonetimi_frame = ctk.CTkFrame(root)
personel_atama_frame = ctk.CTkFrame(root)

for frame in [login_frame, menu_frame, personel_frame, bas_frame, kontrol_frame, ayarlar_frame, 
              kullanici_yonetimi_frame, vardiya_amiri_yonetimi_frame, personel_atama_frame]:
    frame.pack(fill="both", expand=True)

# Başlangıçta sadece login göster
menu_frame.pack_forget()
personel_frame.pack_forget()
bas_frame.pack_forget()
kontrol_frame.pack_forget()
ayarlar_frame.pack_forget()
kullanici_yonetimi_frame.pack_forget()
vardiya_amiri_yonetimi_frame.pack_forget()
personel_atama_frame.pack_forget()

# Kullanıcı bilgisi label (sağ üstte)
user_info_label = ctk.CTkLabel(root, text="", font=ctk.CTkFont(size=10))
user_info_label.place(relx=1.0, rely=0.0, anchor="ne", x=-10, y=60)

countdown_label = ctk.CTkLabel(root, text="", font=ctk.CTkFont(size=9))

# Oturum için geri sayım güncelleyicisi
def update_countdown():
    try:
        if 'current_user' in globals() and current_user and current_user.get('id') and session_last_activity:
            timeout = int(get_setting('session_timeout_seconds', db_session_timeout))
            elapsed = (datetime.now() - session_last_activity).total_seconds()
            remaining = int(timeout - elapsed)
            if remaining < 0:
                remaining = 0
            m = remaining // 60
            s = remaining % 60
            countdown_label.configure(text=f"Oturum {m}dk {s}s sonra otomatik kapanacak")
            if remaining == 0:
                # Oturum zaten sonlandırılacak; temizle mesaj
                countdown_label.configure(text="")
        else:
            countdown_label.configure(text="")
    except Exception:
        pass
    try:
        root.after(1000, update_countdown)
    except Exception:
        pass

# İlk geri sayımı başlat
try:
    update_countdown()
except Exception:
    pass

# Çıkış yap butonu
def logout():
    global current_user
    current_user = {'id': None, 'kullanici_adi': None, 'rol': None}
    user_info_label.configure(text="")
    logout_btn.place_forget()
    try:
        countdown_label.place_forget()
    except Exception:
        pass
    show_frame(login_frame)

logout_btn = ctk.CTkButton(root, text="Çıkış Yap", command=logout, fg_color="#DC143C", hover_color="#B22222", width=80)

# Login Frame
login_title = ctk.CTkLabel(login_frame, text="CSL Etiket Programı", font=ctk.CTkFont(size=24, weight="bold"))
login_title.pack(pady=30)

login_subtitle = ctk.CTkLabel(login_frame, text="Giriş Yapın", font=ctk.CTkFont(size=16))
login_subtitle.pack(pady=10)

login_form_frame = ctk.CTkFrame(login_frame)
login_form_frame.pack(pady=20)

login_username_label = ctk.CTkLabel(login_form_frame, text="Kullanıcı Adı:")
login_username_label.grid(row=0, column=0, padx=10, pady=10, sticky="e")
login_username_entry = ctk.CTkEntry(login_form_frame, width=200)
login_username_entry.grid(row=0, column=1, padx=10, pady=10)

login_password_label = ctk.CTkLabel(login_form_frame, text="Şifre:")
login_password_label.grid(row=1, column=0, padx=10, pady=10, sticky="e")
login_password_entry = ctk.CTkEntry(login_form_frame, width=200, show="*")
login_password_entry.grid(row=1, column=1, padx=10, pady=10)

def do_login_thread(username, password):
    try:
        hashed_password = hashlib.sha256(password.encode()).hexdigest()
        cursor.execute("SELECT id, kullanici_adi, rol FROM kullanicilar WHERE kullanici_adi = ? AND sifre = ?",
                       (username, hashed_password))
        user = cursor.fetchone()
        
        if user:
            current_user['id'] = user[0]
            current_user['kullanici_adi'] = user[1]
            current_user['rol'] = user[2]
            # Oturum zamanını güncelle
            touch_session()
            
            root.after(0, lambda: user_info_label.configure(text=f"Kullanıcı: {current_user['kullanici_adi']} ({ROL_DISPLAY.get(current_user['rol'], current_user['rol'])})"))
            root.after(0, lambda: logout_btn.place(relx=1.0, rely=0.0, anchor="ne", x=-10, y=10))
            root.after(0, lambda: countdown_label.place(relx=1.0, rely=0.0, anchor="ne", x=-10, y=40))
            root.after(0, lambda: user_info_label.place(relx=1.0, rely=0.0, anchor="ne", x=-10, y=60))
            root.after(0, lambda: login_username_entry.delete(0, 'end'))
            root.after(0, lambda: login_password_entry.delete(0, 'end'))
            root.after(0, build_menu)
            root.after(0, lambda: show_frame(menu_frame))
        else:
            root.after(0, lambda: messagebox.showerror("Hata", "Kullanıcı adı veya şifre hatalı."))
    except Exception as e:
        root.after(0, lambda: messagebox.showerror("Hata", f"Giriş yapılırken hata: {str(e)}"))

def do_login():
    username = login_username_entry.get()
    password = login_password_entry.get()
    
    if not username or not password:
        messagebox.showerror("Hata", "Kullanıcı adı ve şifre giriniz.")
        return
    
    thread = threading.Thread(target=do_login_thread, args=(username, password))
    thread.daemon = True
    thread.start()

login_btn = ctk.CTkButton(login_form_frame, text="Giriş Yap", command=do_login, width=200)
login_btn.grid(row=2, column=0, columnspan=2, pady=20)

# Enter tuşu ile giriş
login_password_entry.bind('<Return>', lambda e: do_login())

# Fonksiyonlar
personeller = []
def update_bas_personel():
    global personeller
    if current_user['rol'] == 'vardiya_amiri':
        cursor.execute("""
            SELECT p.ad, p.soyad, p.id 
            FROM personel p
            INNER JOIN personel_atama pa ON p.id = pa.personel_id
            WHERE pa.vardiya_amiri_id = ?
        """, (current_user['id'],))
    else:
        cursor.execute("SELECT ad, soyad, id FROM personel")
    
    personeller = cursor.fetchall()
    if personeller:
        personel_options = [f"{p[0]} {p[1]}" for p in personeller]
        personel_combo.configure(values=personel_options)
        personel_combo.set("")
    else:
        personel_combo.configure(values=[])
        personel_combo.set("")

def show_frame(frame):
    try:
        touch_session()
    except Exception:
        pass
    login_frame.pack_forget()
    menu_frame.pack_forget()
    personel_frame.pack_forget()
    bas_frame.pack_forget()
    kontrol_frame.pack_forget()
    ayarlar_frame.pack_forget()
    kullanici_yonetimi_frame.pack_forget()
    vardiya_amiri_yonetimi_frame.pack_forget()
    personel_atama_frame.pack_forget()
    frame.pack(fill="both", expand=True)
    
    if frame == bas_frame:
        update_bas_personel()
    elif frame == personel_frame:
        refresh_list()
    elif frame == ayarlar_frame:
        refresh_db_entry()
    elif frame == kullanici_yonetimi_frame:
        refresh_kullanici_list()
    elif frame == vardiya_amiri_yonetimi_frame:
        refresh_vardiya_amiri_list()
    elif frame == personel_atama_frame:
        refresh_atama_list()

# Ana menü oluşturma
menu_buttons = []

def build_menu():
    global menu_buttons
    for btn in menu_buttons:
        btn.destroy()
    menu_buttons = []
    
    title_label = ctk.CTkLabel(menu_frame, text="CSL Etiket Programı", font=ctk.CTkFont(size=20, weight="bold"))
    title_label.pack(pady=20)
    menu_buttons.append(title_label)
    
    if current_user['rol'] == 'admin':
        btn1 = ctk.CTkButton(menu_frame, text="Personel Yönet", command=lambda: show_frame(personel_frame))
        btn1.pack(pady=10)
        menu_buttons.append(btn1)
        
        btn2 = ctk.CTkButton(menu_frame, text="Etiket Bas", command=lambda: show_frame(bas_frame), fg_color="#228B22", hover_color="#006400")
        btn2.pack(pady=10)
        menu_buttons.append(btn2)
        
        btn3 = ctk.CTkButton(menu_frame, text="Etiket Kontrol Et", command=lambda: show_frame(kontrol_frame), fg_color="#FF9900", hover_color="#FFA500")
        btn3.pack(pady=10)
        menu_buttons.append(btn3)
        
        btn4 = ctk.CTkButton(menu_frame, text="Kullanıcı Yönetimi", command=lambda: show_frame(kullanici_yonetimi_frame), fg_color="#4169E1", hover_color="#1E90FF")
        btn4.pack(pady=10)
        menu_buttons.append(btn4)
        
        btn5 = ctk.CTkButton(menu_frame, text="Personel Atama", command=lambda: show_frame(personel_atama_frame), fg_color="#9370DB", hover_color="#8A2BE2")
        btn5.pack(pady=10)
        menu_buttons.append(btn5)
        
        btn6 = ctk.CTkButton(menu_frame, text="Ayarlar", command=lambda: show_frame(ayarlar_frame), fg_color="#808080", hover_color="#A9A9A9")
        btn6.pack(pady=10)
        menu_buttons.append(btn6)
        
    elif current_user['rol'] == 'takim_lideri':
        btn1 = ctk.CTkButton(menu_frame, text="Personel Yönet", command=lambda: show_frame(personel_frame))
        btn1.pack(pady=10)
        menu_buttons.append(btn1)
        
        btn2 = ctk.CTkButton(menu_frame, text="Vardiya Amiri Yönetimi", command=lambda: show_frame(vardiya_amiri_yonetimi_frame), fg_color="#4169E1", hover_color="#1E90FF")
        btn2.pack(pady=10)
        menu_buttons.append(btn2)
        
        btn3 = ctk.CTkButton(menu_frame, text="Personel Atama", command=lambda: show_frame(personel_atama_frame), fg_color="#9370DB", hover_color="#8A2BE2")
        btn3.pack(pady=10)
        menu_buttons.append(btn3)
        
        btn4 = ctk.CTkButton(menu_frame, text="Etiket Kontrol Et", command=lambda: show_frame(kontrol_frame), fg_color="#FF9900", hover_color="#FFA500")
        btn4.pack(pady=10)
        menu_buttons.append(btn4)
        
    elif current_user['rol'] == 'vardiya_amiri':
        btn1 = ctk.CTkButton(menu_frame, text="Etiket Bas", command=lambda: show_frame(bas_frame), fg_color="#228B22", hover_color="#006400")
        btn1.pack(pady=10)
        menu_buttons.append(btn1)
        
    elif current_user['rol'] == 'kontrol_elemeni':
        btn1 = ctk.CTkButton(menu_frame, text="Etiket Kontrol Et", command=lambda: show_frame(kontrol_frame), fg_color="#FF9900", hover_color="#FFA500")
        btn1.pack(pady=10)
        menu_buttons.append(btn1)


# Personel yönetimi frame
# Widget cache
_personel_widgets_cache = []

def refresh_list():
    global _personel_widgets_cache
    
    # Mevcut widget'ları gizle (destroy yerine)
    for widget in _personel_widgets_cache:
        try:
            widget.pack_forget()
        except:
            pass
    _personel_widgets_cache.clear()
    
    cursor.execute("SELECT id, ad, soyad, vardiya FROM personel ORDER BY id DESC LIMIT 100")
    personeller = cursor.fetchall()
    
    # Batch rendering - Tüm widget'ları bir kerede oluştur
    for p in personeller:
        frame = ctk.CTkFrame(list_frame)
        frame.pack(fill="x", padx=5, pady=2)
        label = ctk.CTkLabel(frame, text=f"{p[1]} {p[2]} - {p[3]}")
        label.pack(side="left", padx=5)
        edit_btn = ctk.CTkButton(frame, text="Düzenle", command=lambda id=p[0]: edit_personel(id), width=80)
        edit_btn.pack(side="right", padx=5)
        delete_btn = ctk.CTkButton(frame, text="Sil", command=lambda id=p[0]: delete_personel(id), width=60)
        delete_btn.pack(side="right", padx=5)
        _personel_widgets_cache.append(frame)

def add_personel():
    add_form_frame.pack(fill="x", padx=10, pady=10)
    add_btn.pack_forget()


def save_personel_thread(ad, soyad, vardiya):
    try:
        cursor.execute("SELECT id FROM personel WHERE ad = ? AND soyad = ?", (ad, soyad))
        if cursor.fetchone():
            root.after(0, lambda: personel_status_label.configure(text=""))
            root.after(0, lambda: messagebox.showerror("Hata", "Bu personel zaten mevcut."))
            return
        
        while True:
            unique_id = ''.join(random.choices(string.ascii_letters + string.digits, k=10))
            cursor.execute("SELECT id FROM personel WHERE uuid = ?", (unique_id,))
            if not cursor.fetchone():
                break
        
        tarih = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("INSERT INTO personel (ad, soyad, vardiya, uuid, olusturma_tarihi) VALUES (?, ?, ?, ?, ?)",
                       (ad, soyad, vardiya, unique_id, tarih))
        conn.commit()
        
        def clear_form():
            personel_status_label.configure(text="")
            messagebox.showinfo("Başarılı", "Personel eklendi.")
            ad_entry.delete(0, 'end')
            soyad_entry.delete(0, 'end')
            vardiya_entry.delete(0, 'end')
            add_form_frame.pack_forget()
            add_btn.pack(pady=10)
            refresh_list()
        
        root.after(0, clear_form)
    except Exception as e:
        root.after(0, lambda: personel_status_label.configure(text=""))
        root.after(0, lambda: messagebox.showerror("Hata", f"Personel eklenirken hata: {str(e)}"))

def save_personel():
    ad = ad_entry.get()
    soyad = soyad_entry.get()
    vardiya = vardiya_entry.get()
    if ad and soyad and vardiya:
        personel_status_label.configure(text="⏳ Ekleniyor...", text_color="orange")
        thread = threading.Thread(target=save_personel_thread, args=(ad, soyad, vardiya))
        thread.daemon = True
        thread.start()
    else:
        messagebox.showerror("Hata", "Tüm alanları doldurun.")

def cancel_add():
    ad_entry.delete(0, 'end')
    soyad_entry.delete(0, 'end')
    vardiya_entry.delete(0, 'end')
    add_form_frame.pack_forget()
    add_btn.pack(pady=10)

current_edit_id = None

def edit_personel(id):
    global current_edit_id
    current_edit_id = id
    cursor.execute("SELECT ad, soyad, vardiya FROM personel WHERE id = ?", (id,))
    p = cursor.fetchone()
    edit_ad_entry.delete(0, 'end')
    edit_ad_entry.insert(0, p[0])
    edit_soyad_entry.delete(0, 'end')
    edit_soyad_entry.insert(0, p[1])
    edit_vardiya_entry.delete(0, 'end')
    edit_vardiya_entry.insert(0, p[2])
    edit_form_frame.pack(fill="x", padx=10, pady=10)
    add_btn.pack_forget()

def update_personel_thread(id, ad, soyad, vardiya):
    try:
        cursor.execute("UPDATE personel SET ad = ?, soyad = ?, vardiya = ? WHERE id = ?",
                       (ad, soyad, vardiya, id))
        conn.commit()
        
        root.after(0, lambda: messagebox.showinfo("Başarılı", "Personel güncellendi."))
        root.after(0, lambda: edit_form_frame.pack_forget())
        root.after(0, lambda: add_btn.pack(pady=10))
        root.after(0, refresh_list)
    except Exception as e:
        root.after(0, lambda: messagebox.showerror("Hata", f"Personel güncellenirken hata: {str(e)}"))

def update_personel(id):
    ad = edit_ad_entry.get()
    soyad = edit_soyad_entry.get()
    vardiya = edit_vardiya_entry.get()
    if ad and soyad and vardiya:
        thread = threading.Thread(target=update_personel_thread, args=(id, ad, soyad, vardiya))
        thread.daemon = True
        thread.start()
    else:
        messagebox.showerror("Hata", "Tüm alanları doldurun.")

def cancel_edit():
    edit_ad_entry.delete(0, 'end')
    edit_soyad_entry.delete(0, 'end')
    edit_vardiya_entry.delete(0, 'end')
    edit_form_frame.pack_forget()
    add_btn.pack(pady=10)

def delete_personel(id):
    if messagebox.askyesno("Sil", "Personeli silmek istediğinizden emin misiniz?"):
        cursor.execute("DELETE FROM personel WHERE id = ?", (id,))
        cursor.execute("DELETE FROM personel_atama WHERE personel_id = ?", (id,))
        conn.commit()
        refresh_list()

geri_btn_personel = ctk.CTkButton(personel_frame, text="Geri", command=lambda: show_frame(menu_frame))
geri_btn_personel.pack(anchor="nw", padx=10, pady=10)

personel_title = ctk.CTkLabel(personel_frame, text="Personel Yönetimi", font=ctk.CTkFont(size=16, weight="bold"))
personel_title.pack(pady=10)

list_frame = ctk.CTkScrollableFrame(personel_frame)
list_frame.pack(fill="both", expand=True, padx=10, pady=10)

add_form_frame = ctk.CTkFrame(personel_frame)
ad_label = ctk.CTkLabel(add_form_frame, text="Ad:")
ad_label.grid(row=0, column=0, padx=5, pady=5)
ad_entry = ctk.CTkEntry(add_form_frame)
ad_entry.grid(row=0, column=1, padx=5, pady=5)

soyad_label = ctk.CTkLabel(add_form_frame, text="Soyad:")
soyad_label.grid(row=1, column=0, padx=5, pady=5)
soyad_entry = ctk.CTkEntry(add_form_frame)
soyad_entry.grid(row=1, column=1, padx=5, pady=5)

vardiya_label = ctk.CTkLabel(add_form_frame, text="Vardiya:")
vardiya_label.grid(row=2, column=0, padx=5, pady=5)
vardiya_entry = ctk.CTkEntry(add_form_frame)
vardiya_entry.grid(row=2, column=1, padx=5, pady=5)

personel_status_label = ctk.CTkLabel(add_form_frame, text="", font=ctk.CTkFont(size=10))
personel_status_label.grid(row=3, column=0, columnspan=2, pady=5)

save_btn = ctk.CTkButton(add_form_frame, text="Kaydet", command=save_personel)
save_btn.grid(row=4, column=0, padx=5, pady=10)

cancel_btn = ctk.CTkButton(add_form_frame, text="İptal", command=cancel_add)
cancel_btn.grid(row=4, column=1, padx=5, pady=10)

edit_form_frame = ctk.CTkFrame(personel_frame)
edit_ad_label = ctk.CTkLabel(edit_form_frame, text="Ad:")
edit_ad_label.grid(row=0, column=0, padx=5, pady=5)
edit_ad_entry = ctk.CTkEntry(edit_form_frame)
edit_ad_entry.grid(row=0, column=1, padx=5, pady=5)

edit_soyad_label = ctk.CTkLabel(edit_form_frame, text="Soyad:")
edit_soyad_label.grid(row=1, column=0, padx=5, pady=5)
edit_soyad_entry = ctk.CTkEntry(edit_form_frame)
edit_soyad_entry.grid(row=1, column=1, padx=5, pady=5)

edit_vardiya_label = ctk.CTkLabel(edit_form_frame, text="Vardiya:")
edit_vardiya_label.grid(row=2, column=0, padx=5, pady=5)
edit_vardiya_entry = ctk.CTkEntry(edit_form_frame)
edit_vardiya_entry.grid(row=2, column=1, padx=5, pady=5)

update_btn = ctk.CTkButton(edit_form_frame, text="Güncelle", command=lambda: update_personel(current_edit_id))
update_btn.grid(row=3, column=0, padx=5, pady=10)

cancel_edit_btn = ctk.CTkButton(edit_form_frame, text="İptal", command=cancel_edit)
cancel_edit_btn.grid(row=3, column=1, padx=5, pady=10)

add_btn = ctk.CTkButton(personel_frame, text="Personel Ekle", command=add_personel)
add_btn.pack(pady=10)

# Etiket Bas frame
geri_btn_bas = ctk.CTkButton(bas_frame, text="Geri", command=lambda: show_frame(menu_frame))
geri_btn_bas.pack(anchor="nw", padx=10, pady=10)

bas_title = ctk.CTkLabel(bas_frame, text="Etiket Bas", font=ctk.CTkFont(size=16, weight="bold"))
bas_title.pack(pady=10)

personel_var = ctk.StringVar()
personel_combo = ctk.CTkComboBox(bas_frame, values=[], variable=personel_var)
personel_combo.pack(pady=10)

adet_label = ctk.CTkLabel(bas_frame, text="Adet:")
adet_label.pack(pady=5)
adet_entry = ctk.CTkEntry(bas_frame)
adet_entry.pack(pady=5)

bas_status_label = ctk.CTkLabel(bas_frame, text="", font=ctk.CTkFont(size=12))
bas_status_label.pack(pady=5)

# Yazıcı seçimi
printer_label = ctk.CTkLabel(bas_frame, text="Yazıcı Seçimi:")
printer_label.pack(pady=5)

printer_var = ctk.StringVar()
printer_combo = ctk.CTkComboBox(bas_frame, values=["Yükleniyor..."], variable=printer_var, width=300)
printer_combo.pack(pady=5)

# Yazıcı ayarları butonu
def open_printer_settings():
    try:
        if sys.platform == "win32":
            os.system("control printers")
        else:
            messagebox.showinfo("Bilgi", "Yazıcı ayarları sadece Windows'ta desteklenmektedir.")
    except Exception as e:
        messagebox.showerror("Hata", f"Yazıcı ayarları açılamadı: {str(e)}")

printer_settings_btn = ctk.CTkButton(bas_frame, text="Yazıcı Ayarları", command=open_printer_settings, width=150)
printer_settings_btn.pack(pady=5)

# Önizleme alanı
preview_frame = ctk.CTkScrollableFrame(bas_frame, width=500, height=200)
preview_frame.pack(pady=10, padx=10, fill="both", expand=False)

preview_label = ctk.CTkLabel(preview_frame, text="Etiket önizlemesi burada görünecek", text_color="gray")
preview_label.pack(pady=20)

# Global değişkenler
created_labels = []
preview_images = []

def get_printers():
    """Sistemdeki yazıcıları listele"""
    printers = []
    try:
        if sys.platform == "win32":
            # Windows için win32print kullan
            try:
                import win32print
                printer_list = win32print.EnumPrinters(win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS)
                printers = [printer[2] for printer in printer_list]
                # Varsayılan yazıcıyı en başa ekle
                default_printer = win32print.GetDefaultPrinter()
                if default_printer in printers:
                    printers.remove(default_printer)
                printers.insert(0, f"{default_printer} (Varsayılan)")
            except ImportError:
                # win32print yoksa subprocess kullan
                result = subprocess.run(['wmic', 'printer', 'get', 'name'], 
                                      capture_output=True, text=True, shell=True)
                lines = result.stdout.strip().split('\n')[1:]
                printers = [line.strip() for line in lines if line.strip()]
        else:
            # Linux/Mac için lpstat kullan
            result = subprocess.run(['lpstat', '-p'], capture_output=True, text=True)
            lines = result.stdout.strip().split('\n')
            printers = [line.split()[1] for line in lines if line.startswith('printer')]
    except Exception as e:
        printers = ["Varsayılan Yazıcı"]
    
    return printers if printers else ["Varsayılan Yazıcı"]

def load_printers_thread():
    """Yazıcıları arka planda yükle"""
    printers = get_printers()
    root.after(0, lambda: printer_combo.configure(values=printers))
    if printers:
        root.after(0, lambda: printer_var.set(printers[0]))

# Yazıcıları yükle
threading.Thread(target=load_printers_thread, daemon=True).start()

def create_labels_thread(personel_id, adet):
    """Etiketleri oluştur ve önizleme göster"""
    global created_labels, preview_images
    try:
        thread_conn = sqlite3.connect(db_path, check_same_thread=False)
        thread_cursor = thread_conn.cursor()
        
        created_labels = []
        preview_images = []
        
        # Etiketleri oluştur
        for i in range(adet):
            while True:
                unique_id = ''.join(random.choices(string.ascii_letters + string.digits, k=10))
                thread_cursor.execute("SELECT id FROM etiket WHERE uuid = ?", (unique_id,))
                if not thread_cursor.fetchone():
                    break
            
            tarih = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            thread_cursor.execute("INSERT INTO etiket (personel_id, uuid, olusturma_tarihi, basan_kullanici_id) VALUES (?, ?, ?, ?)",
                           (personel_id, unique_id, tarih, current_user['id']))
            
            etiket_id = thread_cursor.lastrowid
            created_labels.append({'id': etiket_id, 'uuid': unique_id})
        
        thread_conn.commit()
        thread_conn.close()
        
        # İlk 5 etiketi önizle
        preview_count = min(5, adet)
        for i in range(preview_count):
            qr = qrcode.QRCode(version=1, box_size=5, border=2)
            qr.add_data(created_labels[i]['uuid'])
            qr.make(fit=True)
            img = qr.make_image(fill='black', back_color='white')
            # PIL Image'i PhotoImage'e çevir
            img = img.resize((100, 100))
            preview_images.append(ImageTk.PhotoImage(img))
        
        # UI'ı güncelle
        root.after(0, update_preview_ui, preview_count, adet)
        
    except Exception as e:
        root.after(0, lambda: messagebox.showerror("Hata", f"Etiket oluşturulurken hata: {str(e)}"))
        root.after(0, lambda: bas_status_label.configure(text=""))

def update_preview_ui(preview_count, total_count):
    """Önizleme UI'ını güncelle"""
    global preview_images
    
    # Önizleme alanını temizle
    for widget in preview_frame.winfo_children():
        widget.destroy()
    
    # Başlık
    title = ctk.CTkLabel(preview_frame, 
                         text=f"✓ {total_count} etiket oluşturuldu (İlk {preview_count} önizleme):",
                         font=ctk.CTkFont(size=12, weight="bold"),
                         text_color="green")
    title.pack(pady=10)
    
    # Önizleme göster
    for i in range(preview_count):
        frame = ctk.CTkFrame(preview_frame)
        frame.pack(pady=5, padx=10, fill="x")
        
        # QR kodu
        qr_label = ctk.CTkLabel(frame, image=preview_images[i], text="")
        qr_label.image = preview_images[i]  # Referansı tut
        qr_label.pack(side="left", padx=10)
        
        # Etiket bilgisi
        info_frame = ctk.CTkFrame(frame)
        info_frame.pack(side="left", padx=10, fill="both", expand=True)
        
        uuid_label = ctk.CTkLabel(info_frame, text=f"UUID: {created_labels[i]['uuid']}", 
                                  font=ctk.CTkFont(size=10))
        uuid_label.pack(anchor="w", pady=2)
        
        text_label = ctk.CTkLabel(info_frame, text="CSL 1\nKontrol OK", 
                                 font=ctk.CTkFont(size=10))
        text_label.pack(anchor="w", pady=2)
    
    # Butonları aktif et
    print_btn.configure(state="normal")
    cancel_btn.configure(state="normal")
    create_btn.configure(state="disabled")
    
    bas_status_label.configure(text="✓ Etiketler hazır! Yazdırmak için 'Yazdır' butonuna basın.", 
                               text_color="green")

def create_labels():
    """Etiket oluşturma işlemini başlat"""
    global personeller, created_labels
    
    selected = personel_var.get()
    if not selected:
        messagebox.showerror("Hata", "Personel seçin.")
        return
    
    personel_id = None
    for p in personeller:
        if f"{p[0]} {p[1]}" == selected:
            personel_id = p[2]
            break
    
    adet = adet_entry.get()
    try:
        adet = int(adet)
        if adet <= 0:
            raise ValueError()
    except:
        messagebox.showerror("Hata", "Geçerli adet girin.")
        return
    
    # Önceki etiketleri temizle
    created_labels = []
    
    bas_status_label.configure(text="⏳ Etiketler oluşturuluyor...", text_color="orange")
    create_btn.configure(state="disabled")
    
    # Thread'de çalıştır
    thread = threading.Thread(target=create_labels_thread, args=(personel_id, adet))
    thread.daemon = True
    thread.start()

def print_labels_thread():
    """Etiketleri yazdır"""
    global created_labels
    
    try:
        # Seçili yazıcıyı al
        selected_printer = printer_var.get()
        if "(Varsayılan)" in selected_printer:
            selected_printer = selected_printer.replace(" (Varsayılan)", "")
        
        # Geçici PDF oluştur
        tmp_pdf = tempfile.NamedTemporaryFile(delete=False, suffix='.pdf')
        tmp_pdf_path = tmp_pdf.name
        tmp_pdf.close()
        
        c = canvas.Canvas(tmp_pdf_path, pagesize=(45*mm, 20*mm))
        temp_qr_files = []
        
        # Her etiket için PDF sayfası oluştur
        for label in created_labels:
            qr = qrcode.QRCode(version=5, box_size=10, border=5)
            qr.add_data(label['uuid'])
            qr.make(fit=True)
            img = qr.make_image(fill='black', back_color='white')
            
            # Geçici QR görüntüsü
            tmp_img = tempfile.NamedTemporaryFile(delete=False, suffix='.png')
            tmp_img_path = tmp_img.name
            tmp_img.close()
            img.save(tmp_img_path)
            temp_qr_files.append(tmp_img_path)
            
            # PDF'e ekle
            c.drawImage(tmp_img_path, 2*mm, 1*mm, width=18*mm, height=18*mm)
            c.setFont("Helvetica", 8)
            c.drawString(25*mm, 7*mm, "CSL 1")
            c.drawString(25*mm, 3*mm, "Kontrol OK")
            c.showPage()
        
        c.save()
        
        # Yazdır
        if sys.platform == "win32":
            try:
                import win32print
                import win32api
                
                # Seçili yazıcıya gönder
                win32api.ShellExecute(
                    0,
                    "print",
                    tmp_pdf_path,
                    f'/d:"{selected_printer}"',
                    ".",
                    0
                )
                # Windows'ta yazdırma kuyruğuna girmesi için bekle
                time.sleep(3)
            except ImportError:
                # win32print yoksa varsayılan yazıcıya gönder
                os.startfile(tmp_pdf_path, "print")
                # Yazdırma işlemi için bekle
                time.sleep(3)
        else:
            # Linux/Mac için lp komutu
            subprocess.run(["lp", "-d", selected_printer, tmp_pdf_path], check=True)
            time.sleep(2)
        
        # Geçici dosyaları temizle
        for qr_file in temp_qr_files:
            try:
                if os.path.exists(qr_file):
                    os.remove(qr_file)
            except:
                pass
        
        try:
            if os.path.exists(tmp_pdf_path):
                os.remove(tmp_pdf_path)
        except:
            pass
        
        # Başarılı
        root.after(0, lambda: bas_status_label.configure(
            text="✓ Etiketler yazdırıldı!", text_color="green"))
        root.after(0, reset_print_ui)
        root.after(3000, lambda: bas_status_label.configure(text=""))
        
    except Exception as e:
        root.after(0, lambda: messagebox.showerror("Hata", f"Yazdırma hatası: {str(e)}"))
        root.after(0, lambda: bas_status_label.configure(text=""))
        root.after(0, lambda: print_btn.configure(state="normal"))

def print_labels():
    """Yazdırma işlemini başlat"""
    global created_labels
    
    if not created_labels:
        messagebox.showerror("Hata", "Önce etiket oluşturun.")
        return
    
    bas_status_label.configure(text="⏳ Yazdırılıyor...", text_color="orange")
    print_btn.configure(state="disabled")
    cancel_btn.configure(state="disabled")
    
    # Thread'de çalıştır
    thread = threading.Thread(target=print_labels_thread)
    thread.daemon = True
    thread.start()

def cancel_labels_thread():
    """Oluşturulan etiketleri iptal et"""
    global created_labels
    
    try:
        thread_conn = sqlite3.connect(db_path, check_same_thread=False)
        thread_cursor = thread_conn.cursor()
        
        # Etiketleri sil
        for label in created_labels:
            thread_cursor.execute("DELETE FROM etiket WHERE id = ?", (label['id'],))
        
        thread_conn.commit()
        thread_conn.close()
        
        root.after(0, lambda: bas_status_label.configure(
            text="✓ Etiketler iptal edildi.", text_color="orange"))
        root.after(0, reset_print_ui)
        root.after(3000, lambda: bas_status_label.configure(text=""))
        
    except Exception as e:
        root.after(0, lambda: messagebox.showerror("Hata", f"İptal hatası: {str(e)}"))
        root.after(0, lambda: bas_status_label.configure(text=""))

def cancel_labels():
    """İptal işlemini başlat"""
    global created_labels
    
    if not created_labels:
        return
    
    result = messagebox.askyesno("Onay", "Oluşturulan etiketler silinecek. Emin misiniz?")
    if not result:
        return
    
    bas_status_label.configure(text="⏳ İptal ediliyor...", text_color="orange")
    cancel_btn.configure(state="disabled")
    print_btn.configure(state="disabled")
    
    # Thread'de çalıştır
    thread = threading.Thread(target=cancel_labels_thread)
    thread.daemon = True
    thread.start()

def reset_print_ui():
    """Yazdırma UI'ını sıfırla"""
    global created_labels, preview_images
    
    created_labels = []
    preview_images = []
    
    # Önizleme alanını temizle
    for widget in preview_frame.winfo_children():
        widget.destroy()
    
    preview_label = ctk.CTkLabel(preview_frame, text="Etiket önizlemesi burada görünecek", 
                                text_color="gray")
    preview_label.pack(pady=20)
    
    # Butonları sıfırla
    create_btn.configure(state="normal")
    print_btn.configure(state="disabled")
    cancel_btn.configure(state="disabled")

# Butonlar
button_frame = ctk.CTkFrame(bas_frame)
button_frame.pack(pady=10)

create_btn = ctk.CTkButton(button_frame, text="Etiket Oluştur", command=create_labels, width=150)
create_btn.pack(side="left", padx=5)

print_btn = ctk.CTkButton(button_frame, text="Yazdır", command=print_labels, 
                         width=150, state="disabled")
print_btn.pack(side="left", padx=5)

cancel_btn = ctk.CTkButton(button_frame, text="İptal", command=cancel_labels, 
                          width=150, state="disabled", fg_color="red", hover_color="darkred")
cancel_btn.pack(side="left", padx=5)

# Etiket Kontrol Et frame
geri_btn_kontrol = ctk.CTkButton(kontrol_frame, text="Geri", command=lambda: show_frame(menu_frame))
geri_btn_kontrol.pack(anchor="nw", padx=10, pady=10)

kontrol_title = ctk.CTkLabel(kontrol_frame, text="Etiket Kontrol Et", font=ctk.CTkFont(size=16, weight="bold"))
kontrol_title.pack(pady=10)

uuid_label = ctk.CTkLabel(kontrol_frame, text="QR Kod (UUID):")
uuid_label.pack(pady=5)
uuid_entry = ctk.CTkEntry(kontrol_frame, width=300)
uuid_entry.pack(pady=5)

def kontrol():
    uuid_code = uuid_entry.get()
    if not uuid_code:
        messagebox.showerror("Hata", "UUID girin.")
        return
    
    cursor.execute("""
        SELECT e.personel_id, e.basan_kullanici_id, e.olusturma_tarihi
        FROM etiket e
        WHERE e.uuid = ?
    """, (uuid_code,))
    etiket_result = cursor.fetchone()
    
    if etiket_result:
        personel_id = etiket_result[0]
        basan_kullanici_id = etiket_result[1]
        etiket_tarihi = etiket_result[2]
        
        cursor.execute("SELECT ad, soyad, vardiya FROM personel WHERE id = ?", (personel_id,))
        personel_result = cursor.fetchone()
        
        basan_kullanici = "Bilinmiyor"
        if basan_kullanici_id:
            cursor.execute("SELECT kullanici_adi FROM kullanicilar WHERE id = ?", (basan_kullanici_id,))
            kullanici_result = cursor.fetchone()
            if kullanici_result:
                basan_kullanici = kullanici_result[0]
        
        if personel_result:
            info_text = f"Ad: {personel_result[0]}\n"
            info_text += f"Soyad: {personel_result[1]}\n"
            info_text += f"Vardiya: {personel_result[2]}\n"
            info_text += f"Etiket Tarihi: {etiket_tarihi}\n"
            info_text += f"Basan Kullanıcı: {basan_kullanici}"
            info_label.configure(text=info_text)
        else:
            messagebox.showerror("Hata", "Personel bulunamadı.")
    else:
        messagebox.showerror("Hata", "Etiket bulunamadı.")

kontrol_btn = ctk.CTkButton(kontrol_frame, text="Kontrol Et", command=kontrol)
kontrol_btn.pack(pady=10)

info_label = ctk.CTkLabel(kontrol_frame, text="", font=ctk.CTkFont(size=12), justify="left")
info_label.pack(pady=10)

# Ayarlar frame
geri_btn_ayarlar = ctk.CTkButton(ayarlar_frame, text="Geri", command=lambda: show_frame(menu_frame))
geri_btn_ayarlar.pack(anchor="nw", padx=10, pady=10)

ayarlar_title = ctk.CTkLabel(ayarlar_frame, text="Ayarlar", font=ctk.CTkFont(size=16, weight="bold"))
ayarlar_title.pack(pady=10)

db_label = ctk.CTkLabel(ayarlar_frame, text="Veritabanı Dosyası:")
db_label.pack(pady=5)

db_entry = ctk.CTkEntry(ayarlar_frame, width=300)
db_entry.pack(pady=5)

def refresh_db_entry():
    """Ayarlardan DB yolunu oku ve entry'yi güncelle"""
    db_entry.delete(0, 'end')
    saved_path = get_setting('db_path', db_path)
    db_entry.insert(0, saved_path)

def select_db():
    file_path = filedialog.asksaveasfilename(defaultextension=".db", filetypes=[("SQLite Database", "*.db")])
    if file_path:
        db_entry.delete(0, 'end')
        db_entry.insert(0, file_path)

select_db_btn = ctk.CTkButton(ayarlar_frame, text="Dosya Seç", command=select_db)
select_db_btn.pack(pady=5)

def save_settings():
    global conn, cursor
    new_db = db_entry.get()
    # Oturum süresi
    try:
        oturum_dk = int(session_timeout_entry.get())
        set_setting('session_timeout_seconds', oturum_dk * 60)
    except Exception:
        pass

    if new_db:
        try:
            # Hedef dizini oluştur (yoksa)
            new_db_abs = os.path.abspath(new_db)
            new_db_dir = os.path.dirname(new_db_abs)
            if not os.path.exists(new_db_dir):
                try:
                    os.makedirs(new_db_dir, exist_ok=True)
                except Exception as e:
                    messagebox.showerror("Hata", f"Dizin oluşturulamadı: {new_db_dir}\nHata: {str(e)}")
                    return

            # Yeni DB'ye geçmeden ÖNCE, eski DB'ye yeni yolu kaydet (kalıcılık için)
            # Bu sayede program yeniden başlatıldığında yeni yolu bulabilir
            try:
                set_setting('db_path', new_db_abs)
            except Exception as e:
                pass

            # Eğer yol farklıysa mevcut DB'yi yeni konuma kopyala (OneDrive vb.)
            global db_path
            if os.path.abspath(new_db) != os.path.abspath(db_path):
                # Önce mevcut bağlantıyı kapat (dosyayı serbest bırakmak için)
                try:
                    conn.close()
                except Exception:
                    pass
                try:
                    if os.path.exists(db_path):
                        shutil.copy2(db_path, new_db)
                except Exception as e:
                    # Kopyalama başarısız olsa da yeni DB üzerinde çalışılacak
                    pass

            # Yeni DB'ye bağlan
            conn = sqlite3.connect(new_db, check_same_thread=False)
            cursor = conn.cursor()
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS personel (
                id INTEGER PRIMARY KEY,
                ad TEXT,
                soyad TEXT,
                vardiya TEXT,
                uuid TEXT UNIQUE,
                olusturma_tarihi TEXT
            )
            ''')
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS etiket (
                id INTEGER PRIMARY KEY,
                personel_id INTEGER,
                uuid TEXT UNIQUE,
                olusturma_tarihi TEXT,
                basan_kullanici_id INTEGER,
                FOREIGN KEY (personel_id) REFERENCES personel (id),
                FOREIGN KEY (basan_kullanici_id) REFERENCES kullanicilar (id)
            )
            ''')
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS kullanicilar (
                id INTEGER PRIMARY KEY,
                kullanici_adi TEXT UNIQUE,
                sifre TEXT,
                rol TEXT,
                olusturma_tarihi TEXT
            )
            ''')
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS personel_atama (
                id INTEGER PRIMARY KEY,
                vardiya_amiri_id INTEGER,
                personel_id INTEGER UNIQUE,
                atama_tarihi TEXT,
                FOREIGN KEY (vardiya_amiri_id) REFERENCES kullanicilar (id),
                FOREIGN KEY (personel_id) REFERENCES personel (id)
            )
            ''')
            # Ayarlar tablosunu yeni DB'de oluştur
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS ayarlar (
                anahtar TEXT PRIMARY KEY,
                deger TEXT
            )
            ''')
            conn.commit()
            create_default_admin()
            # DB yolunu ayarlara kaydet (bir sonraki startup'ta buradan okunacak)
            set_setting('db_path', os.path.abspath(new_db))
            messagebox.showinfo("Başarılı", "Veritabanı güncellendi ve kaydedildi.")
            db_path = os.path.abspath(new_db)
        except Exception as e:
            messagebox.showerror("Hata", f"Veritabanı güncellenirken hata: {str(e)}")

save_btn = ctk.CTkButton(ayarlar_frame, text="Kaydet", command=save_settings)
save_btn.pack(pady=10)

# Oturum süresi ayarı (dakika)
session_timeout_label = ctk.CTkLabel(ayarlar_frame, text="Oturum Süresi (dakika):")
session_timeout_label.pack(pady=5)
session_timeout_entry = ctk.CTkEntry(ayarlar_frame, width=100)
try:
    current_timeout = int(get_setting('session_timeout_seconds', db_session_timeout))
    session_timeout_entry.insert(0, str(max(1, current_timeout // 60)))
except Exception:
    session_timeout_entry.insert(0, str(5))
session_timeout_entry.pack(pady=5)

# Şifre Değiştir Bölümü (Sadece Admin)
sifre_ayar_title = ctk.CTkLabel(ayarlar_frame, text="Şifre Değiştir", font=ctk.CTkFont(size=14, weight="bold"))
sifre_ayar_title.pack(pady=20)

sifre_form_frame = ctk.CTkFrame(ayarlar_frame)
sifre_form_frame.pack(pady=10)

eski_sifre_label = ctk.CTkLabel(sifre_form_frame, text="Eski Şifre:")
eski_sifre_label.grid(row=0, column=0, padx=5, pady=5, sticky="e")
eski_sifre_entry = ctk.CTkEntry(sifre_form_frame, show="*", width=200)
eski_sifre_entry.grid(row=0, column=1, padx=5, pady=5)

yeni_sifre_label = ctk.CTkLabel(sifre_form_frame, text="Yeni Şifre:")
yeni_sifre_label.grid(row=1, column=0, padx=5, pady=5, sticky="e")
yeni_sifre_entry = ctk.CTkEntry(sifre_form_frame, show="*", width=200)
yeni_sifre_entry.grid(row=1, column=1, padx=5, pady=5)

yeni_sifre_tekrar_label = ctk.CTkLabel(sifre_form_frame, text="Şifre Tekrar:")
yeni_sifre_tekrar_label.grid(row=2, column=0, padx=5, pady=5, sticky="e")
yeni_sifre_tekrar_entry = ctk.CTkEntry(sifre_form_frame, show="*", width=200)
yeni_sifre_tekrar_entry.grid(row=2, column=1, padx=5, pady=5)

sifre_status_label = ctk.CTkLabel(sifre_form_frame, text="", font=ctk.CTkFont(size=10))
sifre_status_label.grid(row=3, column=0, columnspan=2, pady=5)

def change_password_thread(eski_sifre, yeni_sifre, yeni_sifre_tekrar):
    try:
        if yeni_sifre != yeni_sifre_tekrar:
            root.after(0, lambda: sifre_status_label.configure(text=""))
            root.after(0, lambda: messagebox.showerror("Hata", "Yeni şifreler eşleşmiyor!"))
            return
        
        if len(yeni_sifre) < 4:
            root.after(0, lambda: sifre_status_label.configure(text=""))
            root.after(0, lambda: messagebox.showerror("Hata", "Şifre en az 4 karakter olmalıdır!"))
            return
        
        eski_sifre_hash = hashlib.sha256(eski_sifre.encode()).hexdigest()
        cursor.execute("SELECT sifre FROM kullanicilar WHERE id = ?", (current_user['id'],))
        result = cursor.fetchone()
        
        if not result or result[0] != eski_sifre_hash:
            root.after(0, lambda: sifre_status_label.configure(text=""))
            root.after(0, lambda: messagebox.showerror("Hata", "Eski şifre yanlış!"))
            return
        
        yeni_sifre_hash = hashlib.sha256(yeni_sifre.encode()).hexdigest()
        cursor.execute("UPDATE kullanicilar SET sifre = ? WHERE id = ?", 
                      (yeni_sifre_hash, current_user['id']))
        conn.commit()
        
        root.after(0, lambda: sifre_status_label.configure(text=""))
        root.after(0, lambda: messagebox.showinfo("Başarılı", "Şifre başarıyla değiştirildi!"))
        root.after(0, lambda: eski_sifre_entry.delete(0, 'end'))
        root.after(0, lambda: yeni_sifre_entry.delete(0, 'end'))
        root.after(0, lambda: yeni_sifre_tekrar_entry.delete(0, 'end'))
        
    except Exception as e:
        root.after(0, lambda: sifre_status_label.configure(text=""))
        root.after(0, lambda: messagebox.showerror("Hata", f"Şifre değiştirilirken hata: {str(e)}"))

def change_password():
    eski_sifre = eski_sifre_entry.get()
    yeni_sifre = yeni_sifre_entry.get()
    yeni_sifre_tekrar = yeni_sifre_tekrar_entry.get()
    
    if not eski_sifre or not yeni_sifre or not yeni_sifre_tekrar:
        messagebox.showerror("Hata", "Tüm alanları doldurun.")
        return
    
    sifre_status_label.configure(text="⏳ Değiştiriliyor...", text_color="orange")
    thread = threading.Thread(target=change_password_thread, args=(eski_sifre, yeni_sifre, yeni_sifre_tekrar))
    thread.daemon = True
    thread.start()

def clear_password_fields():
    eski_sifre_entry.delete(0, 'end')
    yeni_sifre_entry.delete(0, 'end')
    yeni_sifre_tekrar_entry.delete(0, 'end')

sifre_degistir_btn = ctk.CTkButton(sifre_form_frame, text="Şifre Değiştir", command=change_password)
sifre_degistir_btn.grid(row=4, column=0, padx=5, pady=10)

sifre_temizle_btn = ctk.CTkButton(sifre_form_frame, text="Temizle", command=clear_password_fields)
sifre_temizle_btn.grid(row=4, column=1, padx=5, pady=10)


# Kullanıcı Yönetimi Frame (Sadece Admin)
geri_btn_kullanici = ctk.CTkButton(kullanici_yonetimi_frame, text="Geri", command=lambda: show_frame(menu_frame))
geri_btn_kullanici.pack(anchor="nw", padx=10, pady=10)

kullanici_title = ctk.CTkLabel(kullanici_yonetimi_frame, text="Kullanıcı Yönetimi", font=ctk.CTkFont(size=16, weight="bold"))
kullanici_title.pack(pady=10)

kullanici_list_frame = ctk.CTkScrollableFrame(kullanici_yonetimi_frame)
kullanici_list_frame.pack(fill="both", expand=True, padx=10, pady=10)

# Widget cache
_kullanici_widgets_cache = []

def refresh_kullanici_list():
    global _kullanici_widgets_cache
    
    for widget in _kullanici_widgets_cache:
        try:
            widget.pack_forget()
        except:
            pass
    _kullanici_widgets_cache.clear()
    
    cursor.execute("SELECT id, kullanici_adi, rol FROM kullanicilar ORDER BY id")
    kullanicilar = cursor.fetchall()
    for k in kullanicilar:
        frame = ctk.CTkFrame(kullanici_list_frame)
        frame.pack(fill="x", padx=5, pady=2)
        label = ctk.CTkLabel(frame, text=f"{k[1]} - {ROL_DISPLAY.get(k[2], k[2])}")
        label.pack(side="left", padx=5)
        edit_kullanici_btn = ctk.CTkButton(frame, text="Düzenle", command=lambda id=k[0]: edit_kullanici(id), width=80)
        edit_kullanici_btn.pack(side="right", padx=5)
        if k[1] != 'admin':
            delete_kullanici_btn = ctk.CTkButton(frame, text="Sil", command=lambda id=k[0]: delete_kullanici(id), width=60)
            delete_kullanici_btn.pack(side="right", padx=5)
        _kullanici_widgets_cache.append(frame)

kullanici_add_form_frame = ctk.CTkFrame(kullanici_yonetimi_frame)
kullanici_username_label = ctk.CTkLabel(kullanici_add_form_frame, text="Kullanıcı Adı:")
kullanici_username_label.grid(row=0, column=0, padx=5, pady=5)
kullanici_username_entry = ctk.CTkEntry(kullanici_add_form_frame)
kullanici_username_entry.grid(row=0, column=1, padx=5, pady=5)

kullanici_password_label = ctk.CTkLabel(kullanici_add_form_frame, text="Şifre:")
kullanici_password_label.grid(row=1, column=0, padx=5, pady=5)
kullanici_password_entry = ctk.CTkEntry(kullanici_add_form_frame, show="*")
kullanici_password_entry.grid(row=1, column=1, padx=5, pady=5)

kullanici_rol_label = ctk.CTkLabel(kullanici_add_form_frame, text="Rol:")
kullanici_rol_label.grid(row=2, column=0, padx=5, pady=5)
kullanici_rol_var = ctk.StringVar(value="Vardiya Amiri")
kullanici_rol_combo = ctk.CTkComboBox(kullanici_add_form_frame, values=["Admin", "Takım Lideri", "Vardiya Amiri", "Kontrol Elemanı"], variable=kullanici_rol_var)
kullanici_rol_combo.grid(row=2, column=1, padx=5, pady=5)

kullanici_status_label = ctk.CTkLabel(kullanici_add_form_frame, text="", font=ctk.CTkFont(size=10))
kullanici_status_label.grid(row=3, column=0, columnspan=2, pady=5)

def add_kullanici():
    kullanici_add_form_frame.pack(fill="x", padx=10, pady=10)
    kullanici_add_btn.pack_forget()

def save_kullanici_thread(username, password, rol):
    try:
        cursor.execute("SELECT id FROM kullanicilar WHERE kullanici_adi = ?", (username,))
        if cursor.fetchone():
            root.after(0, lambda: kullanici_status_label.configure(text=""))
            root.after(0, lambda: messagebox.showerror("Hata", "Bu kullanıcı adı zaten mevcut."))
            return
        
        hashed_password = hashlib.sha256(password.encode()).hexdigest()
        tarih = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        cursor.execute("INSERT INTO kullanicilar (kullanici_adi, sifre, rol, olusturma_tarihi) VALUES (?, ?, ?, ?)",
                       (username, hashed_password, rol, tarih))
        conn.commit()
        
        def clear_form():
            kullanici_status_label.configure(text="")
            messagebox.showinfo("Başarılı", "Kullanıcı eklendi.")
            kullanici_username_entry.delete(0, 'end')
            kullanici_password_entry.delete(0, 'end')
            kullanici_add_form_frame.pack_forget()
            kullanici_add_btn.pack(pady=10)
            refresh_kullanici_list()
        
        root.after(0, clear_form)
    except Exception as e:
        root.after(0, lambda: kullanici_status_label.configure(text=""))
        root.after(0, lambda err=str(e): messagebox.showerror("Hata", f"Kullanıcı eklenirken hata: {err}"))

def save_kullanici():
    username = kullanici_username_entry.get()
    password = kullanici_password_entry.get()
    rol_display = kullanici_rol_var.get()
    rol = ROL_REVERSE.get(rol_display, 'vardiya_amiri')
    
    if username and password and rol:
        kullanici_status_label.configure(text="⏳ Ekleniyor...", text_color="orange")
        thread = threading.Thread(target=save_kullanici_thread, args=(username, password, rol))
        thread.daemon = True
        thread.start()
    else:
        messagebox.showerror("Hata", "Tüm alanları doldurun.")

def cancel_add_kullanici():
    kullanici_username_entry.delete(0, 'end')
    kullanici_password_entry.delete(0, 'end')
    kullanici_add_form_frame.pack_forget()
    kullanici_add_btn.pack(pady=10)

kullanici_save_btn = ctk.CTkButton(kullanici_add_form_frame, text="Kaydet", command=save_kullanici)
kullanici_save_btn.grid(row=4, column=0, padx=5, pady=10)

kullanici_cancel_btn = ctk.CTkButton(kullanici_add_form_frame, text="İptal", command=cancel_add_kullanici)
kullanici_cancel_btn.grid(row=4, column=1, padx=5, pady=10)

current_edit_kullanici_id = None
kullanici_edit_form_frame = ctk.CTkFrame(kullanici_yonetimi_frame)
kullanici_edit_username_label = ctk.CTkLabel(kullanici_edit_form_frame, text="Kullanıcı Adı:")
kullanici_edit_username_label.grid(row=0, column=0, padx=5, pady=5)
kullanici_edit_username_entry = ctk.CTkEntry(kullanici_edit_form_frame)
kullanici_edit_username_entry.grid(row=0, column=1, padx=5, pady=5)

kullanici_edit_password_label = ctk.CTkLabel(kullanici_edit_form_frame, text="Yeni Şifre:")
kullanici_edit_password_label.grid(row=1, column=0, padx=5, pady=5)
kullanici_edit_password_entry = ctk.CTkEntry(kullanici_edit_form_frame, show="*")
kullanici_edit_password_entry.grid(row=1, column=1, padx=5, pady=5)

kullanici_edit_rol_label = ctk.CTkLabel(kullanici_edit_form_frame, text="Rol:")
kullanici_edit_rol_label.grid(row=2, column=0, padx=5, pady=5)
kullanici_edit_rol_var = ctk.StringVar()
kullanici_edit_rol_combo = ctk.CTkComboBox(kullanici_edit_form_frame, values=["Admin", "Takım Lideri", "Vardiya Amiri", "Kontrol Elemanı"], variable=kullanici_edit_rol_var)
kullanici_edit_rol_combo.grid(row=2, column=1, padx=5, pady=5)

def edit_kullanici(id):
    global current_edit_kullanici_id
    current_edit_kullanici_id = id
    cursor.execute("SELECT kullanici_adi, rol FROM kullanicilar WHERE id = ?", (id,))
    k = cursor.fetchone()
    kullanici_edit_username_entry.delete(0, 'end')
    kullanici_edit_username_entry.insert(0, k[0])
    kullanici_edit_rol_var.set(ROL_DISPLAY.get(k[1], k[1]))
    kullanici_edit_password_entry.delete(0, 'end')
    kullanici_edit_form_frame.pack(fill="x", padx=10, pady=10)
    kullanici_add_btn.pack_forget()

def update_kullanici_thread(id, username, password, rol):
    try:
        hashed_password = hashlib.sha256(password.encode()).hexdigest()
        cursor.execute("UPDATE kullanicilar SET kullanici_adi = ?, sifre = ?, rol = ? WHERE id = ?",
                       (username, hashed_password, rol, id))
        conn.commit()
        
        root.after(0, lambda: messagebox.showinfo("Başarılı", "Kullanıcı güncellendi."))
        root.after(0, lambda: kullanici_edit_form_frame.pack_forget())
        root.after(0, lambda: kullanici_add_btn.pack(pady=10))
        root.after(0, refresh_kullanici_list)
    except Exception as e:
        root.after(0, lambda: messagebox.showerror("Hata", f"Kullanıcı güncellenirken hata: {str(e)}"))

def update_kullanici(id):
    username = kullanici_edit_username_entry.get()
    password = kullanici_edit_password_entry.get()
    rol_display = kullanici_edit_rol_var.get()
    rol = ROL_REVERSE.get(rol_display, 'vardiya_amiri')
    
    if username and password and rol:
        thread = threading.Thread(target=update_kullanici_thread, args=(id, username, password, rol))
        thread.daemon = True
        thread.start()
    else:
        messagebox.showerror("Hata", "Tüm alanlar zorunludur.")

def cancel_edit_kullanici():
    kullanici_edit_username_entry.delete(0, 'end')
    kullanici_edit_password_entry.delete(0, 'end')
    kullanici_edit_form_frame.pack_forget()
    kullanici_add_btn.pack(pady=10)

kullanici_update_btn = ctk.CTkButton(kullanici_edit_form_frame, text="Güncelle", command=lambda: update_kullanici(current_edit_kullanici_id))
kullanici_update_btn.grid(row=3, column=0, padx=5, pady=10)

kullanici_cancel_edit_btn = ctk.CTkButton(kullanici_edit_form_frame, text="İptal", command=cancel_edit_kullanici)
kullanici_cancel_edit_btn.grid(row=3, column=1, padx=5, pady=10)

def delete_kullanici(id):
    if messagebox.askyesno("Sil", "Kullanıcıyı silmek istediğinizden emin misiniz?"):
        cursor.execute("DELETE FROM kullanicilar WHERE id = ?", (id,))
        cursor.execute("DELETE FROM personel_atama WHERE vardiya_amiri_id = ?", (id,))
        conn.commit()
        refresh_kullanici_list()

kullanici_add_btn = ctk.CTkButton(kullanici_yonetimi_frame, text="Kullanıcı Ekle", command=add_kullanici)
kullanici_add_btn.pack(pady=10)

# Vardiya Amiri Yönetimi Frame (Sadece Takım Lideri)
geri_btn_vardiya_amiri = ctk.CTkButton(vardiya_amiri_yonetimi_frame, text="Geri", command=lambda: show_frame(menu_frame))
geri_btn_vardiya_amiri.pack(anchor="nw", padx=10, pady=10)

vardiya_amiri_title = ctk.CTkLabel(vardiya_amiri_yonetimi_frame, text="Vardiya Amiri Yönetimi", font=ctk.CTkFont(size=16, weight="bold"))
vardiya_amiri_title.pack(pady=10)

vardiya_amiri_list_frame = ctk.CTkScrollableFrame(vardiya_amiri_yonetimi_frame)
vardiya_amiri_list_frame.pack(fill="both", expand=True, padx=10, pady=10)

# Widget cache
_vardiya_amiri_widgets_cache = []

def refresh_vardiya_amiri_list():
    global _vardiya_amiri_widgets_cache
    
    for widget in _vardiya_amiri_widgets_cache:
        try:
            widget.pack_forget()
        except:
            pass
    _vardiya_amiri_widgets_cache.clear()
    
    cursor.execute("SELECT id, kullanici_adi FROM kullanicilar WHERE rol = 'vardiya_amiri' ORDER BY id")
    vardiya_amirleri = cursor.fetchall()
    for v in vardiya_amirleri:
        frame = ctk.CTkFrame(vardiya_amiri_list_frame)
        frame.pack(fill="x", padx=5, pady=2)
        label = ctk.CTkLabel(frame, text=f"{v[1]}")
        label.pack(side="left", padx=5)
        edit_vardiya_amiri_btn = ctk.CTkButton(frame, text="Düzenle", command=lambda id=v[0]: edit_vardiya_amiri(id), width=80)
        edit_vardiya_amiri_btn.pack(side="right", padx=5)
        delete_vardiya_amiri_btn = ctk.CTkButton(frame, text="Sil", command=lambda id=v[0]: delete_vardiya_amiri(id), width=60)
        delete_vardiya_amiri_btn.pack(side="right", padx=5)
        _vardiya_amiri_widgets_cache.append(frame)

vardiya_amiri_add_form_frame = ctk.CTkFrame(vardiya_amiri_yonetimi_frame)
vardiya_amiri_username_label = ctk.CTkLabel(vardiya_amiri_add_form_frame, text="Kullanıcı Adı:")
vardiya_amiri_username_label.grid(row=0, column=0, padx=5, pady=5)
vardiya_amiri_username_entry = ctk.CTkEntry(vardiya_amiri_add_form_frame)
vardiya_amiri_username_entry.grid(row=0, column=1, padx=5, pady=5)

vardiya_amiri_password_label = ctk.CTkLabel(vardiya_amiri_add_form_frame, text="Şifre:")
vardiya_amiri_password_label.grid(row=1, column=0, padx=5, pady=5)
vardiya_amiri_password_entry = ctk.CTkEntry(vardiya_amiri_add_form_frame, show="*")
vardiya_amiri_password_entry.grid(row=1, column=1, padx=5, pady=5)

def add_vardiya_amiri():
    vardiya_amiri_add_form_frame.pack(fill="x", padx=10, pady=10)
    vardiya_amiri_add_btn.pack_forget()

def save_vardiya_amiri_thread(username, password):
    try:
        cursor.execute("SELECT id FROM kullanicilar WHERE kullanici_adi = ?", (username,))
        if cursor.fetchone():
            root.after(0, lambda: messagebox.showerror("Hata", "Bu kullanıcı adı zaten mevcut."))
            return
        
        hashed_password = hashlib.sha256(password.encode()).hexdigest()
        tarih = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("INSERT INTO kullanicilar (kullanici_adi, sifre, rol, olusturma_tarihi) VALUES (?, ?, ?, ?)",
                       (username, hashed_password, 'vardiya_amiri', tarih))
        conn.commit()
        
        root.after(0, lambda: messagebox.showinfo("Başarılı", "Vardiya amiri eklendi."))
        root.after(0, lambda: vardiya_amiri_username_entry.delete(0, 'end'))
        root.after(0, lambda: vardiya_amiri_password_entry.delete(0, 'end'))
        root.after(0, lambda: vardiya_amiri_add_form_frame.pack_forget())
        root.after(0, lambda: vardiya_amiri_add_btn.pack(pady=10))
        root.after(0, refresh_vardiya_amiri_list)
    except Exception as e:
        root.after(0, lambda: messagebox.showerror("Hata", f"Vardiya amiri eklenirken hata: {str(e)}"))

def save_vardiya_amiri():
    username = vardiya_amiri_username_entry.get()
    password = vardiya_amiri_password_entry.get()
    
    if username and password:
        thread = threading.Thread(target=save_vardiya_amiri_thread, args=(username, password))
        thread.daemon = True
        thread.start()
    else:
        messagebox.showerror("Hata", "Tüm alanları doldurun.")

def cancel_add_vardiya_amiri():
    vardiya_amiri_username_entry.delete(0, 'end')
    vardiya_amiri_password_entry.delete(0, 'end')
    vardiya_amiri_add_form_frame.pack_forget()
    vardiya_amiri_add_btn.pack(pady=10)

vardiya_amiri_save_btn = ctk.CTkButton(vardiya_amiri_add_form_frame, text="Kaydet", command=save_vardiya_amiri)
vardiya_amiri_save_btn.grid(row=2, column=0, padx=5, pady=10)

vardiya_amiri_cancel_btn = ctk.CTkButton(vardiya_amiri_add_form_frame, text="İptal", command=cancel_add_vardiya_amiri)
vardiya_amiri_cancel_btn.grid(row=2, column=1, padx=5, pady=10)

current_edit_vardiya_amiri_id = None
vardiya_amiri_edit_form_frame = ctk.CTkFrame(vardiya_amiri_yonetimi_frame)
vardiya_amiri_edit_username_label = ctk.CTkLabel(vardiya_amiri_edit_form_frame, text="Kullanıcı Adı:")
vardiya_amiri_edit_username_label.grid(row=0, column=0, padx=5, pady=5)
vardiya_amiri_edit_username_entry = ctk.CTkEntry(vardiya_amiri_edit_form_frame)
vardiya_amiri_edit_username_entry.grid(row=0, column=1, padx=5, pady=5)

vardiya_amiri_edit_password_label = ctk.CTkLabel(vardiya_amiri_edit_form_frame, text="Yeni Şifre:")
vardiya_amiri_edit_password_label.grid(row=1, column=0, padx=5, pady=5)
vardiya_amiri_edit_password_entry = ctk.CTkEntry(vardiya_amiri_edit_form_frame, show="*")
vardiya_amiri_edit_password_entry.grid(row=1, column=1, padx=5, pady=5)

def edit_vardiya_amiri(id):
    global current_edit_vardiya_amiri_id
    current_edit_vardiya_amiri_id = id
    cursor.execute("SELECT kullanici_adi FROM kullanicilar WHERE id = ?", (id,))
    v = cursor.fetchone()
    vardiya_amiri_edit_username_entry.delete(0, 'end')
    vardiya_amiri_edit_username_entry.insert(0, v[0])
    vardiya_amiri_edit_password_entry.delete(0, 'end')
    vardiya_amiri_edit_form_frame.pack(fill="x", padx=10, pady=10)
    vardiya_amiri_add_btn.pack_forget()

def update_vardiya_amiri_thread(id, username, password):
    try:
        hashed_password = hashlib.sha256(password.encode()).hexdigest()
        cursor.execute("UPDATE kullanicilar SET kullanici_adi = ?, sifre = ? WHERE id = ?",
                       (username, hashed_password, id))
        conn.commit()
        
        root.after(0, lambda: messagebox.showinfo("Başarılı", "Vardiya amiri güncellendi."))
        root.after(0, lambda: vardiya_amiri_edit_form_frame.pack_forget())
        root.after(0, lambda: vardiya_amiri_add_btn.pack(pady=10))
        root.after(0, refresh_vardiya_amiri_list)
    except Exception as e:
        root.after(0, lambda: messagebox.showerror("Hata", f"Vardiya amiri güncellenirken hata: {str(e)}"))

def update_vardiya_amiri(id):
    username = vardiya_amiri_edit_username_entry.get()
    password = vardiya_amiri_edit_password_entry.get()
    
    if username and password:
        thread = threading.Thread(target=update_vardiya_amiri_thread, args=(id, username, password))
        thread.daemon = True
        thread.start()
    else:
        messagebox.showerror("Hata", "Tüm alanlar zorunludur.")

def cancel_edit_vardiya_amiri():
    vardiya_amiri_edit_username_entry.delete(0, 'end')
    vardiya_amiri_edit_password_entry.delete(0, 'end')
    vardiya_amiri_edit_form_frame.pack_forget()
    vardiya_amiri_add_btn.pack(pady=10)

vardiya_amiri_update_btn = ctk.CTkButton(vardiya_amiri_edit_form_frame, text="Güncelle", command=lambda: update_vardiya_amiri(current_edit_vardiya_amiri_id))
vardiya_amiri_update_btn.grid(row=2, column=0, padx=5, pady=10)

vardiya_amiri_cancel_edit_btn = ctk.CTkButton(vardiya_amiri_edit_form_frame, text="İptal", command=cancel_edit_vardiya_amiri)
vardiya_amiri_cancel_edit_btn.grid(row=2, column=1, padx=5, pady=10)

def delete_vardiya_amiri(id):
    if messagebox.askyesno("Sil", "Vardiya amirini silmek istediğinizden emin misiniz?"):
        cursor.execute("DELETE FROM kullanicilar WHERE id = ?", (id,))
        cursor.execute("DELETE FROM personel_atama WHERE vardiya_amiri_id = ?", (id,))
        conn.commit()
        refresh_vardiya_amiri_list()

vardiya_amiri_add_btn = ctk.CTkButton(vardiya_amiri_yonetimi_frame, text="Vardiya Amiri Ekle", command=add_vardiya_amiri)
vardiya_amiri_add_btn.pack(pady=10)


# Personel Atama Frame (Admin ve Takım Lideri)
geri_btn_atama = ctk.CTkButton(personel_atama_frame, text="Geri", command=lambda: show_frame(menu_frame))
geri_btn_atama.pack(anchor="nw", padx=10, pady=10)

atama_title = ctk.CTkLabel(personel_atama_frame, text="Personel Atama", font=ctk.CTkFont(size=16, weight="bold"))
atama_title.pack(pady=10)

atama_main_frame = ctk.CTkFrame(personel_atama_frame)
atama_main_frame.pack(fill="both", expand=True, padx=10, pady=10)

atama_left_frame = ctk.CTkFrame(atama_main_frame)
atama_left_frame.pack(side="left", fill="both", expand=True, padx=5)

atama_right_frame = ctk.CTkFrame(atama_main_frame)
atama_right_frame.pack(side="right", fill="both", expand=True, padx=5)

atama_vardiya_amiri_label = ctk.CTkLabel(atama_left_frame, text="Vardiya Amirleri", font=ctk.CTkFont(size=14, weight="bold"))
atama_vardiya_amiri_label.pack(pady=5)

atama_vardiya_amiri_list = ctk.CTkScrollableFrame(atama_left_frame, height=300)
atama_vardiya_amiri_list.pack(fill="both", expand=True, pady=5)

atama_personel_label = ctk.CTkLabel(atama_right_frame, text="Personeller", font=ctk.CTkFont(size=14, weight="bold"))
atama_personel_label.pack(pady=5)

atama_personel_list = ctk.CTkScrollableFrame(atama_right_frame, height=300)
atama_personel_list.pack(fill="both", expand=True, pady=5)

selected_vardiya_amiri_id = None

def refresh_atama_list():
    global selected_vardiya_amiri_id
    for widget in atama_vardiya_amiri_list.winfo_children():
        widget.destroy()
    
    cursor.execute("SELECT id, kullanici_adi FROM kullanicilar WHERE rol = 'vardiya_amiri'")
    vardiya_amirleri = cursor.fetchall()
    
    for v in vardiya_amirleri:
        btn = ctk.CTkButton(atama_vardiya_amiri_list, text=v[1], 
                            command=lambda id=v[0], name=v[1]: select_vardiya_amiri(id, name))
        btn.pack(fill="x", padx=5, pady=2)

def select_vardiya_amiri(id, name):
    global selected_vardiya_amiri_id
    selected_vardiya_amiri_id = id
    atama_personel_label.configure(text=f"Personeller - {name}")
    refresh_personel_atama_list()

def refresh_personel_atama_list():
    if selected_vardiya_amiri_id is None:
        return
    
    for widget in atama_personel_list.winfo_children():
        widget.destroy()
    
    cursor.execute("""
        SELECT p.id, p.ad, p.soyad 
        FROM personel p
        INNER JOIN personel_atama pa ON p.id = pa.personel_id
        WHERE pa.vardiya_amiri_id = ?
    """, (selected_vardiya_amiri_id,))
    atanmis_personeller = cursor.fetchall()
    
    if atanmis_personeller:
        atanmis_label = ctk.CTkLabel(atama_personel_list, text="Atanmış Personeller:", font=ctk.CTkFont(weight="bold"))
        atanmis_label.pack(pady=5)
        
        for p in atanmis_personeller:
            frame = ctk.CTkFrame(atama_personel_list)
            frame.pack(fill="x", padx=5, pady=2)
            label = ctk.CTkLabel(frame, text=f"{p[1]} {p[2]}")
            label.pack(side="left", padx=5)
            remove_btn = ctk.CTkButton(frame, text="Çıkar", command=lambda pid=p[0]: remove_personel_atama(pid), 
                                       fg_color="#DC143C", hover_color="#B22222", width=60)
            remove_btn.pack(side="right", padx=5)
    
    cursor.execute("""
        SELECT p.id, p.ad, p.soyad 
        FROM personel p
        WHERE p.id NOT IN (
            SELECT personel_id FROM personel_atama
        )
    """)
    atanmamis_personeller = cursor.fetchall()
    
    if atanmamis_personeller:
        atanmamis_label = ctk.CTkLabel(atama_personel_list, text="Atanmamış Personeller:", font=ctk.CTkFont(weight="bold"))
        atanmamis_label.pack(pady=5)
        
        for p in atanmamis_personeller:
            frame = ctk.CTkFrame(atama_personel_list)
            frame.pack(fill="x", padx=5, pady=2)
            label = ctk.CTkLabel(frame, text=f"{p[1]} {p[2]}")
            label.pack(side="left", padx=5)
            add_btn = ctk.CTkButton(frame, text="Ata", command=lambda pid=p[0]: add_personel_atama(pid), 
                                    fg_color="#228B22", hover_color="#006400", width=60)
            add_btn.pack(side="right", padx=5)

def add_personel_atama(personel_id):
    if selected_vardiya_amiri_id is None:
        return
    
    cursor.execute("SELECT id FROM personel_atama WHERE personel_id = ?", (personel_id,))
    if cursor.fetchone():
        messagebox.showerror("Hata", "Bu personel zaten başka bir vardiya amirine atanmış!")
        return
    
    tarih = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("INSERT INTO personel_atama (vardiya_amiri_id, personel_id, atama_tarihi) VALUES (?, ?, ?)",
                   (selected_vardiya_amiri_id, personel_id, tarih))
    conn.commit()
    refresh_personel_atama_list()

def remove_personel_atama(personel_id):
    if selected_vardiya_amiri_id is None:
        return
    
    cursor.execute("DELETE FROM personel_atama WHERE vardiya_amiri_id = ? AND personel_id = ?",
                   (selected_vardiya_amiri_id, personel_id))
    conn.commit()
    refresh_personel_atama_list()

root.mainloop()

# Veritabanı kapat
conn.close()
