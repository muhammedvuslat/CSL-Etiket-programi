import customtkinter as ctk
import sqlite3
import qrcode
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import mm
from PIL import Image
import pyzbar.pyzbar as pyzbar
from tkinter import filedialog, messagebox
import uuid
import random
import string
from datetime import datetime
import os

# Veritabanı bağlantısı
conn = sqlite3.connect('personel.db')
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
    FOREIGN KEY (personel_id) REFERENCES personel (id)
)
''')
conn.commit()

# Ana pencere
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")

root = ctk.CTk()
root.title("CSL Etiket Programı")
root.geometry("600x500")

# Frame'ler
menu_frame = ctk.CTkFrame(root)
personel_frame = ctk.CTkFrame(root)
bas_frame = ctk.CTkFrame(root)
kontrol_frame = ctk.CTkFrame(root)
ayarlar_frame = ctk.CTkFrame(root)

for frame in [menu_frame, personel_frame, bas_frame, kontrol_frame, ayarlar_frame]:
    frame.pack(fill="both", expand=True)

# Başlangıçta sadece menu göster
personel_frame.pack_forget()
bas_frame.pack_forget()
kontrol_frame.pack_forget()
ayarlar_frame.pack_forget()

# Çık butonu
exit_btn = ctk.CTkButton(root, text="Çık", command=root.quit, fg_color="#DC143C", hover_color="#B22222", width=50)
exit_btn.place(relx=1.0, rely=0.0, anchor="ne", x=-10, y=10)

# Fonksiyonlar
personeller = []
def update_bas_personel():
    global personeller
    cursor.execute("SELECT ad, soyad, id FROM personel")
    personeller = cursor.fetchall()
    if personeller:
        personel_options = [f"{p[0]} {p[1]}" for p in personeller]
        personel_combo.configure(values=personel_options)
        personel_combo.set("")  # Seçimi temizle
    else:
        personel_combo.configure(values=[])
        personel_combo.set("")

# Personel yönetimi frame
def refresh_list():
    for widget in list_frame.winfo_children():
        widget.destroy()
    cursor.execute("SELECT id, ad, soyad, vardiya FROM personel")
    personeller = cursor.fetchall()
    for p in personeller:
        frame = ctk.CTkFrame(list_frame)
        frame.pack(fill="x", padx=5, pady=2)
        label = ctk.CTkLabel(frame, text=f"{p[1]} {p[2]} - {p[3]}")
        label.pack(side="left", padx=5)
        edit_btn = ctk.CTkButton(frame, text="Düzenle", command=lambda id=p[0]: edit_personel(id))
        edit_btn.pack(side="right", padx=5)
        delete_btn = ctk.CTkButton(frame, text="Sil", command=lambda id=p[0]: delete_personel(id))
        delete_btn.pack(side="right", padx=5)

def add_personel():
    # Formu göster
    add_form_frame.pack(fill="x", padx=10, pady=10)
    add_btn.pack_forget()  # Ekle butonunu gizle

def save_personel():
    ad = ad_entry.get()
    soyad = soyad_entry.get()
    vardiya = vardiya_entry.get()
    if ad and soyad and vardiya:
        # Aynı personel var mı kontrol et
        cursor.execute("SELECT id FROM personel WHERE ad = ? AND soyad = ?", (ad, soyad))
        if cursor.fetchone():
            messagebox.showerror("Hata", "Bu personel zaten mevcut.")
            return
        # Benzersiz 10 karakterli alfanumerik kod üret
        while True:
            unique_id = ''.join(random.choices(string.ascii_letters + string.digits, k=10))
            cursor.execute("SELECT id FROM personel WHERE uuid = ?", (unique_id,))
            if not cursor.fetchone():
                break

        tarih = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("INSERT INTO personel (ad, soyad, vardiya, uuid, olusturma_tarihi) VALUES (?, ?, ?, ?, ?)",
                       (ad, soyad, vardiya, unique_id, tarih))
        conn.commit()
        messagebox.showinfo("Başarılı", "Personel eklendi.")
        # Formu temizle ve gizle
        ad_entry.delete(0, 'end')
        soyad_entry.delete(0, 'end')
        vardiya_entry.delete(0, 'end')
        add_form_frame.pack_forget()
        add_btn.pack(pady=10)
        refresh_list()
        # Etiket Bas alanını güncelle
        update_bas_personel()
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
    # Formu göster
    edit_form_frame.pack(fill="x", padx=10, pady=10)
    add_btn.pack_forget()  # Ekle butonunu gizle

def update_personel(id):
    ad = edit_ad_entry.get()
    soyad = edit_soyad_entry.get()
    vardiya = edit_vardiya_entry.get()
    if ad and soyad and vardiya:
        cursor.execute("UPDATE personel SET ad = ?, soyad = ?, vardiya = ? WHERE id = ?",
                       (ad, soyad, vardiya, id))
        conn.commit()
        messagebox.showinfo("Başarılı", "Personel güncellendi.")
        edit_form_frame.pack_forget()
        add_btn.pack(pady=10)
        refresh_list()
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
        conn.commit()
        refresh_list()

geri_btn_personel = ctk.CTkButton(personel_frame, text="Geri", command=lambda: show_frame(menu_frame))
geri_btn_personel.pack(anchor="nw", padx=10, pady=10)

personel_title = ctk.CTkLabel(personel_frame, text="Personel Yönetimi", font=ctk.CTkFont(size=16, weight="bold"))
personel_title.pack(pady=10)

list_frame = ctk.CTkScrollableFrame(personel_frame)
list_frame.pack(fill="both", expand=True, padx=10, pady=10)

# Ekle formu
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

save_btn = ctk.CTkButton(add_form_frame, text="Kaydet", command=save_personel)
save_btn.grid(row=3, column=0, padx=5, pady=10)

cancel_btn = ctk.CTkButton(add_form_frame, text="İptal", command=cancel_add)
cancel_btn.grid(row=3, column=1, padx=5, pady=10)

# Düzenle formu
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

refresh_list()

refresh_list()

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

def bas():
    global personeller
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
    except:
        messagebox.showerror("Hata", "Geçerli adet girin.")
        return
    # PDF oluşturma
    c = canvas.Canvas("etiketler.pdf", pagesize=(45*mm, 20*mm))
    temp_files = []
    for i in range(adet):
        # Benzersiz 10 karakterli alfanumerik kod üret
        while True:
            unique_id = ''.join(random.choices(string.ascii_letters + string.digits, k=10))
            cursor.execute("SELECT id FROM etiket WHERE uuid = ?", (unique_id,))
            if not cursor.fetchone():
                break
        tarih = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("INSERT INTO etiket (personel_id, uuid, olusturma_tarihi) VALUES (?, ?, ?)",
                       (personel_id, unique_id, tarih))
        qr = qrcode.QRCode(version=5, box_size=10, border=5)
        qr.add_data(unique_id)
        qr.make(fit=True)
        img = qr.make_image(fill='black', back_color='white')
        temp_file = f"temp_qr_{i}.png"
        img.save(temp_file)
        temp_files.append(temp_file)
        c.drawImage(temp_file, 2*mm, 1*mm, width=18*mm, height=18*mm)
        c.setFont("Helvetica", 8)
        c.drawString(25*mm, 7*mm, "CSL 1")
        c.drawString(25*mm, 3*mm, "Kontrol OK")
        c.showPage()
    c.save()
    conn.commit()
    # PDF aç
    import sys
    if sys.platform == "win32":
        os.startfile("etiketler.pdf")
    else:
        os.system("xdg-open etiketler.pdf")
    # Temp dosyaları temizle
    for temp_file in temp_files:
        if os.path.exists(temp_file):
            os.remove(temp_file)
    conn.commit()
    messagebox.showinfo("Başarılı", f"{adet} etiket PDF olarak oluşturuldu ve açıldı.")

bas_btn = ctk.CTkButton(bas_frame, text="Bas", command=bas)
bas_btn.pack(pady=10)

# Etiket Kontrol Et frame
geri_btn_kontrol = ctk.CTkButton(kontrol_frame, text="Geri", command=lambda: show_frame(menu_frame))
geri_btn_kontrol.pack(anchor="nw", padx=10, pady=10)

kontrol_title = ctk.CTkLabel(kontrol_frame, text="Etiket Kontrol Et", font=ctk.CTkFont(size=16, weight="bold"))
kontrol_title.pack(pady=10)

uuid_label = ctk.CTkLabel(kontrol_frame, text="QR Kod (UUID):")
uuid_label.pack(pady=5)
uuid_entry = ctk.CTkEntry(kontrol_frame)
uuid_entry.pack(pady=5)

def kontrol():
    uuid_code = uuid_entry.get()
    if not uuid_code:
        messagebox.showerror("Hata", "UUID girin.")
        return
    # Önce etiket tablosundan ara
    cursor.execute("SELECT personel_id FROM etiket WHERE uuid = ?", (uuid_code,))
    etiket_result = cursor.fetchone()
    if etiket_result:
        personel_id = etiket_result[0]
        cursor.execute("SELECT ad, soyad, olusturma_tarihi FROM personel WHERE id = ?", (personel_id,))
        result = cursor.fetchone()
        if result:
            info_label.configure(text=f"Ad: {result[0]}\nSoyad: {result[1]}\nTarih: {result[2]}")
        else:
            messagebox.showerror("Hata", "Personel bulunamadı.")
    else:
        messagebox.showerror("Hata", "Etiket bulunamadı.")

kontrol_btn = ctk.CTkButton(kontrol_frame, text="Kontrol Et", command=kontrol)
kontrol_btn.pack(pady=10)

info_label = ctk.CTkLabel(kontrol_frame, text="")
info_label.pack(pady=10)

# Ayarlar frame
geri_btn_ayarlar = ctk.CTkButton(ayarlar_frame, text="Geri", command=lambda: show_frame(menu_frame))
geri_btn_ayarlar.pack(anchor="nw", padx=10, pady=10)

ayarlar_title = ctk.CTkLabel(ayarlar_frame, text="Ayarlar", font=ctk.CTkFont(size=16, weight="bold"))
ayarlar_title.pack(pady=10)

db_label = ctk.CTkLabel(ayarlar_frame, text="Veritabanı Dosyası:")
db_label.pack(pady=5)

db_entry = ctk.CTkEntry(ayarlar_frame)
db_entry.insert(0, 'personel.db')
db_entry.pack(pady=5)

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
    if new_db:
        try:
            conn.close()
            conn = sqlite3.connect(new_db)
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
                FOREIGN KEY (personel_id) REFERENCES personel (id)
            )
            ''')
            conn.commit()
            messagebox.showinfo("Başarılı", "Veritabanı güncellendi.")
        except Exception as e:
            messagebox.showerror("Hata", f"Veritabanı güncellenirken hata: {str(e)}")

save_btn = ctk.CTkButton(ayarlar_frame, text="Kaydet", command=save_settings)
save_btn.pack(pady=10)

def show_frame(frame):
    menu_frame.pack_forget()
    personel_frame.pack_forget()
    bas_frame.pack_forget()
    kontrol_frame.pack_forget()
    ayarlar_frame.pack_forget()
    frame.pack(fill="both", expand=True)
    if frame == bas_frame:
        update_bas_personel()

# Ana menü
title_label = ctk.CTkLabel(menu_frame, text="CSL Etiket Programı", font=ctk.CTkFont(size=20, weight="bold"))
title_label.pack(pady=20)

personel_btn = ctk.CTkButton(menu_frame, text="Personel Yönet", command=lambda: show_frame(personel_frame))
personel_btn.pack(pady=10)

bas_btn = ctk.CTkButton(menu_frame, text="Etiket Bas", command=lambda: show_frame(bas_frame), fg_color="#228B22", hover_color="#006400")
bas_btn.pack(pady=10)

kontrol_btn = ctk.CTkButton(menu_frame, text="Etiket Kontrol Et", command=lambda: show_frame(kontrol_frame), fg_color="#FF9900", hover_color="#FFA500")
kontrol_btn.pack(pady=10)

ayarlar_btn = ctk.CTkButton(menu_frame, text="Ayarlar", command=lambda: show_frame(ayarlar_frame), fg_color="#808080", hover_color="#A9A9A9")
ayarlar_btn.pack(pady=10)

root.mainloop()

# Veritabanı kapat
conn.close()