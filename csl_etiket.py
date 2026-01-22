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
conn.commit()

# Ana pencere
ctk.set_appearance_mode("System")
ctk.set_default_color_theme("blue")

root = ctk.CTk()
root.title("CSL Etiket Programı")
root.geometry("400x300")

# Fonksiyonlar
def personel_tanimla():
    personel_window = ctk.CTkToplevel(root)
    personel_window.title("Personel Yönetimi")
    personel_window.geometry("600x400")

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
        add_window = ctk.CTkToplevel(personel_window)
        add_window.title("Personel Ekle")
        add_window.geometry("300x200")

        ad_label = ctk.CTkLabel(add_window, text="Ad:")
        ad_label.pack(pady=5)
        ad_entry = ctk.CTkEntry(add_window)
        ad_entry.pack(pady=5)

        soyad_label = ctk.CTkLabel(add_window, text="Soyad:")
        soyad_label.pack(pady=5)
        soyad_entry = ctk.CTkEntry(add_window)
        soyad_entry.pack(pady=5)

        vardiya_label = ctk.CTkLabel(add_window, text="Vardiya:")
        vardiya_label.pack(pady=5)
        vardiya_entry = ctk.CTkEntry(add_window)
        vardiya_entry.pack(pady=5)

        def save():
            ad = ad_entry.get()
            soyad = soyad_entry.get()
            vardiya = vardiya_entry.get()
            if ad and soyad and vardiya:
                unique_id = str(uuid.uuid4())
                tarih = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                cursor.execute("INSERT INTO personel (ad, soyad, vardiya, uuid, olusturma_tarihi) VALUES (?, ?, ?, ?, ?)",
                               (ad, soyad, vardiya, unique_id, tarih))
                conn.commit()
                messagebox.showinfo("Başarılı", "Personel eklendi.")
                add_window.destroy()
                refresh_list()
            else:
                messagebox.showerror("Hata", "Tüm alanları doldurun.")

        save_btn = ctk.CTkButton(add_window, text="Kaydet", command=save)
        save_btn.pack(pady=10)

    def edit_personel(id):
        cursor.execute("SELECT ad, soyad, vardiya FROM personel WHERE id = ?", (id,))
        p = cursor.fetchone()
        edit_window = ctk.CTkToplevel(personel_window)
        edit_window.title("Personel Düzenle")
        edit_window.geometry("300x200")

        ad_entry = ctk.CTkEntry(edit_window)
        ad_entry.insert(0, p[0])
        ad_entry.pack(pady=5)

        soyad_entry = ctk.CTkEntry(edit_window)
        soyad_entry.insert(0, p[1])
        soyad_entry.pack(pady=5)

        vardiya_entry = ctk.CTkEntry(edit_window)
        vardiya_entry.insert(0, p[2])
        vardiya_entry.pack(pady=5)

        def update():
            ad = ad_entry.get()
            soyad = soyad_entry.get()
            vardiya = vardiya_entry.get()
            if ad and soyad and vardiya:
                cursor.execute("UPDATE personel SET ad = ?, soyad = ?, vardiya = ? WHERE id = ?",
                               (ad, soyad, vardiya, id))
                conn.commit()
                messagebox.showinfo("Başarılı", "Personel güncellendi.")
                edit_window.destroy()
                refresh_list()
            else:
                messagebox.showerror("Hata", "Tüm alanları doldurun.")

        update_btn = ctk.CTkButton(edit_window, text="Güncelle", command=update)
        update_btn.pack(pady=10)

    def delete_personel(id):
        if messagebox.askyesno("Sil", "Personeli silmek istediğinizden emin misiniz?"):
            cursor.execute("DELETE FROM personel WHERE id = ?", (id,))
            conn.commit()
            refresh_list()

    list_frame = ctk.CTkScrollableFrame(personel_window)
    list_frame.pack(fill="both", expand=True, padx=10, pady=10)

    add_btn = ctk.CTkButton(personel_window, text="Personel Ekle", command=add_personel)
    add_btn.pack(pady=10)

    refresh_list()

def etiket_bas():
    bas_window = ctk.CTkToplevel(root)
    bas_window.title("Etiket Bas")
    bas_window.geometry("400x200")

    cursor.execute("SELECT ad, soyad, id FROM personel")
    personeller = cursor.fetchall()
    if not personeller:
        messagebox.showerror("Hata", "Hiç personel tanımlanmamış.")
        return

    personel_options = [f"{p[0]} {p[1]}" for p in personeller]
    personel_var = ctk.StringVar()
    personel_combo = ctk.CTkComboBox(bas_window, values=personel_options, variable=personel_var)
    personel_combo.pack(pady=10)

    adet_label = ctk.CTkLabel(bas_window, text="Adet:")
    adet_label.pack(pady=5)
    adet_entry = ctk.CTkEntry(bas_window)
    adet_entry.pack(pady=5)

    def bas():
        selected = personel_var.get()
        if not selected:
            messagebox.showerror("Hata", "Personel seçin.")
            return
        selected_id = None
        for p in personeller:
            if f"{p[0]} {p[1]}" == selected:
                selected_id = p[2]
                break
        cursor.execute("SELECT uuid FROM personel WHERE id = ?", (selected_id,))
        uuid_code = cursor.fetchone()[0]
        adet = adet_entry.get()
        try:
            adet = int(adet)
        except:
            messagebox.showerror("Hata", "Geçerli adet girin.")
            return
        # PDF oluşturma
        c = canvas.Canvas("etiketler.pdf", pagesize=(45*mm, 20*mm))
        for i in range(adet):
            qr = qrcode.QRCode(version=1, box_size=10, border=5)
            qr.add_data(uuid_code)
            qr.make(fit=True)
            img = qr.make_image(fill='black', back_color='white')
            img.save("temp_qr.png")
            c.drawImage("temp_qr.png", 2*mm, 5*mm, width=10*mm, height=10*mm)
            c.drawString(2*mm, 2*mm, "CSL 1 Kontrol OK")
            c.showPage()
        c.save()
        # PDF aç
        os.system("xdg-open etiketler.pdf")
        # Log
        tarih = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("UPDATE personel SET olusturma_tarihi = ? WHERE id = ?", (tarih, selected_id))
        conn.commit()
        messagebox.showinfo("Başarılı", f"{adet} etiket PDF olarak oluşturuldu ve açıldı.")
        bas_window.destroy()

    bas_btn = ctk.CTkButton(bas_window, text="Bas", command=bas)
    bas_btn.pack(pady=10)

def etiket_kontrol_et():
    kontrol_window = ctk.CTkToplevel(root)
    kontrol_window.title("Etiket Kontrol Et")
    kontrol_window.geometry("400x200")

    uuid_label = ctk.CTkLabel(kontrol_window, text="QR Kod (UUID):")
    uuid_label.pack(pady=5)
    uuid_entry = ctk.CTkEntry(kontrol_window)
    uuid_entry.pack(pady=5)

    def kontrol():
        uuid_code = uuid_entry.get()
        if not uuid_code:
            messagebox.showerror("Hata", "UUID girin.")
            return
        cursor.execute("SELECT ad, soyad, olusturma_tarihi FROM personel WHERE uuid = ?", (uuid_code,))
        result = cursor.fetchone()
        if result:
            info_label.configure(text=f"Ad: {result[0]}\nSoyad: {result[1]}\nTarih: {result[2]}")
        else:
            messagebox.showerror("Hata", "Personel bulunamadı.")

    kontrol_btn = ctk.CTkButton(kontrol_window, text="Kontrol Et", command=kontrol)
    kontrol_btn.pack(pady=10)

    info_label = ctk.CTkLabel(kontrol_window, text="")
    info_label.pack(pady=10)

# Ana menü
title_label = ctk.CTkLabel(root, text="CSL Etiket Programı", font=ctk.CTkFont(size=20, weight="bold"))
title_label.pack(pady=20)

personel_btn = ctk.CTkButton(root, text="Personel Tanımla", command=personel_tanimla)
personel_btn.pack(pady=10)

bas_btn = ctk.CTkButton(root, text="Etiket Bas", command=etiket_bas)
bas_btn.pack(pady=10)

kontrol_btn = ctk.CTkButton(root, text="Etiket Kontrol Et", command=etiket_kontrol_et)
kontrol_btn.pack(pady=10)

root.mainloop()

# Veritabanı kapat
conn.close()