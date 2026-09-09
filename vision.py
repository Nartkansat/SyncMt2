import tkinter as tk
from tkinter import messagebox
import time
import threading
import keyboard
import random
import ctypes
from ctypes import c_int, c_void_p, c_ushort, c_uint
import os
import sys
import mss
import cv2
import numpy as np
import json
import winsound

import glob

APP_VERSION = "3.5.0"

# --- PYINSTALLER EMBEDDED RESOURCE PATH RESOLVER ---
def res_path(relative_path):
    """
    PyInstaller tek dosya (.exe) ve normal Python ortamı için dosya yolu çözücü.
    Gömülü (.exe) içindeki sys._MEIPASS klasörünü veya exe yanını kontrol eder.
    """
    if not relative_path:
        return ""
    if getattr(sys, 'frozen', False):
        base_dir = getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))
        p_mei = os.path.join(base_dir, relative_path)
        if os.path.exists(p_mei):
            return p_mei
        p_exe = os.path.join(os.path.dirname(sys.executable), relative_path)
        if os.path.exists(p_exe):
            return p_exe
        return p_mei
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), relative_path)

def res_glob(pattern):
    """PyInstaller .exe veya normal Python ortamında desene uyan tüm dosyaları arar."""
    results = []
    if getattr(sys, 'frozen', False):
        base_dir = getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))
        results.extend(glob.glob(os.path.join(base_dir, pattern)))
        results.extend(glob.glob(os.path.join(os.path.dirname(sys.executable), pattern)))
    else:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        results.extend(glob.glob(os.path.join(base_dir, pattern)))
    return list(dict.fromkeys(results))

# --- INTERCEPTION DLL AYARLARI ---
dll_path = res_path("interception.dll")
interception = ctypes.CDLL(dll_path)
class InterceptionMouseStroke(ctypes.Structure):
    _fields_ = [
        ("state", c_ushort),
        ("flags", c_ushort),
        ("rolling", ctypes.c_short),
        ("x", c_int),
        ("y", c_int),
        ("information", c_uint)
    ]

# Fonksiyon tiplerini 3.13 için tanımlıyoruz (Hata almamak için şart)
interception.interception_create_context.restype = c_void_p
interception.interception_set_filter.argtypes = [c_void_p, c_void_p, c_ushort]
interception.interception_send.argtypes = [c_void_p, c_int, c_void_p, c_uint]
interception.interception_receive.argtypes = [c_void_p, c_int, c_void_p, c_uint]
interception.interception_is_mouse.argtypes = [c_int]
interception.interception_is_mouse.restype = c_int

context = interception.interception_create_context()

DEVICE_ID = 1 # Klavye ID'si
MOUSE_DEVICE_ID = 11 # Fare ID'si (Genelde 11-20 arasındadır)
is_running = False
pause_for_1_key = False
target_temporarily_lost = False
is_dead = False # Karakter ölüyken her şeyi durdurmak için bayrak
bot_state = "IDLE"
route_waypoints = []
clearing_at_waypoint = False  # Tur sırasında waypoint'te durunca True olur (Space aktif)


hp_pixel = None # Örn: {"x": 100, "y": 100, "r": 255, "g": 0, "b": 0}
mp_pixel = None # Örn: {"x": 100, "y": 100, "r": 0, "g": 0, "b": 255}
calibration_mode = None # "hp" veya "mp"
calibrating_armor_pos = False
cfg_armor_pos = None      # {"x": int, "y": int}

def get_color_at(x, y):
    with mss.mss() as sct:
        img = np.array(sct.grab({"top": y, "left": x, "width": 1, "height": 1}))
        b, g, r, a = img[0][0]
        return int(r), int(g), int(b)

def _wait_armor_click_thread():
    global calibrating_armor_pos, cfg_armor_pos
    while ctypes.windll.user32.GetAsyncKeyState(0x01) & 0x8000:
        time.sleep(0.05)
    time.sleep(0.15)
    
    calibrating_armor_pos = True
    print("[BİLGİ] Zırh konumu için: Farenizi envanterdeki Zırhın üzerine getirip F9 tuşuna basın (veya Sol Tıklayın)...")
    
    while calibrating_armor_pos:
        if keyboard.is_pressed('f9') or (ctypes.windll.user32.GetAsyncKeyState(0x78) & 0x8000) or (ctypes.windll.user32.GetAsyncKeyState(0x01) & 0x8000):
            calibrating_armor_pos = False
            class POINT(ctypes.Structure):
                _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]
            pt = POINT()
            ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
            cfg_armor_pos = {"x": pt.x, "y": pt.y}
            print(f"[BİLGİ] 🛡️ [F9/Interception] Zırh konumu algılandı: X={pt.x}, Y={pt.y}")
            
            time.sleep(0.3)
            try:
                root.after(0, on_armor_pos_captured, pt.x, pt.y)
            except Exception:
                pass
            break
        time.sleep(0.03)

def start_armor_calibration():
    global calibrating_armor_pos
    if calibrating_armor_pos:
        return
    if 'btn_armor_pos' in globals() and btn_armor_pos:
        btn_armor_pos.config(text="📍 Zırha Gelip F9 veya Tıkla...", bg="#D97706", fg="#FFFFFF")
    if 'lbl_armor_pos' in globals() and lbl_armor_pos:
        lbl_armor_pos.config(text="F9 tuşu / Tıklama bekleniyor...", fg="#F59E0B")
    t = threading.Thread(target=_wait_armor_click_thread, daemon=True)
    t.start()

def on_armor_pos_captured(x, y):
    if 'btn_armor_pos' in globals() and btn_armor_pos:
        btn_armor_pos.config(text="🛡️ Zırh Konum Kaydet", bg="#1F2937", fg="#F3F4F6")
    if 'lbl_armor_pos' in globals() and lbl_armor_pos:
        lbl_armor_pos.config(text=f"Zırh Konumu: X={x}, Y={y}", fg=SUCCESS)
    save_config()
    try:
        messagebox.showinfo("Zırh Konumu Algılandı", f"Zırh konumu başarıyla algılandı!\n\nX: {x}\nY: {y}")
    except Exception:
        pass

def calibrate_hotkey_loop():
    global hp_pixel, mp_pixel, calibration_mode
    while True:
        if calibration_mode and keyboard.is_pressed('f6'):
            class POINT(ctypes.Structure):
                _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]
            pt = POINT()
            ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
            r, g, b = get_color_at(pt.x, pt.y)
            
            if calibration_mode == "hp":
                hp_pixel = {"x": pt.x, "y": pt.y, "r": r, "g": g, "b": b}
                print(f"[BİLGİ] Can piksellendi: X={pt.x}, Y={pt.y}, Renk=({r},{g},{b})")
            elif calibration_mode == "mp":
                mp_pixel = {"x": pt.x, "y": pt.y, "r": r, "g": g, "b": b}
                print(f"[BİLGİ] Mana piksellendi: X={pt.x}, Y={pt.y}, Renk=({r},{g},{b})")
                
            calibration_mode = None
            save_config() # Ayarlandığı anda hemen kaydet
            time.sleep(0.5)
        time.sleep(0.05)

t_calib = threading.Thread(target=calibrate_hotkey_loop)
t_calib.daemon = True
t_calib.start()

# --- AYARLAR (GUI üzerinden değiştirilecek) ---
cfg_space = True
cfg_quote = True
cfg_1 = True
cfg_hp = True
cfg_mp = True
cfg_target = True
cfg_item = True
cfg_revive = True # Otomatik dirilme
cfg_patrol = False
cfg_clearing = True # Metin etraf turu (alan temizliği)
cfg_use_coords = False # Bölge koordinat sınırı
cfg_fish_delay_min = "0.5" # Balık botu min çekme gecikmesi (sn)
cfg_fish_delay_max = "1.5" # Balık botu max çekme gecikmesi (sn)
cfg_fish_delay = "0.5 - 1.5"
cfg_ch_change = False  # CH (Kanal) Değiştirme
cfg_pot_alarm = True   # Pot Bitti Sesli Uyarısı
cfg_horse_mode = False # Atta Savaş / Skilde Attan İn (Ctrl+G)
cfg_player_name = "Ali" # Karakter / İtem Sahibi İsmi
cfg_pm_stop = True     # PM/Fısıltı Gelince Botu Durdur ve Mektuba Tıkla
cfg_captcha_enable = True  # Bot Verify Otomatik Çözüm
cfg_captcha_alarm  = True  # Bot Verify Sesli Uyarı
cfg_pm_reply_1 = "as"
cfg_pm_reply_2 = "abi ben kardesiyim tam bilmiyorum oyunu ben."
cfg_pm_reply_3 = "dedigim gibi kardesiyim ben abim aktif olunca yazarsaniz sevinirim iyi oyunlar."
pm_senders_history = {} # {sender_hash_str: msg_count}
last_metin_pos = None  # Son bilinen metin konumu
bot_start_time = 0     # Bot başlama veya CH değiştirme zamanı
is_mounted = True      # Karakterin ata binmiş durumda olduğunu takip eder
cfg_min_x = 750
cfg_max_x = 900
cfg_min_y = 750
cfg_max_y = 900

# --- BOT MOD AKTİFLİK AYARLARI ---
cfg_metin_enable = True
cfg_fish_enable = False
cfg_fish_bait_key = '2'   # Varsayılan Yem tuşu: 2
cfg_fish_rod_key = '3'    # Varsayılan Olta atma tuşu: 3
cfg_fish_delay = '2.5'
cfg_auto_bait = True
cfg_auto_open_fish = False
cfg_fish_armor_anim = False
cfg_armor_pos = None      # {"x": int, "y": int}
calibrating_armor_pos = False
cfg_multi_bait = False        # Çoklu Yem Modu
cfg_multi_bait_keys = "alt+1, alt+2, alt+3, alt+4" # Çoklu yem için kullanılacak tuş sırası
cfg_multi_bait_slot = 1       # Aktif slot: 1..5 (Alt+1 .. Alt+5)
cfg_multi_bait_count = 0      # Mevcut slotta kullanılan yem sayısı (0..200)

# --- HEDEF METIN AYARLARI ---
cfg_metin_default = True
cfg_metin_hirs = False
cfg_metin_savas = False
cfg_metin_dovus = False
cfg_metin_siyah = False
cfg_metin_uzuntu = False
cfg_metin_ruh = True

# --- POT TUŞ AYARLARI ---
cfg_hp_key = 'f3'  # Varsayılan: F3
cfg_mp_key = 'f2'  # Varsayılan: F2

_audio_mixer_initialized = False

def _init_audio_mixer():
    global _audio_mixer_initialized
    if _audio_mixer_initialized:
        return True
    try:
        os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = '1'
        import pygame
        pygame.mixer.pre_init(44100, -16, 2, 2048)
        pygame.mixer.init()
        _audio_mixer_initialized = True
        return True
    except Exception as e:
        print(f"[SES] Mixer başlatılamadı: {e}")
        return False

def start_code_voice_loop():
    """Ekranda Bot Verify kodu olduğu sürece codevoice.mp3 sesini döngü halinde kesintisiz çalar."""
    try:
        if _init_audio_mixer():
            import pygame
            p = res_path("codevoice.mp3")
            if os.path.exists(p):
                pygame.mixer.music.load(p)
                pygame.mixer.music.play(-1) # -1: kesintisiz başa sararak döngü
                return
    except Exception as e:
        print(f"[SES] Kod sesi çalma hatası: {e}")
    play_loud_captcha_alarm()

def stop_code_voice_loop():
    """Doğrulama kodu penceresi kapandığında codevoice sesini anında susturur."""
    try:
        if _audio_mixer_initialized:
            import pygame
            if pygame.mixer.music.get_busy():
                pygame.mixer.music.stop()
    except Exception:
        pass

def play_pm_voice():
    """PM geldiğinde pmvoice.mp3 sesini çalar."""
    try:
        if _init_audio_mixer():
            import pygame
            p = res_path("pmvoice.mp3")
            if os.path.exists(p):
                snd = pygame.mixer.Sound(p)
                snd.play()
                return
    except Exception as e:
        print(f"[SES] PM sesi çalma hatası: {e}")
    try:
        winsound.Beep(1800, 300)
    except Exception:
        pass

def play_loud_captcha_alarm():
    """Bot Verify veya PM uyarısı için yüksek sesli siren sesi (yedek / fallback)."""
    def _run():
        try:
            for _ in range(2):
                winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
                time.sleep(0.08)
                winsound.MessageBeep(winsound.MB_ICONHAND)
                time.sleep(0.08)
            for _ in range(3):
                winsound.Beep(2800, 160)
                winsound.Beep(3500, 160)
                winsound.Beep(2800, 160)
                winsound.Beep(3500, 200)
                time.sleep(0.05)
                winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
        except Exception:
            pass
    threading.Thread(target=_run, daemon=True).start()

def send_key_raw(code, state):
    """Ctype kullanarak kernel'e doğrudan ham veri gönderir"""
    stroke = (c_ushort * 10)()
    stroke[0] = code
    stroke[1] = state
    interception.interception_send(context, DEVICE_ID, stroke, 1)

def send_string_interception(text):
    """Metin2 anti-cheat takılmadan Interception Kernel Sürücüsü ile klavyeden harf harf yazar"""
    # Türkçe karakterleri İngilizce eşdeğerlerine dönüştür
    tr_map = str.maketrans("ışğüöçİŞĞÜÖÇ", "isguocisguoc")
    text = text.translate(tr_map).lower()

    scan_codes = {
        'a': 0x1E, 'b': 0x30, 'c': 0x2E, 'd': 0x20, 'e': 0x12, 'f': 0x21,
        'g': 0x22, 'h': 0x23, 'i': 0x17, 'j': 0x24, 'k': 0x25, 'l': 0x26,
        'm': 0x32, 'n': 0x31, 'o': 0x18, 'p': 0x19, 'q': 0x10, 'r': 0x13,
        's': 0x1F, 't': 0x14, 'u': 0x16, 'v': 0x2F, 'w': 0x11, 'x': 0x2D,
        'y': 0x15, 'z': 0x2C,
        ' ': 0x39, '.': 0x34, ',': 0x33, '\n': 0x1C, '\r': 0x1C,
        '0': 0x0B, '1': 0x02, '2': 0x03, '3': 0x04, '4': 0x05,
        '5': 0x06, '6': 0x07, '7': 0x08, '8': 0x09, '9': 0x0A
    }
    for char in text:
        code = scan_codes.get(char)
        if code:
            send_key_raw(code, 0) # Key Down
            time.sleep(0.03)
            send_key_raw(code, 1) # Key Up
            time.sleep(0.04)

def send_mouse_click_raw(x, y, right=False):
    """
    Evrensel 4 Katmanlı Hibrit Tıklama Motoru:
    1. SetCursorPos (Piksel İmleç Taşıma)
    2. Interception Donanım Filtresi (Tüm Fare Cihazları 1-20)
    3. Win32 Absolute + Relative mouse_event (Touchpad & Fiziksel Fare Desteği)
    Her butona önce hover yapar (60ms), basılı tutar (90ms) ve bırakır.
    """
    px, py = int(x), int(y)
    ctypes.windll.user32.SetCursorPos(px, py)
    time.sleep(0.06)
    
    screen_width = max(1, ctypes.windll.user32.GetSystemMetrics(0))
    screen_height = max(1, ctypes.windll.user32.GetSystemMetrics(1))
    abs_x = int((px * 65535) / screen_width)
    abs_y = int((py * 65535) / screen_height)
    
    # 1. Interception ile fareyi taşı (Tüm cihaz ID'leri 1..20 kontrol edilir)
    move_stroke = InterceptionMouseStroke()
    move_stroke.state = 0
    move_stroke.flags = 1 # INTERCEPTION_MOUSE_MOVE_ABSOLUTE
    move_stroke.x = abs_x
    move_stroke.y = abs_y
    
    for m_id in range(1, 21):
        try:
            if interception.interception_is_mouse(m_id):
                interception.interception_send(context, m_id, ctypes.byref(move_stroke), 1)
        except Exception:
            pass
    
    # Win32 Fare Taşıma
    try:
        ctypes.windll.user32.mouse_event(0x8000 | 0x0001, abs_x, abs_y, 0, 0)
    except Exception:
        pass
        
    time.sleep(0.05)
    
    # 2. Tıklama Başlat (MouseDown)
    down_state = 4 if right else 1 # 4: RIGHT_DOWN, 1: LEFT_DOWN
    up_state = 8 if right else 2   # 8: RIGHT_UP, 2: LEFT_UP
    win32_down = 0x0008 if right else 0x0002 # MOUSEEVENTF_RIGHTDOWN / MOUSEEVENTF_LEFTDOWN
    win32_up   = 0x0010 if right else 0x0004 # MOUSEEVENTF_RIGHTUP / MOUSEEVENTF_LEFTUP
    
    # Katman A: Interception Donanım Basışı
    down_stroke = InterceptionMouseStroke()
    down_stroke.state = down_state
    down_stroke.flags = 0
    
    for m_id in range(1, 21):
        try:
            if interception.interception_is_mouse(m_id):
                interception.interception_send(context, m_id, ctypes.byref(down_stroke), 1)
        except Exception:
            pass
    
    # Katman B: Win32 Absolute & Relative mouse_event (Touchpad ve Fiziksel Fare uyumu)
    try:
        ctypes.windll.user32.mouse_event(win32_down, 0, 0, 0, 0)
        ctypes.windll.user32.mouse_event(0x8000 | 0x0001 | win32_down, abs_x, abs_y, 0, 0)
    except Exception:
        pass
        
    time.sleep(0.09) # Oyun butonunun basılı durumunu algılaması için basılı tutma süresi
    
    # 3. Tıklama Bırak (MouseUp)
    # Katman A: Interception Donanım Bırakışı
    up_stroke = InterceptionMouseStroke()
    up_stroke.state = up_state
    up_stroke.flags = 0
    
    for m_id in range(1, 21):
        try:
            if interception.interception_is_mouse(m_id):
                interception.interception_send(context, m_id, ctypes.byref(up_stroke), 1)
        except Exception:
            pass
            
    # Katman B: Win32 Absolute & Relative mouse_event Bırakışı
    try:
        ctypes.windll.user32.mouse_event(win32_up, 0, 0, 0, 0)
        ctypes.windll.user32.mouse_event(0x8000 | 0x0001 | win32_up, abs_x, abs_y, 0, 0)
    except Exception:
        pass
        
    time.sleep(0.05)

def get_avoidance_offset(sct, monitor):
    """Sağ üstteki Minimap alanını tarayarak etrafta slot/mob (kırmızı nokta) kümelenmesi var mı kontrol eder.
    Var ise rotadan sapmak için dinamik piksel offseti üretir."""
    try:
        mm_left = monitor["left"] + monitor["width"] - 160
        mm_top = monitor["top"] + 15
        mm_img = np.array(sct.grab({"top": mm_top, "left": mm_left, "width": 140, "height": 140}))
        
        # Minimap üzerindeki canlı kırmızı renkli slot noktalarını tespit et (R>170, G<70, B<70)
        b, g, r = mm_img[:,:,0], mm_img[:,:,1], mm_img[:,:,2]
        red_mask = (r > 170) & (g < 70) & (b < 70)
        red_count = np.sum(red_mask)
        
        if red_count > 25:  # Önümüzde veya etrafımızda mob kümesi var
            # Karakterin slotların yanından kavisli geçmesi için sağa/sola kaçış offseti ver
            return random.choice([-90, 90]), random.choice([-50, 50])
    except:
        pass
    return 0, 0

def send_space():
    send_key_raw(57, 0) # DOWN
    time.sleep(0.01)
    send_key_raw(57, 1) # UP

def is_metin_mode_active():
    """Metin botu modunun çalışabilmesi için:
    1. Bot çalışıyor olmalı (is_running == True)
    2. Karakter ölü olmamalı (is_dead == False)
    3. Metin Botu Aktif seçili olmalı (cfg_metin_enable == True)
    4. Balık botu kapalı olmalı (cfg_fish_enable == False)
    """
    global is_running, is_dead, cfg_metin_enable, cfg_fish_enable
    return is_running and not is_dead and cfg_metin_enable and not cfg_fish_enable

def is_fish_mode_active():
    """Balık botu modunun çalışabilmesi için:
    1. Bot çalışıyor olmalı (is_running == True)
    2. Karakter ölü olmamalı (is_dead == False)
    3. Balık Botu Aktif seçili olmalı (cfg_fish_enable == True)
    4. Metin botu kapalı olmalı (cfg_metin_enable == False)
    """
    global is_running, is_dead, cfg_metin_enable, cfg_fish_enable
    return is_running and not is_dead and cfg_fish_enable and not cfg_metin_enable

def press_space_loop():
    """Oto Vuruş (Boşluk):
    - COMBAT / ENGAGE: Sadece Metin başındayken kilitli vurur
    - CLEARING_MOBS + clearing_at_waypoint=True: tur waypoint'inde durunca vurur
    - Balık Botu açıkken kesinlikle DURUR
    """
    global pause_for_1_key, cfg_space, target_temporarily_lost, bot_state, clearing_at_waypoint
    while True:
        can_attack = (
            (bot_state in ["COMBAT", "ENGAGE"]) or
            (bot_state == "CLEARING_MOBS" and clearing_at_waypoint)
        )
        if is_metin_mode_active() and cfg_space and can_attack and not pause_for_1_key:
            send_space()
            time.sleep(0.01)
        else:
            time.sleep(0.03)

def send_quote():
    # Türk Q klavyede ESC'nin altındaki (" é) tuşunun Scan Code'u 0x29'dur.
    send_key_raw(0x29, 0) 
    time.sleep(random.uniform(0.05, 0.15))
    send_key_raw(0x29, 1)

def send_ctrl_g():
    """Ctrl + G kombinasyonunu basar (Attan İn / Ata Bin)."""
    send_key_raw(0x1D, 0)  # Ctrl DOWN
    time.sleep(0.06)
    send_key_raw(0x22, 0)  # G DOWN
    time.sleep(0.08)
    send_key_raw(0x22, 1)  # G UP
    time.sleep(0.06)
    send_key_raw(0x1D, 1)  # Ctrl UP
    time.sleep(0.6)        # Attan inme / ata binme animasyon süresi

send_ctrl_h = send_ctrl_g

def ensure_mounted_before_ch_change():
    """Kanal değiştirilmeden önce karakterin ata binmiş olmasını sağlar."""
    global is_mounted, cfg_horse_mode
    if cfg_horse_mode and not is_mounted:
        print("[AT MODU] 🐎 Kanal değiştirmeden önce ata biniliyor (Ctrl+G)...")
        send_ctrl_g()
        is_mounted = True
        time.sleep(0.6)

def send_hp_pot():
    """Can potası tuşunu basar (yapılandırılabilir)"""
    key = cfg_hp_key.strip().lower()
    code = SCAN_CODES.get(key, 0x3D) # Varsayılan F3
    send_key_raw(code, 0)
    time.sleep(random.uniform(0.05, 0.15))
    send_key_raw(code, 1)

def send_mp_pot():
    """Mana potası tuşunu basar (yapılandırılabilir)"""
    key = cfg_mp_key.strip().lower()
    code = SCAN_CODES.get(key, 0x3C) # Varsayılan F2
    send_key_raw(code, 0)
    time.sleep(random.uniform(0.05, 0.15))
    send_key_raw(code, 1)

def press_quote_loop():
    global cfg_quote, pause_for_1_key, bot_state
    while True:
        can_loot = (bot_state != "PATROL")
        if is_metin_mode_active() and cfg_quote and can_loot and not pause_for_1_key:
            send_quote()
            time.sleep(random.uniform(0.2, 1.0))
        else:
            time.sleep(0.1)

# --- YETENEK YÖNETİCİSİ (SKILL MANAGER) ---
SCAN_CODES = {
    '1': 0x02, '2': 0x03, '3': 0x04, '4': 0x05, '5': 0x06, '6': 0x07, '7': 0x08, '8': 0x09, '9': 0x0A, '0': 0x0B,
    'q': 0x10, 'w': 0x11, 'e': 0x12, 'r': 0x13, 't': 0x14, 'y': 0x15, 'u': 0x16, 'i': 0x17, 'o': 0x18, 'p': 0x19,
    'a': 0x1E, 's': 0x1F, 'd': 0x20, 'f': 0x21, 'g': 0x22, 'h': 0x23, 'j': 0x24, 'k': 0x25, 'l': 0x26,
    'z': 0x2C, 'x': 0x2D, 'c': 0x2E, 'v': 0x2F, 'b': 0x30, 'n': 0x31, 'm': 0x32,
    'space': 0x39, 'enter': 0x1C, 'shift': 0x2A, 'ctrl': 0x1D, 'alt': 0x38, 'esc': 0x01,
    'f1': 0x3B, 'f2': 0x3C, 'f3': 0x3D, 'f4': 0x3E, 'f5': 0x3F, 'f6': 0x40, 'f7': 0x41, 'f8': 0x42, 'f9': 0x43, 'f10': 0x44, 'f11': 0x57, 'f12': 0x58
}

def send_fish_bait():
    """Yem tuşunu basar (yapılandırılabilir)"""
    key = cfg_fish_bait_key.strip().lower()
    code = SCAN_CODES.get(key, 0x03) # Varsayılan 2
    send_key_raw(code, 0)
    time.sleep(random.uniform(0.05, 0.15))
    send_key_raw(code, 1)

def send_fish_rod():
    """Olta / atış tuşunu basar (yapılandırılabilir)"""
    key = cfg_fish_rod_key.strip().lower()
    code = SCAN_CODES.get(key, 0x04) # Varsayılan 3
    send_key_raw(code, 0)
    time.sleep(random.uniform(0.05, 0.15))
    send_key_raw(code, 1)

def send_fish_rod_instant():
    """Olta tuşunu MILISANIYE seviyesinde gecikmesiz anında basar"""
    key = cfg_fish_rod_key.strip().lower()
    code = SCAN_CODES.get(key, 0x04) # Varsayılan 3
    send_key_raw(code, 0)
    time.sleep(0.01)
    send_key_raw(code, 1)

# RAM Önbelleği: Disk okuma gecikmesini sıfırlamak için resimleri RAM'de tut
bubble_templates_cache = {}

def get_cached_bubble_templates():
    paths = res_glob("balon_*.png")
    if not paths and os.path.exists(res_path("balon.png")):
        paths = [res_path("balon.png")]
    
    templates = []
    for p in paths:
        if p not in bubble_templates_cache:
            img = cv2.imread(p, cv2.IMREAD_GRAYSCALE)
            if img is not None:
                bubble_templates_cache[p] = img
        if p in bubble_templates_cache:
            templates.append(bubble_templates_cache[p])
    return templates

# RAM Önbelleği: Sohbet görsellerini RAM'de tutarak sabit sürücü (Disk I/O) gecikmesini 0.00ms'ye düşür
chat_hook_cache = {}
chat_lost_cache = None

def get_cached_chat_hook_templates():
    paths = res_glob("oltaya_*.png")
    templates = []
    for p in paths:
        if p not in chat_hook_cache:
            img = cv2.imread(p, cv2.IMREAD_GRAYSCALE)
            if img is not None:
                chat_hook_cache[p] = img
        if p in chat_hook_cache:
            templates.append(chat_hook_cache[p])
    return templates

def get_cached_chat_lost_template():
    global chat_lost_cache
    p = res_path("yemi_kaybettin.png")
    if chat_lost_cache is None and os.path.exists(p):
        chat_lost_cache = cv2.imread(p, cv2.IMREAD_GRAYSCALE)
    return chat_lost_cache

def fish_bot_loop():
    """
    Balık Botu Ana Döngüsü - Temiz, Basit, Güvenilir

    Her tur şu adımları sırayla yapar:
      1. Yem Tak  (cfg_fish_bait_key)
      2. Olta At  (cfg_fish_rod_key)
      3. Balık/Küre sohbet yazısını veya baloncuğu bekle
         - "Yemi kaybettin." → 1'e dön
         - "oltaya takılmış..." / "birşey takıldı..." → çek
         - baloncuk görünürse → çek
         - 45 sn geçerse → 1'e dön
      4. Olta Çek  (cfg_fish_rod_key)
      5. Balığın envantere düşmesini bekle → 1'e dön
    """
    global is_running, cfg_fish_enable, is_dead, cfg_fish_bait_key, cfg_fish_rod_key, cfg_fish_delay, cfg_multi_bait, cfg_multi_bait_slot, cfg_multi_bait_count

    def press_key(key_str, count=1):
        key_clean = key_str.strip().lower()
        if key_clean.startswith("alt+"):
            sub_k = key_clean.replace("alt+", "").strip()
            code_alt = 0x38
            code_sub = SCAN_CODES.get(sub_k, 0x02)
            for _ in range(count):
                send_key_raw(code_alt, 0)
                time.sleep(random.uniform(0.08, 0.12))
                send_key_raw(code_sub, 0)
                time.sleep(random.uniform(0.12, 0.16))
                send_key_raw(code_sub, 1)
                time.sleep(random.uniform(0.08, 0.12))
                send_key_raw(code_alt, 1)
                if count > 1:
                    time.sleep(0.15)
        elif key_clean.startswith("ctrl+"):
            sub_k = key_clean.replace("ctrl+", "").strip()
            code_ctrl = 0x1D
            code_sub = SCAN_CODES.get(sub_k, 0x02)
            for _ in range(count):
                send_key_raw(code_ctrl, 0)
                time.sleep(random.uniform(0.08, 0.12))
                send_key_raw(code_sub, 0)
                time.sleep(random.uniform(0.12, 0.16))
                send_key_raw(code_sub, 1)
                time.sleep(random.uniform(0.08, 0.12))
                send_key_raw(code_ctrl, 1)
                if count > 1:
                    time.sleep(0.15)
        elif key_clean.startswith("shift+"):
            sub_k = key_clean.replace("shift+", "").strip()
            code_shift = 0x2A
            code_sub = SCAN_CODES.get(sub_k, 0x02)
            for _ in range(count):
                send_key_raw(code_shift, 0)
                time.sleep(random.uniform(0.08, 0.12))
                send_key_raw(code_sub, 0)
                time.sleep(random.uniform(0.12, 0.16))
                send_key_raw(code_sub, 1)
                time.sleep(random.uniform(0.08, 0.12))
                send_key_raw(code_shift, 1)
                if count > 1:
                    time.sleep(0.15)
        else:
            code = SCAN_CODES.get(key_clean, None)
            if code:
                for _ in range(count):
                    send_key_raw(code, 0)
                    time.sleep(random.uniform(0.10, 0.15))
                    send_key_raw(code, 1)
                    if count > 1:
                        time.sleep(0.15)

    def scan_chat(sct, monitor):
        """Sohbet kutusunun ALT bölümünü tarayarak balık tespiti yapar."""
        region = {
            "top":    monitor["top"]  + int(monitor["height"] * 0.76),
            "left":   monitor["left"],
            "width":  int(monitor["width"]  * 0.38),
            "height": int(monitor["height"] * 0.20)
        }
        try:
            c_img  = np.array(sct.grab(region))
            c_gray = cv2.cvtColor(c_img, cv2.COLOR_BGRA2GRAY)

            # Balık takıldı mı?
            for t in get_cached_chat_hook_templates():
                res = cv2.matchTemplate(c_gray, t, cv2.TM_CCOEFF_NORMED)
                if res.max() >= 0.78:
                    return "hooked"
        except Exception:
            pass
        return None

    def scan_bubble(sct, monitor):
        """Karakter başı bölgesinde baloncuk taraması yapar."""
        templates = get_cached_bubble_templates()
        if not templates:
            return False
        cx = monitor["left"] + monitor["width"]  // 2
        cy = monitor["top"]  + monitor["height"] // 2
        region = {
            "top":    max(0, cy - 260),
            "left":   max(0, cx - 280),
            "width":  560,
            "height": 380
        }
        try:
            img  = np.array(sct.grab(region))
            gray = cv2.cvtColor(img, cv2.COLOR_BGRA2GRAY)
            for t in templates:
                res = cv2.matchTemplate(gray, t, cv2.TM_CCOEFF_NORMED)
                if res.max() >= 0.60:
                    return True
        except Exception:
            pass
        return False

    def isleep(seconds):
        """Kesintiye uğrayabilen sleep: is_running veya cfg_fish_enable False olursa anında durur."""
        end = time.time() + seconds
        while time.time() < end:
            if not is_fish_mode_active():
                return False   # iptal edildi
            time.sleep(0.1)
        return True            # tamamlandı

    def do_armor_cancel():
        if cfg_fish_armor_anim and cfg_armor_pos:
            time.sleep(0.25)
            ax = cfg_armor_pos.get("x")
            ay = cfg_armor_pos.get("y")
            if ax is not None and ay is not None:
                print(f"[BALIK BOTU] 🛡️ Zırh animasyon sıfırlama yapılıyor (Sağ tık: X={ax}, Y={ay})...")
                send_mouse_click_raw(ax, ay, right=True)
                time.sleep(0.25)

    global fish_needs_reset
    with mss.mss() as sct:
        was_interrupted = False
        while True:
            if not is_fish_mode_active():
                was_interrupted = True
                time.sleep(0.3)
                continue

            if fish_needs_reset or was_interrupted:
                fish_needs_reset = False
                was_interrupted = False
                time.sleep(0.4)

            monitor = sct.monitors[1]

            # ── ADIM 1: YEM TAK ──────────────────────────────────────
            if cfg_auto_bait:
                time.sleep(0.4) # Karakter duruşunun ve envanterin tamamen sıfırlanması için emniyet beklemesi
                if not is_fish_mode_active():
                    was_interrupted = True
                    continue
                
                if cfg_multi_bait:
                    keys = get_multi_bait_key_list()
                    total_slots = len(keys)
                    if cfg_multi_bait_slot < 1 or cfg_multi_bait_slot > total_slots:
                        cfg_multi_bait_slot = 1
                    curr_idx = cfg_multi_bait_slot - 1
                    bait_key = keys[curr_idx]

                    cfg_multi_bait_count += 1
                    remaining = max(0, 200 - cfg_multi_bait_count)
                    print(f"[BALIK BOTU] 🪱 Yem takılıyor (Tuş: [{bait_key.upper()}] | Slot: {cfg_multi_bait_slot}/{total_slots} | Kullanılan: {cfg_multi_bait_count}/200 - Kalan: {remaining})...")
                    press_key(bait_key, count=1)
                    
                    if cfg_multi_bait_count >= 200:
                        cfg_multi_bait_count = 0
                        cfg_multi_bait_slot = (cfg_multi_bait_slot % total_slots) + 1
                        next_key = keys[cfg_multi_bait_slot - 1]
                        print(f"[BALIK BOTU] 🔄 200 Yem bitti! Sıradaki yem tuşuna geçildi: [{next_key.upper()}] (Slot {cfg_multi_bait_slot}/{total_slots})")
                    
                    save_config()
                    update_multi_bait_ui()
                else:
                    print(f"[BALIK BOTU] 🪱 Yem takılıyor (Tuş: {cfg_fish_bait_key})...")
                    press_key(cfg_fish_bait_key, count=1)

                if not isleep(1.4):   # yem animasyonu — kesilirse başa dön
                    was_interrupted = True
                    continue

            # ── ADIM 2: OLTA AT ───────────────────────────────────────
            if not is_fish_mode_active():
                was_interrupted = True
                continue
            time.sleep(0.3) # Yemin envanterde işlenmesi için emniyet beklemesi
            if not is_fish_mode_active():
                was_interrupted = True
                continue
            print(f"[BALIK BOTU] 🎣 Olta suya atılıyor (Tuş: {cfg_fish_rod_key})...")
            press_key(cfg_fish_rod_key, count=1)
            cast_time = time.time()

            # Olta atıldıktan sonra su hareketinin oturması için kısa bekleme
            if not isleep(2.5):
                was_interrupted = True
                continue

            # ── ADIM 3: BEKLE (Balık / Baloncuk / Timeout) ──────────────
            print("[BALIK BOTU] 🔍 Balık bekleniyor...")
            action = None
            while is_running and cfg_fish_enable and not is_dead:
                elapsed = time.time() - cast_time

                # 25 sn timeout
                if elapsed > 25.0:
                    print("[BALIK BOTU] ⏰ 25 saniye doldu (Timeout), olta karaya çekilip yeniden başlanıyor...")
                    press_key(cfg_fish_rod_key, count=1)   # geri çek
                    isleep(2.0)
                    action = "timeout"
                    break

                # Sohbet tarama
                chat_result = scan_chat(sct, monitor)
                if chat_result == "hooked":
                    print("[BALIK BOTU] 💎 Sohbet: Balık takıldı!")
                    action = "pull"
                    break

                # Baloncuk tarama
                if scan_bubble(sct, monitor):
                    print("[BALIK BOTU] 💡 Baloncuk algılandı!")
                    action = "pull"
                    break

                time.sleep(0.05)   # ~20 tarama/sn

            if not (is_running and cfg_fish_enable):
                was_interrupted = True
                continue

            if action != "pull":
                # Timeout durumunda başa dön (Adım 1)
                continue

            # ── ADIM 4: OLTA ÇEK (SADECE BALIK GELDİĞİNDE) ─────────────
            delay_val = get_random_fish_delay()

            if delay_val > 0:
                print(f"[BALIK BOTU] 🎲 {delay_val:.2f}sn rastgele gecikme bekleniyor (Aralık: {cfg_fish_delay_min}-{cfg_fish_delay_max}sn)...")
                if not isleep(delay_val):
                    was_interrupted = True
                    continue

            print(f"[BALIK BOTU] 🎣 Olta çekiliyor (Tuş: {cfg_fish_rod_key})!")
            press_key(cfg_fish_rod_key, count=1)
            
            # SADECE BURADA ZIRH DEĞİŞTİRME YAPILIR:
            do_armor_cancel()

            # ── ADIM 5: BALIK ENVANTERİN DÜŞME ANİMASYONU ───────────
            print("[BALIK BOTU] ✅ Balık çekildi! Yeni tura hazırlanılıyor...")
            # Zırh Giyme aktifse animasyon anında sıfırlandığından 0.6sn bekleme yeterlidir.
            # Zırh Giyme kapalıysa Metin2 doğal balık çekme animasyonu için 2.5sn beklenir.
            post_pull_wait = 0.6 if (cfg_fish_armor_anim and cfg_armor_pos) else 2.5
            if not isleep(post_pull_wait):
                was_interrupted = True
                continue
            # → başa dön (Adım 1)

skills_config = [] # GUI tarafında doldurulacak

def reset_skills():
    """Tüm aktif yeteneklerin cooldown zamanını sıfırlar ve 2 saniyelik gecikme sayacını başlatır."""
    global bot_start_time
    bot_start_time = time.time()
    for skill in skills_config:
        skill["last_cast"] = 0
    if is_metin_mode_active():
        print("[BİLGİ] Yetenek süreleri sıfırlandı. 2 saniye sonra skiller kullanılacak...")

def send_custom_key(code):
    send_key_raw(code, 0)
    time.sleep(random.uniform(0.05, 0.15))
    send_key_raw(code, 1)

def skill_manager_loop():
    global bot_start_time, is_mounted, cfg_horse_mode, bot_state, last_metin_pos
    while True:
        if is_metin_mode_active():
            now = time.time()
            
            # Sadece METİN BAŞINDAYKEN (COMBAT / ENGAGE modunda) skil bas!
            # Metin'e yürürken, LOOT yaparken veya CH değiştirirken skil basmayı engelle.
            if bot_state not in ["COMBAT", "ENGAGE"]:
                time.sleep(0.2)
                continue

            # Bot başladıktan veya CH değiştikten sonra EN AZ 2 saniye bekle
            if bot_start_time == 0 or (now - bot_start_time < 2.0):
                time.sleep(0.2)
                continue

            for skill in skills_config:
                try:
                    if not skill["enabled"].get():
                        continue
                        
                    cooldown_str = skill["cooldown"].get()
                    if not cooldown_str.isdigit():
                        continue
                    cooldown = int(cooldown_str)
                    
                    key_str = skill["key"].get().strip().lower()
                    if not key_str or key_str not in SCAN_CODES:
                        continue
                        
                    if (now - skill["last_cast"]) >= cooldown:
                        pause_for_1_key = True  # Otomatik vuruşu durdur (çakışmayı önlemek için)
                        time.sleep(0.4)         # Vuruş animasyonunun bitmesi için bekle
                        
                        # Atta isek skilleri basmak için önce attan in
                        if cfg_horse_mode and is_mounted:
                            print("[AT MODU] 🐎 Skil basmak için attan iniliyor (Ctrl+G)...")
                            send_ctrl_g()
                            is_mounted = False
                            time.sleep(0.6)
                        
                        code = SCAN_CODES[key_str]
                        send_custom_key(code)   # Yeteneği kullan
                        print(f"[YETENEK] ✨ Skil kullanıldı: {key_str.upper()}")
                        
                        skill["last_cast"] = time.time()
                        time.sleep(1.0)
                        
                        # Sıradaki diğer yeteneklerin de hemen kullanılıp kullanılmayacağını kontrol et
                        has_more_skills_ready = False
                        future_now = time.time()
                        for s_other in skills_config:
                            if s_other["enabled"].get() and s_other["cooldown"].get().isdigit():
                                cd_other = int(s_other["cooldown"].get())
                                k_other = s_other["key"].get().strip().lower()
                                if k_other in SCAN_CODES and (future_now - s_other["last_cast"]) >= cd_other:
                                    has_more_skills_ready = True
                                    break

                        # Başka hemen kullanılacak yetenek kalmadıysa tekrar ata bin
                        if cfg_horse_mode and not is_mounted and not has_more_skills_ready:
                            print("[AT MODU] 🐎 Tüm skiller basıldı, ata tekrar biniliyor (Ctrl+G)...")
                            send_ctrl_g()
                            is_mounted = True
                            time.sleep(0.6)
                            
                            # Ata bindikten hemen sonra Metin'e VURUŞ KİLİTLENMESİNİ TAZELE!
                            if last_metin_pos is not None:
                                time.sleep(0.5)  # At binişi animasyonu bitmeden kilitleme yapma
                                send_mouse_click_raw(last_metin_pos[0], last_metin_pos[1])
                                time.sleep(0.15)
                                send_mouse_click_raw(last_metin_pos[0], last_metin_pos[1])  # Çift tıkla (kilit garantisi)
                                print(f"[AT MODU] ⚔️ Metin vuruşu tazeledi (kilitlendi): X={last_metin_pos[0]}, Y={last_metin_pos[1]}")

                        pause_for_1_key = False
                        break
                except Exception as e:
                    pass
        time.sleep(0.1)

import glob

def send_esc():
    """ESC tuşunu basar (Scan code: 0x01)"""
    send_key_raw(0x01, 0)
    time.sleep(0.05)
    send_key_raw(0x01, 1)

def click_channel_change_button():
    """ESC menüsündeki 'Kanal değiştir' butonunu arar ve tıklar."""
    ensure_mounted_before_ch_change()
    p = res_path("kanal_degistir.png")
    if not os.path.exists(p):
        print(f"[HATA] '{p}' bulunamadı!")
        return False
    template = cv2.imread(p, cv2.IMREAD_GRAYSCALE)
    if template is None:
        return False
    with mss.mss() as sct:
        monitor = sct.monitors[1]
        img = np.array(sct.grab(monitor))
        gray = cv2.cvtColor(img, cv2.COLOR_BGRA2GRAY)
        res = cv2.matchTemplate(gray, template, cv2.TM_CCOEFF_NORMED)
        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)
        if max_val >= 0.65:
            h, w = template.shape
            cx = monitor["left"] + max_loc[0] + (w // 2)
            cy = monitor["top"] + max_loc[1] + (h // 2)
            print(f"[BİLGİ] 'Kanal değiştir' butonu bulundu ({cx},{cy}). Tıklanıyor...")
            
            # Fareyi buton üzerine götür ve bekle (hover efekti için)
            ctypes.windll.user32.SetCursorPos(int(cx), int(cy))
            time.sleep(0.2)
            
            # Tıklamayı hem Win32 API hem Interception ile kesin gönder
            _click_pos(cx, cy)
            time.sleep(0.15)
            _click_pos(cx, cy)
            time.sleep(0.15)
            send_mouse_click_raw(cx, cy)
            return True
        else:
            print(f"[UYARI] 'Kanal değiştir' butonu ekranda bulunamadı (Eşleşme: {max_val:.2f})")
            return False

def auto_change_channel():
    """
    Ekranda 'Kanal seçimi' penceresini 5 saniye boyunca arar.
    Aktif CH'yi (kırmızı/parlak renkte olanı) tespit eder.
    Bir altındaki CH'ye tıklar (CH4 ise CH1'e döner) ve 'Tamam' butonuna tıklar.
    """
    header_path = res_path("kanal_secimi_header.png")
    if not os.path.exists(header_path):
        print("[HATA] 'kanal_secimi_header.png' bulunamadı!")
        return False

    template = cv2.imread(header_path, cv2.IMREAD_GRAYSCALE)
    if template is None:
        return False

    with mss.mss() as sct:
        monitor = sct.monitors[1]
        
        # 'Kanal seçimi' penceresinin tam açılması için 5 saniye boyunca ekranda tara
        start_wait = time.time()
        found_win = False
        win_x, win_y = 0, 0
        full_bgr = None
        gray = None
        
        while time.time() - start_wait < 5.0:
            img_bgra = np.array(sct.grab(monitor))
            full_bgr = cv2.cvtColor(img_bgra, cv2.COLOR_BGRA2BGR)
            gray = cv2.cvtColor(full_bgr, cv2.COLOR_BGR2GRAY)
            
            res = cv2.matchTemplate(gray, template, cv2.TM_CCOEFF_NORMED)
            min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)
            
            if max_val >= 0.60:
                win_x = monitor["left"] + max_loc[0]
                win_y = monitor["top"] + max_loc[1]
                found_win = True
                break
            time.sleep(0.3)

        if not found_win:
            print("[UYARI] 'Kanal seçimi' penceresi ekranda bulunamadı!")
            return False

        # 4 CH butonunun merkez Y ofsetleri (CH1, CH2, CH3, CH4)
        ch_offsets = [49, 81, 113, 145]

        # Aktif CH'yi renk analizi ile bul (Kırmızı kanalı R-B en yüksek olan aktif CH'dir)
        ch_scores = []
        for idx, offset_y in enumerate(ch_offsets, start=1):
            px_x = int(win_x + 25)
            px_y = int(win_y + offset_y)
            if 0 <= px_y < full_bgr.shape[0] and 0 <= px_x < full_bgr.shape[1]:
                b, g, r = full_bgr[px_y, px_x].astype(int)
                score = r - b
            else:
                score = 0
            ch_scores.append((score, idx))

        ch_scores.sort(reverse=True)
        active_ch = ch_scores[0][1]
        next_ch = (active_ch % 4) + 1  # CH1->CH2, CH2->CH3, CH3->CH4, CH4->CH1

        print(f"[CH] 📊 Aktif Kanal: CH{active_ch} → Yeni Kanal: CH{next_ch} seçiliyor...")

        # Sıradaki CH butonunun merkez koordinatları
        target_offset_y = ch_offsets[next_ch - 1]
        btn_x = win_x + 90
        btn_y = win_y + target_offset_y

        # 1. Sıradaki CH butonuna git, bekle ve tıkla
        ctypes.windll.user32.SetCursorPos(int(btn_x), int(btn_y))
        time.sleep(0.25)
        _click_pos(btn_x, btn_y)
        time.sleep(0.15)
        _click_pos(btn_x, btn_y)
        time.sleep(0.2)
        send_mouse_click_raw(btn_x, btn_y)
        time.sleep(0.5)

        # 2. 'Tamam' butonunun koordinatı
        tamam_x = win_x + 40
        tamam_y = win_y + 168

        if os.path.exists("ch_tamam.png"):
            tamam_tpl = cv2.imread("ch_tamam.png", cv2.IMREAD_GRAYSCALE)
            if tamam_tpl is not None:
                t_res = cv2.matchTemplate(gray, tamam_tpl, cv2.TM_CCOEFF_NORMED)
                _, t_max_val, _, t_max_loc = cv2.minMaxLoc(t_res)
                if t_max_val >= 0.60:
                    th, tw = tamam_tpl.shape
                    tamam_x = monitor["left"] + t_max_loc[0] + (tw // 2)
                    tamam_y = monitor["top"] + t_max_loc[1] + (th // 2)

        # 3. 'Tamam' butonuna git, bekle ve tıkla
        print(f"[CH] 'Tamam' butonuna tıklanıyor ({tamam_x}, {tamam_y})...")
        ctypes.windll.user32.SetCursorPos(int(tamam_x), int(tamam_y))
        time.sleep(0.25)
        _click_pos(tamam_x, tamam_y)
        time.sleep(0.15)
        _click_pos(tamam_x, tamam_y)
        time.sleep(0.2)
        send_mouse_click_raw(tamam_x, tamam_y)

        print(f"[CH] ✅ CH{next_ch} seçildi ve Tamam'a tıklandı! Kanal değiştiriliyor...")
        reset_skills()
        return True

def check_metin_status_loop():
    global is_running, cfg_target, target_temporarily_lost, bot_state, cfg_clearing, clearing_at_waypoint, cfg_fish_enable, last_metin_pos
    
    with mss.mss() as sct:
        monitor = sct.monitors[1] # Birincil ekran
        # Artık tüm ekranı arayacağız çünkü metin 3D dünyada herhangi bir yerde olabilir
        search_region = {
            "top": monitor["top"],
            "left": monitor["left"],
            "width": monitor["width"],
            "height": monitor["height"]
        }
        
        not_found_count = 0
        combat_start_time = 0
        last_combat_click_time = 0
        last_archer_scan_time = 0
        clearing_start_time = 0
        return_start_time = 0
        metin_lost_start_time = 0
        idle_no_metin_start = 0
        # Etraf turu: metnin 8 yönünü sırayla gezen sabit offset listesi
        # (x_offset, y_offset) — piksel cinsinden
        CLEARING_WAYPOINTS = [
            ( 220,    0),   # Sağ
            ( 220, -160),   # Sağ-yukarı
            (   0, -200),   # Yukarı
            (-220, -160),   # Sol-yukarı
            (-220,    0),   # Sol
            (-220,  160),   # Sol-aşağı
            (   0,  200),   # Aşağı
            ( 220,  160),   # Sağ-aşağı
        ]
        clearing_wp_index = 0
        clearing_wp_time  = 0
        last_metin_pos    = None  # Son bilinen metin konumu (ekranda görünmese bile kullanılır)
        hp_triggered_clearing = False  # HP düşüşü nedeniyle tur tetiklendi mi
        clearing_interval = random.uniform(55, 65)  # Her tur arasındaki süre (~60sn / 1 dk)
        
        patrol_wp_index = 0
        patrol_direction = 1  # 1 = İleri (Son noktaya doğru), -1 = Geri (Başlangıca doğru)
        last_patrol_click_time = 0
        
        while True:
            if is_metin_mode_active() and cfg_target and not is_dead:
                now = time.time()
                
                # Sadece arayüzden seçilen metin dosyalarını hedeflere ekle
                metin_template_paths = []
                if cfg_metin_default and os.path.exists(res_path("hedef.png")): metin_template_paths.append(res_path("hedef.png"))
                if cfg_metin_hirs and os.path.exists(res_path("hedef_hirs.png")): metin_template_paths.append(res_path("hedef_hirs.png"))
                if cfg_metin_savas and os.path.exists(res_path("hedef_savas.png")): metin_template_paths.append(res_path("hedef_savas.png"))
                if cfg_metin_dovus and os.path.exists(res_path("hedef_dovus.png")): metin_template_paths.append(res_path("hedef_dovus.png"))
                if cfg_metin_siyah and os.path.exists(res_path("hedef_siyah.png")): metin_template_paths.append(res_path("hedef_siyah.png"))
                if cfg_metin_uzuntu and os.path.exists(res_path("hedef_uzuntu.png")): metin_template_paths.append(res_path("hedef_uzuntu.png"))
                if cfg_metin_ruh and os.path.exists(res_path("hedef_ruh.png")): metin_template_paths.append(res_path("hedef_ruh.png"))
                
                archer_template_paths = res_glob("okcu_*.png")
                if not archer_template_paths and os.path.exists(res_path("okcu.png")):
                    archer_template_paths = [res_path("okcu.png")]
                
                if not metin_template_paths and bot_state != "ENGAGE_ARCHER":
                    time.sleep(1)
                    continue
                    
                sct_img = sct.grab(search_region)
                img = np.array(sct_img)
                gray_img = cv2.cvtColor(img, cv2.COLOR_BGRA2GRAY)
                
                found_metin = False
                found_archer = False
                match_center = None
                
                # --- 1. METİN TARAMASI ---
                for path in metin_template_paths:
                    template = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
                    if template is None: continue
                    res = cv2.matchTemplate(gray_img, template, cv2.TM_CCOEFF_NORMED)
                    loc = np.where(res >= 0.75)
                    
                    # Ekranın en üstündeki (can barındaki) yazıları yoksay, fakat hedefte olup olmadığını anla
                    valid_match_idx = -1
                    is_target_bar_visible = False
                    for idx in range(len(loc[0])):
                        if loc[0][idx] < 120: 
                            is_target_bar_visible = True
                        else:
                            if valid_match_idx == -1: # İlk geçerli (yerdeki) metni al
                                valid_match_idx = idx
                            
                    if valid_match_idx != -1 or (is_target_bar_visible and bot_state in ["COMBAT", "ENGAGE", "RUNNING_TO_TARGET"]):
                        found_metin = True
                        if valid_match_idx != -1:
                            h, w = template.shape
                            match_y = loc[0][valid_match_idx]
                            match_x = loc[1][valid_match_idx]
                            
                            # 3 Boyutlu perspektif için mesafeye (Y koordinatına) göre dinamik tıklama offseti hesapla
                            dynamic_y_offset = int(65 + (match_y * 0.09))
                            match_center = (monitor["left"] + match_x + (w // 2), monitor["top"] + match_y + (h // 2) + dynamic_y_offset)
                        break
                
                # --- HEDEF YÖNETİMİ ---
                if found_metin:
                    target_temporarily_lost = False
                    metin_lost_start_time = 0  # Hedef göründüğü an kayıp sayacını sıfırla
                    idle_no_metin_start = 0    # Metin görünce idle kanal değiştirme sayacını sıfırla
                    
                    # Son bilinen metin konumunu güncelle
                    if match_center is not None:
                        last_metin_pos = match_center
                    
                    if bot_state == "PATROL" or bot_state == "IDLE":
                        if match_center is not None:
                            print(f"[BİLGİ] Metin bulundu! Hedefe koşuluyor: X={match_center[0]}, Y={match_center[1]}")
                            bot_state = "RUNNING_TO_TARGET"
                            send_mouse_click_raw(match_center[0], match_center[1])
                            combat_start_time = now
                        
                    elif bot_state == "RUNNING_TO_TARGET":
                        # Tıkladık ve koşuyoruz. 1.8 sn geçtikten sonra hedefe varıldı kabul et VEYA target bar görünürse hemen geç
                        if is_target_bar_visible or (now - combat_start_time >= 1.8):
                            print("[BİLGİ] Hedefe varıldı, savaşa (COMBAT) başlanıyor!")
                            bot_state = "COMBAT"
                            last_combat_click_time = now
                        elif not is_target_bar_visible and (now - combat_start_time > 2.5) and match_center is not None:
                            # 2.5 saniye geçtiyse ve kilitlenmediysek (ıskaladıysak) tekrar tıkla
                            print(f"[BİLGİ] Kilitlenme başarısız, tekrar tıklanıyor: X={match_center[0]}, Y={match_center[1]}")
                            send_mouse_click_raw(match_center[0], match_center[1])
                            combat_start_time = now
                            
                    elif bot_state in ["COMBAT", "ENGAGE"]:
                        if not is_target_bar_visible:
                            # Savaşıyorduk ama kilit kaybolmuş! Tekrar tıklamalıyız.
                            if now - combat_start_time > 1.5 and match_center is not None:
                                print("[BİLGİ] Hedef kilidi kaybedildi, tekrar tıklanıyor...")
                                send_mouse_click_raw(match_center[0], match_center[1])
                                combat_start_time = now
                                last_combat_click_time = now
                                bot_state = "COMBAT"
                            # SIKIŞMA ÇÖZÜCÜ: Hedef barı 6 saniyedir açılamadıysa slotların engelini kaldır ve tekrar tıkla
                            elif now - last_combat_click_time > 6.0:
                                print("[UYARI] 🚨 Sıkışma / Vuramama algılandı! Etraftaki slotlar temizlenip metne tekrar kilitleniliyor...")
                                if match_center is not None:
                                    for _ in range(4):
                                        send_space()
                                        time.sleep(0.08)
                                    send_mouse_click_raw(match_center[0], match_center[1])
                                    last_combat_click_time = now
                        else:
                            # PERİYODİK SALDIRI TAZELEME:
                            # Her 4 saniyede bir hedefe tıklayarak saldırı kilitlenmesini tazeler
                            if match_center is not None and now - last_combat_click_time > 4.0:
                                print("[BİLGİ] Metin saldırısı tazeleniyor (tıklandı)...")
                                send_mouse_click_raw(match_center[0], match_center[1])
                                last_combat_click_time = now
                            
                            # ETRAF TURU TETİKİ: SADECE 1 dakikada bir (60 saniye)
                            timer_expired = (now - combat_start_time > clearing_interval)
                            
                            if cfg_clearing and match_center is not None and timer_expired:
                                print(f"[BİLGİ] Etraf turu başlıyor ({clearing_interval:.0f}s timer, 8 yön)...")
                                bot_state = "CLEARING_MOBS"
                                clearing_start_time = now
                                clearing_wp_index = 0
                                clearing_wp_time  = 0
                                clearing_interval = random.uniform(55, 65)  # Sonraki tur için yeni süre (1 dk)
                            
                    elif bot_state == "RETURNING_TO_METIN":
                        # can_attack False olduğu için vurmayı bırakıp koşacak
                        if is_target_bar_visible and now - return_start_time > 1.0:
                            print("[BİLGİ] Metne başarıyla dönüldü, vurmaya devam ediliyor!")
                            bot_state = "COMBAT"
                            combat_start_time = now
                        else:
                            # Sürekli metne tıkla ki yürüme eylemi devam etsin
                            if int((now - return_start_time) * 10) % 10 == 0 and last_metin_pos is not None:
                                send_mouse_click_raw(last_metin_pos[0], last_metin_pos[1])
                                
                            if now - return_start_time > 10.0:
                                print("[BİLGİ] 10 saniye geçmesine rağmen metne ulaşılamadı. Önü kapalı, yolu açmak için vuruluyor!")
                                bot_state = "CLEARING_MOBS"
                                clearing_start_time = now

                else:
                    # Metin ekranda görünmüyor
                    target_temporarily_lost = True
                    
                    if bot_state in ["COMBAT", "ENGAGE", "ENGAGE_ARCHER", "RUNNING_TO_TARGET"]:
                        if metin_lost_start_time == 0:
                            metin_lost_start_time = now
                        elif now - metin_lost_start_time >= 3.5:
                            print("[BİLGİ] Hedef 3.5 saniye boyunca ekranda görünmedi. Kesildi kabul ediliyor!")
                            metin_lost_start_time = 0
                            
                            if cfg_ch_change:
                                bot_state = "LOOT"
                                print("[BİLGİ] CH Değiştir aktif: Yerdeki eşyaları toplamak için 10 saniye bekleniyor...")
                                time.sleep(10)
                                
                                ensure_mounted_before_ch_change()
                                print("[BİLGİ] ESC tuşuna basılıyor...")
                                send_esc()
                                time.sleep(1.0)
                                
                                print("[BİLGİ] 'Kanal değiştir' butonuna tıklanıyor...")
                                if click_channel_change_button():
                                    time.sleep(1.5)  # Kanal seçimi penceresinin açılması için bekle
                                    print("[BİLGİ] Otomatik kanal seçimi yapılıyor...")
                                    auto_change_channel()
                                    time.sleep(5.0)  # Harita/Kanal yükleme ekranı için bekle
                            else:
                                print("[BİLGİ] Yerdeki eşyalar toplanıyor...")
                                bot_state = "LOOT"
                                time.sleep(6)
                            
                            if is_running and cfg_patrol:
                                bot_state = "PATROL"
                                print("[BİLGİ] Devriyeye dönülüyor...")
                            else:
                                bot_state = "IDLE"
                    
                    elif bot_state == "IDLE" and cfg_ch_change:
                        if idle_no_metin_start == 0:
                            idle_no_metin_start = now
                        elif now - idle_no_metin_start >= 12.0:
                            print("[BİLGİ] Ekranda 12 saniyedir Metin bulunamadı. Otomatik kanal değiştiriliyor...")
                            idle_no_metin_start = 0
                            ensure_mounted_before_ch_change()
                            send_esc()
                            time.sleep(1.0)
                            if click_channel_change_button():
                                time.sleep(1.5)
                                auto_change_channel()
                                time.sleep(5.0)

                # -------------------------------------------------------
                # CLEARING_MOBS: found_metin'den bağımsız — last_metin_pos kullanır
                # Yola çıkarken: Space KAPALI | Noktaya varınca: Space AÇIK (Vurur)
                # -------------------------------------------------------
                if bot_state == "CLEARING_MOBS" and last_metin_pos is not None:
                    if clearing_wp_index < len(CLEARING_WAYPOINTS):
                        if clearing_wp_time == 0 or (now - clearing_wp_time) >= 1.5:
                            if clearing_wp_time != 0:
                                clearing_wp_index += 1
                            
                            if clearing_wp_index < len(CLEARING_WAYPOINTS):
                                ox, oy = CLEARING_WAYPOINTS[clearing_wp_index]
                                tx = last_metin_pos[0] + ox
                                ty = last_metin_pos[1] + oy
                                print(f"[BİLGİ] Alan turu: yön {clearing_wp_index+1}/{len(CLEARING_WAYPOINTS)} → ({ox:+d}, {oy:+d}) | Koşuluyor...")
                                clearing_at_waypoint = False   # HAREKET — Space KAPALI
                                send_mouse_click_raw(tx, ty)
                                clearing_wp_time = time.time()
                        else:
                            elapsed = now - clearing_wp_time
                            if elapsed >= 0.3:
                                if not clearing_at_waypoint:
                                    print(f"[BİLGİ] Noktaya varıldı ({clearing_wp_index+1}/{len(CLEARING_WAYPOINTS)}), boşlukla vuruluyor...")
                                clearing_at_waypoint = True   # VARILDI — Space AÇIK
                            else:
                                clearing_at_waypoint = False  # HAREKET — Space KAPALI
                    else:
                        clearing_at_waypoint = False
                        print("[BİLGİ] Alan turu tamamlandı, metne dönülüyor...")
                        clearing_wp_index = 0
                        clearing_wp_time = 0
                        bot_state = "RETURNING_TO_METIN"
                        return_start_time = now

                elif bot_state == "RETURNING_TO_METIN" and last_metin_pos is not None:
                    if is_target_bar_visible and now - return_start_time > 1.8:
                        print("[BİLGİ] Metne başarıyla dönüldü, vurmaya devam ediliyor!")
                        send_mouse_click_raw(last_metin_pos[0], last_metin_pos[1])  # Metne vuruş başlat
                        bot_state = "COMBAT"
                        combat_start_time = now
                        last_combat_click_time = now
                    else:
                        # Her 1 saniyede bir son bilinen metine tıkla
                        if int(now - return_start_time) != int(now - return_start_time - 0.2):
                            send_mouse_click_raw(last_metin_pos[0], last_metin_pos[1])
                        if now - return_start_time > 10.0:
                            print("[BİLGİ] 10 sn geçti, metne ulaşılamadı — tekrar tur yapılıyor...")
                            bot_state = "CLEARING_MOBS"
                            clearing_start_time = now
                            clearing_wp_index = 0
                            clearing_wp_time = 0
                    
                elif bot_state == "PATROL":
                    # Metin bulunamadı, devriye modu aktif:
                    # Gidiş-Dönüş (Ping-Pong) mantığı ile tam belirlenen rota sınırları içinde kalır
                    if now - last_patrol_click_time > 2.8:
                        off_x, off_y = get_avoidance_offset(sct, monitor)
                        center_x = monitor["left"] + (monitor["width"] // 2)
                        center_y = monitor["top"] + (monitor["height"] // 2)
                        
                        if len(route_waypoints) > 0:
                            # Sınır güvenlik kontrolü
                            if patrol_wp_index >= len(route_waypoints):
                                patrol_wp_index = len(route_waypoints) - 1
                                patrol_direction = -1
                            elif patrol_wp_index < 0:
                                patrol_wp_index = 0
                                patrol_direction = 1

                            wp = route_waypoints[patrol_wp_index]
                            
                            # Koordinat sınırı aktifse mesafe/sınır kontrolü uygulanır
                            if cfg_use_coords:
                                print(f"[BÖLGE SINIRI] Koordinat Alanı: X({cfg_min_x}-{cfg_max_x}) Y({cfg_min_y}-{cfg_max_y}) içinde devriye atılıyor.")

                            if patrol_direction == 1:
                                target_x = wp["x"] + off_x
                                target_y = wp["y"] + off_y
                                print(f"[DEVRİYE] İleri → Rota {patrol_wp_index+1}/{len(route_waypoints)} noktasına gidiliyor...")
                            else:
                                dx = wp["x"] - center_x
                                dy = wp["y"] - center_y
                                target_x = center_x - dx + off_x
                                target_y = center_y + abs(dy) + 60 + off_y
                                print(f"[DEVRİYE] Geri Dönüş ← Rota {patrol_wp_index+1}/{len(route_waypoints)} noktasına dönülüyor...")
                            
                            send_mouse_click_raw(target_x, target_y)
                            
                            # İndeksi yön doğrultusunda güncelle
                            patrol_wp_index += patrol_direction
                            
                            # Uç noktalara varıldığında yönü değiştir (Ping-Pong)
                            if patrol_wp_index >= len(route_waypoints):
                                print("[DEVRİYE] 🚩 Rota sonuna ulaşıldı! (Son noktadan geri dönülüyor...)")
                                patrol_direction = -1
                                patrol_wp_index = len(route_waypoints) - 1
                            elif patrol_wp_index < 0:
                                print("[DEVRİYE] 🏁 Rota başlangıcına dönüldü! (Tekrar ileri gidiliyor...)")
                                patrol_direction = 1
                                patrol_wp_index = 0
                        else:
                            # Kayıtlı rota yoksa 3D oyun ekranının ileri ufkuna (üst-orta kısmına) tıklayarak akıcı şekilde koş
                            c_x = monitor["left"] + (monitor["width"] // 2)
                            c_y = monitor["top"] + int(monitor["height"] * 0.38)
                            target_x = c_x + off_x + random.randint(-40, 40)
                            target_y = c_y + off_y + random.randint(-20, 20)
                            print("[DEVRİYE] Otomatik devriye geziliyor (Metin taranıyor)...")
                            send_mouse_click_raw(target_x, target_y)
                            
                        last_patrol_click_time = now

                time.sleep(0.2) # Hedefin kaybolduğunu ÇOK DAHA HIZLI (saniyede 5 kez) fark etmesi için
            else:
                target_temporarily_lost = False
                time.sleep(0.1)

def check_pot_status_loop():
    global is_running, cfg_hp, cfg_mp, hp_pixel, mp_pixel, cfg_hp_key, cfg_mp_key, cfg_pot_alarm
    
    hp_empty_start_time = 0
    mp_empty_start_time = 0
    last_alarm_time = 0
    
    with mss.mss() as sct:
        while True:
            if is_metin_mode_active() and (cfg_hp or cfg_mp):
                now = time.time()
                
                # Can Kontrolü
                hp_is_low = False
                if cfg_hp and hp_pixel:
                    img = np.array(sct.grab({"top": hp_pixel["y"], "left": hp_pixel["x"], "width": 1, "height": 1}))
                    b, g, r, a = img[0][0]
                    if int(r) < int(hp_pixel["r"]) - 30 or int(r) < 80:
                        hp_is_low = True
                        for _ in range(3):
                            send_hp_pot()
                            time.sleep(0.15)
                
                if hp_is_low:
                    if hp_empty_start_time == 0:
                        hp_empty_start_time = now
                    elif now - hp_empty_start_time >= 4.0: # 4 saniyedir can doldurulamıyor -> POT BİTTİ
                        if cfg_pot_alarm and (now - last_alarm_time >= 2.5):
                            print("[UYARI] ⚠️ HP POTU BİTTİ! (Can doldurulamıyor)")
                            try:
                                winsound.Beep(2200, 400)
                                winsound.Beep(1800, 300)
                            except:
                                pass
                            last_alarm_time = now
                else:
                    hp_empty_start_time = 0
                        
                # Mana Kontrolü
                mp_is_low = False
                if cfg_mp and mp_pixel:
                    img = np.array(sct.grab({"top": mp_pixel["y"], "left": mp_pixel["x"], "width": 1, "height": 1}))
                    b, g, r, a = img[0][0]
                    if int(b) < int(mp_pixel["b"]) - 30 or int(b) < 80:
                        mp_is_low = True
                        for _ in range(3):
                            send_mp_pot()
                            time.sleep(0.15)
                
                if mp_is_low:
                    if mp_empty_start_time == 0:
                        mp_empty_start_time = now
                    elif now - mp_empty_start_time >= 4.0: # 4 saniyedir mana doldurulamıyor -> MANA BİTTİ
                        if cfg_pot_alarm and (now - last_alarm_time >= 2.5):
                            print("[UYARI] ⚠️ MP POTU BİTTİ! (Mana doldurulamıyor)")
                            try:
                                winsound.Beep(1800, 300)
                                winsound.Beep(1400, 300)
                            except:
                                pass
                            last_alarm_time = now
                else:
                    mp_empty_start_time = 0
                        
                time.sleep(0.15)  # Kontrol sıklığı
            else:
                time.sleep(0.1)

def click_item_loop():
    global is_running, cfg_item, is_dead
    
    item_template_path = "item.png"
    
    with mss.mss() as sct:
        monitor = sct.monitors[1] # Tüm ekran
        search_region = {
            "top": monitor["top"],
            "left": monitor["left"],
            "width": monitor["width"],
            "height": monitor["height"]
        }
        
        while True:
            if is_metin_mode_active() and cfg_item:
                if not os.path.exists(item_template_path):
                    time.sleep(1)
                    continue
                    
                template = cv2.imread(item_template_path, cv2.IMREAD_GRAYSCALE)
                if template is None:
                    time.sleep(1)
                    continue
                    
                sct_img = sct.grab(search_region)
                img = np.array(sct_img)
                gray_img = cv2.cvtColor(img, cv2.COLOR_BGRA2GRAY)
                
                # Eşya yazısını ara (Yazılar için yüksek eşleşme oranı gerekir)
                res = cv2.matchTemplate(gray_img, template, cv2.TM_CCOEFF_NORMED)
                threshold = 0.8
                loc = np.where(res >= threshold)
                
                if len(loc[0]) > 0:
                    # Bulunan ilk "NART's" yazısının tam ortasını hesapla
                    h, w = template.shape
                    match_y = loc[0][0]
                    match_x = loc[1][0]
                    
                    center_x = monitor["left"] + match_x + (w // 2)
                    center_y = monitor["top"] + match_y + (h // 2)
                    
                    # Fareyi oraya götür ve sol tıkla
                    ctypes.windll.user32.SetCursorPos(int(center_x), int(center_y))
                    time.sleep(0.05)
                    ctypes.windll.user32.mouse_event(0x0002, 0, 0, 0, 0) # Sol Tık Bas
                    time.sleep(0.05)
                    ctypes.windll.user32.mouse_event(0x0004, 0, 0, 0, 0) # Sol Tık Bırak
                    
                    time.sleep(0.5) # Üst üste çok hızlı tıklamaması için bekle
                else:
                    time.sleep(0.2)
            else:
                time.sleep(0.1)

def auto_revive_loop():
    global is_running, cfg_revive, is_dead, bot_state, last_metin_pos
    
    revive_template_path = "olum.png"
    
    with mss.mss() as sct:
        monitor = sct.monitors[1] # Tüm ekran
        search_region = {
            "top": monitor["top"],
            "left": monitor["left"],
            "width": monitor["width"],
            "height": monitor["height"]
        }
        
        while True:
            if is_metin_mode_active() and cfg_revive:
                if not os.path.exists(revive_template_path):
                    time.sleep(1)
                    continue
                    
                template = cv2.imread(revive_template_path, cv2.IMREAD_GRAYSCALE)
                if template is None:
                    time.sleep(1)
                    continue
                    
                sct_img = sct.grab(search_region)
                img = np.array(sct_img)
                gray_img = cv2.cvtColor(img, cv2.COLOR_BGRA2GRAY)
                
                res = cv2.matchTemplate(gray_img, template, cv2.TM_CCOEFF_NORMED)
                threshold = 0.8 # Hassasiyeti eski haline döndürdük
                loc = np.where(res >= threshold)
                
                if len(loc[0]) > 0 and not is_dead:
                    is_dead = True # Ölüm bayrağını çek (diğer looplar durur)
                    bot_state = "IDLE" # Eski koşu/savaş hedefini derhal sıfırla
                    last_metin_pos = None # Eski metin konumunu sil ki dirilince oraya koşmasın
                    print("[BİLGİ] Karakter öldü! 13 saniye bekleniyor...")
                    time.sleep(13)
                    
                    # Resmi bulduğumuz koordinatın tam ortasını hesapla
                    h, w = template.shape
                    match_y = loc[0][0]
                    match_x = loc[1][0]
                    
                    center_x = monitor["left"] + match_x + (w // 2)
                    center_y = monitor["top"] + match_y + (h // 2)
                    
                    print(f"[BİLGİ] Fareniz şu koordinata götürülüp tıklanacak (Interception ile): X={center_x}, Y={center_y}")
                    
                    # Interception ile kernel seviyesinde fareyi hareket ettir ve tıkla
                    send_mouse_click_raw(center_x, center_y)
                    time.sleep(0.3)
                    send_mouse_click_raw(center_x, center_y) # Garanti olması için çift tıkla
                    
                    time.sleep(2) # Dirilmesini bekle
                    
                    print("[BİLGİ] Can ve mana dolduruluyor...")
                    for _ in range(5):
                        send_hp_pot()
                        send_mp_pot()
                        time.sleep(0.3)
                        
                    print("[BİLGİ] Dirilme tamamlandı, bot tekrar aktif!")
                    bot_state = "IDLE" # Dirildikten sonra eski yere koşma, sıfır durumdan başla
                    last_metin_pos = None
                    is_dead = False # Bayrağı indir (diğer looplar tekrar başlar)
                    time.sleep(2) # Ölüm yazısının tamamen kaybolması için bekle
                else:
                    time.sleep(1)
            else:
                time.sleep(1)

def patrol_loop():
    global bot_state, is_running, route_waypoints
    current_wp_idx = 0
    last_click_time = 0
    
    with mss.mss() as sct:
        screen_width = ctypes.windll.user32.GetSystemMetrics(0)
        screen_height = ctypes.windll.user32.GetSystemMetrics(1)
        # Ekranın tam ortasından biraz yukarıda 200x200 bir alan (Stuck tespiti için)
        stuck_region = {
            "top": max(0, (screen_height // 2) - 150),
            "left": max(0, (screen_width // 2) - 100),
            "width": 200,
            "height": 200
        }
        
        last_frame = None
        stuck_time = 0
        
        while True:
            # Otomatik state değişimi: Eklendikten sonra bot zaten çalışıyorsa
            if is_metin_mode_active() and cfg_patrol and len(route_waypoints) > 0 and bot_state == "IDLE":
                bot_state = "PATROL"
                
            if is_metin_mode_active() and cfg_patrol and bot_state == "PATROL" and route_waypoints:
                now = time.time()
                
                # Her 6 saniyede bir sıradaki rotaya tıkla (15 sn çok uzundu, karakter duruyordu)
                if now - last_click_time > 6:
                    if current_wp_idx >= len(route_waypoints):
                        current_wp_idx = 0
                    wp = route_waypoints[current_wp_idx]
                    print(f"[DEVRİYE] Nokta {current_wp_idx+1} tıklanıyor: X={wp['x']}, Y={wp['y']}")
                    send_mouse_click_raw(wp['x'], wp['y'])
                    last_click_time = now
                    current_wp_idx += 1
                    
                # Her 4 saniyede bir sıkışma (stuck) kontrolü yap (süreyi uzattık)
                if now - stuck_time > 4:
                    stuck_time = now
                    img = np.array(sct.grab(stuck_region))
                    gray = cv2.cvtColor(img, cv2.COLOR_BGRA2GRAY)
                    
                    if last_frame is not None:
                        diff = cv2.absdiff(gray, last_frame)
                        non_zero_count = np.count_nonzero(diff > 10)
                        
                        # Eşik değerini çok düşürdük (2000'den 500'e). Sadece cidden hareketsiz kaldığında tetiklenecek.
                        if non_zero_count < 500:
                            print("[UYARI] Karakter takıldı! Anti-stuck manevrası yapılıyor...")
                            send_key_raw(0x1F, 0) # S (Geri) Bas
                            time.sleep(1.5)
                            send_key_raw(0x1F, 1)
                            
                            send_key_raw(0x20, 0) # D (Sağ) Bas (A yerine D daha mantıklı olabilir)
                            time.sleep(1.0)
                            send_key_raw(0x20, 1)
                            
                            last_click_time = 0 
                            if current_wp_idx > 0:
                                current_wp_idx -= 1
                    
                    last_frame = gray
                
                time.sleep(0.5)
            else:
                last_frame = None
                time.sleep(0.5)

def toggle_running(event=None):
    global is_running
    if not is_running:
        start_bot()
    else:
        stop_bot()


def hotkey_toggle():
    if calibrating_armor_pos:
        return
    try:
        root.after(0, toggle_running)
    except:
        pass

def start_bot():
    """3 saniyelik geri sayımdan sonra botu başlatır."""
    btn_start.config(state=tk.DISABLED)
    _countdown(3)

def _countdown(remaining):
    """Geri sayım tamamlanınca botu gerçekten başlatır."""
    if remaining > 0:
        status_dot.config(fg="#FFB300")
        status_label.config(text=f"BAŞLATILIYOR... {remaining}", fg="#FFB300")
        root.after(1000, _countdown, remaining - 1)
    else:
        global is_running, bot_state, fish_needs_reset
        is_running = True
        fish_needs_reset = True
        reset_skills()
        if cfg_patrol and len(route_waypoints) > 0:
            bot_state = "PATROL"
        else:
            bot_state = "IDLE"
        update_ui()

def stop_bot():
    global is_running, bot_state
    is_running = False
    bot_state = "IDLE"
    if 'var_fish_enable' in globals() and var_fish_enable.get():
        try:
            send_fish_rod()
        except Exception:
            pass
    update_ui()
def update_ui():
    if is_running:
        status_label.config(text="● DURUM: AKTİF (ÇALIŞIYOR)", fg="#00FF7F")
        btn_start.config(state=tk.DISABLED, bg="#2A2D34", fg="#555555")
        btn_stop.config(state=tk.NORMAL, bg="#FF4C4C", fg="#FFFFFF")
    else:
        status_label.config(text="● DURUM: BEKLİYOR", fg="#FF4C4C")
        btn_start.config(state=tk.NORMAL, bg="#00E676", fg="#FFFFFF")
        btn_stop.config(state=tk.DISABLED, bg="#2A2D34", fg="#555555")

# --- THREAD BAŞLATMA ---
t_space = threading.Thread(target=press_space_loop)
t_space.daemon = True
t_space.start()

t_quote = threading.Thread(target=press_quote_loop)
t_quote.daemon = True
t_quote.start()

t_skill = threading.Thread(target=skill_manager_loop)
t_skill.daemon = True
t_skill.start()

t_vision = threading.Thread(target=check_metin_status_loop)
t_vision.daemon = True
t_vision.start()

t_pot = threading.Thread(target=check_pot_status_loop)
t_pot.daemon = True
t_pot.start()

t_item = threading.Thread(target=click_item_loop)
t_item.daemon = True
t_item.start()

t_revive = threading.Thread(target=auto_revive_loop)
t_revive.daemon = True
t_revive.start()

t_patrol = threading.Thread(target=patrol_loop)
t_patrol.daemon = True
t_patrol.start()

t_fish = threading.Thread(target=fish_bot_loop)
t_fish.daemon = True
t_fish.start()

_bv_ok_tpl = None
_bv_text_tpl  = None
_bv_templates_loaded = False

def _load_bv_templates():
    global _bv_ok_tpl, _bv_text_tpl, _bv_templates_loaded
    if _bv_templates_loaded:
        return
    ok_p = res_path("bot_verify_ok.png")
    if os.path.exists(ok_p):
        _bv_ok_tpl = cv2.imread(ok_p, cv2.IMREAD_GRAYSCALE)
    txt_p = res_path("bot_verify_yellow_text.png")
    if os.path.exists(txt_p):
        _bv_text_tpl = cv2.imread(txt_p, cv2.IMREAD_GRAYSCALE)
    _bv_templates_loaded = True

def _find_verify_window(full_bgr):
    """
    Bot Verify penceresini ekranda arar.
    Kullanıcının birebir ekran görüntüsünden alınan 1:1 şablonlar ile %100 kusursuz çift doğrulama:
    1. bot_verify_ok.png (88x24px OK Butonu) şablonu (>= 0.80)
    2. bot_verify_yellow_text.png (86x10px Sarı '<svside> Bot Verify' Metni) şablonu (>= 0.75)
    Her iki şablon da aynı anda doğrulandığında pencere konumu döner.
    Boş ekranda ASLA tetiklenmez.
    """
    _load_bv_templates()
    gray = cv2.cvtColor(full_bgr, cv2.COLOR_BGR2GRAY)
    h_img, w_img = gray.shape

    if _bv_ok_tpl is None:
        return None

    res_ok = cv2.matchTemplate(gray, _bv_ok_tpl, cv2.TM_CCOEFF_NORMED)
    _, max_val_ok, _, max_loc_ok = cv2.minMaxLoc(res_ok)

    if max_val_ok >= 0.80:
        ox, oy = max_loc_ok

        wx = max(0, ox - 28)
        wy = max(0, oy - 142)
        ww, wh = 144, 186

        # Çift Doğrulama: OK butonunun hemen altındaki sarı metin şablonunu kontrol et
        if _bv_text_tpl is not None:
            sub_y1, sub_y2 = oy + 15, min(h_img, oy + 50)
            sub_x1, sub_x2 = max(0, ox - 15), min(w_img, ox + 100)
            sub_gray = gray[sub_y1:sub_y2, sub_x1:sub_x2]

            if sub_gray.size > 0:
                res_txt = cv2.matchTemplate(sub_gray, _bv_text_tpl, cv2.TM_CCOEFF_NORMED)
                _, max_val_txt, _, _ = cv2.minMaxLoc(res_txt)
                if max_val_txt >= 0.70:
                    return wx, wy, ww, wh
        else:
            return wx, wy, ww, wh

    return None

def _click_pos(x, y):
    """Interception + Win32 Hibrit tıklaması. İmleci taşır ve sol tık üretir."""
    send_mouse_click_raw(x, y, right=False)

def verify_alert_loop():
    """
    Her 0.8 saniyede bir ekranda Bot Verify doğrulama penceresini arar.
    Algılandığında botu derhal durdurur ve codevoice.mp3 sesini kesintisiz döngüde çalar.
    Pencere ekrandan kaybolana (kullanıcı manuel çözene) kadar ses çalar ve botları bekletir,
    pencere kapandığında sesi anında susturur ve bot modüllerini otomatik tekrar başlatır.
    """
    global is_running
    is_alerting = False

    with mss.mss() as sct:
        while True:
            time.sleep(0.8)
            if not is_running:
                if is_alerting:
                    stop_code_voice_loop()
                    is_alerting = False
                continue

            try:
                monitor = sct.monitors[1]
                img_bgra = np.array(sct.grab(monitor))
                full_bgr = cv2.cvtColor(img_bgra, cv2.COLOR_BGRA2BGR)

                result = _find_verify_window(full_bgr)
                if result is not None:
                    wx, wy, ww, wh = result
                    if not is_alerting:
                        print(f"[BOT VERIFY UYARISI] 🔐 Bot Verify doğrulama penceresi algılandı! ({wx},{wy}) {ww}x{wh}")
                        is_alerting = True
                        disable_active_bot_modules(reason="Bot Verify Doğrulama Penceresi Algılandı")
                        if cfg_captcha_alarm:
                            start_code_voice_loop()
                        else:
                            try:
                                winsound.Beep(1200, 300)
                            except Exception:
                                pass
                else:
                    if is_alerting:
                        print("[BOT VERIFY UYARISI] 🧹 Bot Verify penceresi kapandı/çözüldü. Ses susturuldu ve bot modülleri tekrar aktif ediliyor...")
                        stop_code_voice_loop()
                        is_alerting = False
                        try:
                            root.after(0, restore_active_bot_modules)
                        except Exception:
                            pass
            except Exception as e:
                pass

# Geriye dönük uyumluluk için alias
captcha_solver_loop = verify_alert_loop

def check_and_close_horse_menu():
    """
    Attan inerken veya tıklarken yanlışlıkla açılan
    'Atınla ne yapmak istiyorsun?' menüsünü algılar ve 'Hiçbirşey (pencereyi kapat)'
    butonuna tıklayarak pencereyi otomatik kapatır.
    """
    btn_path = res_path("hicbirsey_btn.png")
    header_path = res_path("at_menu_header.png")
    
    if not os.path.exists(btn_path) and not os.path.exists(header_path):
        return False
        
    try:
        with mss.mss() as sct:
            monitor = sct.monitors[1]
            img_bgra = np.array(sct.grab(monitor))
            gray = cv2.cvtColor(img_bgra, cv2.COLOR_BGRA2GRAY)
            
            # 1. Doğrudan 'Hiçbirşey (pencereyi kapat)' butonunu ara
            if os.path.exists(btn_path):
                btn_tpl = cv2.imread(btn_path, cv2.IMREAD_GRAYSCALE)
                if btn_tpl is not None:
                    res = cv2.matchTemplate(gray, btn_tpl, cv2.TM_CCOEFF_NORMED)
                    min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)
                    if max_val >= 0.70:
                        h, w = btn_tpl.shape
                        cx = monitor["left"] + max_loc[0] + (w // 2)
                        cy = monitor["top"] + max_loc[1] + (h // 2)
                        print(f"[AT MENÜSÜ] 🐴 Yanlışlıkla at menüsü açıldı! 'Hiçbirşey (pencereyi kapat)' tıklanıyor... ({cx},{cy})")
                        _click_pos(cx, cy)
                        time.sleep(0.15)
                        _click_pos(cx, cy)
                        time.sleep(0.2)
                        return True

            # 2. Buton şablonu uyuşmazsa başlık üzerinden hizala
            if os.path.exists(header_path):
                hdr_tpl = cv2.imread(header_path, cv2.IMREAD_GRAYSCALE)
                if hdr_tpl is not None:
                    res = cv2.matchTemplate(gray, hdr_tpl, cv2.TM_CCOEFF_NORMED)
                    min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)
                    if max_val >= 0.70:
                        cx = monitor["left"] + max_loc[0] + 120
                        cy = monitor["top"] + max_loc[1] + 225
                        print(f"[AT MENÜSÜ] 🐴 At menüsü başlığı algılandı! 'Hiçbirşey' tıklanıyor... ({cx},{cy})")
                        _click_pos(cx, cy)
                        time.sleep(0.15)
                        _click_pos(cx, cy)
                        time.sleep(0.2)
                        return True
    except Exception:
        pass
    return False

previous_bot_module = None # "METIN", "FISH" veya None
fish_needs_reset = False   # PM veya kesinti sonrası balık oltasını sıfırlama bayrağı

def disable_active_bot_modules(reason="Belirtilmedi"):
    global previous_bot_module, cfg_metin_enable, cfg_fish_enable
    print(f"[BOT DURDURMA BİLGİSİ] 🛑 Bot Modülleri Pasife Alındı! Sebep: {reason}")
    try:
        # Önceden çalışan aktif bot modülünü hatırla
        if cfg_metin_enable or (var_metin_enable and var_metin_enable.get()):
            previous_bot_module = "METIN"
        elif cfg_fish_enable or (var_fish_enable and var_fish_enable.get()):
            previous_bot_module = "FISH"
            try:
                send_fish_rod()
            except Exception:
                pass
        
        # ANINDA SENKRON OLARAK KÜRESEL BAYRAKLARI KAPAT (Thread Yarışını Önlemek İçin)
        cfg_metin_enable = False
        cfg_fish_enable = False
        
        if var_metin_enable:
            var_metin_enable.set(False)
        if var_fish_enable:
            var_fish_enable.set(False)
        apply_settings()
        refresh_all_visuals()
    except Exception:
        pass

def restore_active_bot_modules():
    global previous_bot_module, fish_needs_reset
    try:
        # Ekranda hala Bot Verify penceresi varsa ASLA botu tekrar aktif etme!
        with mss.mss() as sct:
            mon = sct.monitors[1]
            img_bgra = np.array(sct.grab(mon))
            full_bgr = cv2.cvtColor(img_bgra, cv2.COLOR_BGRA2BGR)
            if _find_verify_window(full_bgr) is not None:
                print("[CAPTCHA] ✋ Bot Verify penceresi ekranda olduğu için bot modülleri aktif EDİLMEDİ!")
                return

        if previous_bot_module == "METIN":
            print("[BOT] 🔄 Metin Botu tekrar aktif ediliyor...")
            var_metin_enable.set(True)
        elif previous_bot_module == "FISH":
            print("[BOT] 🔄 Balık Botu tekrar aktif ediliyor...")
            fish_needs_reset = True
            var_fish_enable.set(True)
        
        previous_bot_module = None
        apply_settings()
        refresh_all_visuals()
    except Exception:
        pass

def is_pm_window_open():
    """
    Ekranda fısıltı/mesaj penceresinin ('Gönder' butonu) açık olup olmadığını kontrol eder.
    Yanlış tetiklenmeyi önlemek için eşik değeri 0.88'e yükseltilmiştir.
    """
    btn_path = res_path("pm_gonder_btn.png")
    if not os.path.exists(btn_path):
        return False
    try:
        template = cv2.imread(btn_path, cv2.IMREAD_COLOR)
        if template is None:
            return False
        with mss.mss() as sct:
            monitor = sct.monitors[1]
            img_bgra = np.array(sct.grab(monitor))
            img_bgr = cv2.cvtColor(img_bgra, cv2.COLOR_BGRA2BGR)
            
            res = cv2.matchTemplate(img_bgr, template, cv2.TM_CCOEFF_NORMED)
            min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)
            return max_val >= 0.88
    except Exception:
        pass
    return False

def check_and_handle_pm_letter():
    """
    Ekranda PM (Fısıltı) mektup ikonunu (mektup.png) arar.
    """
    global is_running
    if not is_running or not cfg_pm_stop:
        return False

    # 1. EKRANDA BOT VERIFY DOĞRULAMA PENCERESİ VARSA ASLA PM MEKTUBU İŞLEMİ YAPMA!
    try:
        with mss.mss() as sct_check:
            mon_check = sct_check.monitors[1]
            full_check = cv2.cvtColor(np.array(sct_check.grab(mon_check)), cv2.COLOR_BGRA2BGR)
            if _find_verify_window(full_check) is not None:
                return False
    except Exception:
        pass

    # MESAJ PENCERESİ ZATEN AÇIKSA BİR DAHA ASLA TIKLAMA!
    if is_pm_window_open():
        disable_active_bot_modules(reason="Fısıltı/PM Mesaj Penceresi Açık ('Gönder' butonu bulundu)")
        return True

    tpl_path = res_path("mektup.png")
    if not os.path.exists(tpl_path):
        return False

    try:
        template = cv2.imread(tpl_path, cv2.IMREAD_COLOR)
        if template is None:
            return False

        with mss.mss() as sct:
            monitor = sct.monitors[1]
            w_mon = monitor["width"]
            h_mon = monitor["height"]

            # Mektup ikonu mini haritanın altında (ekranın sağ %32'lik kısmı, Y %5-%65)
            roi_monitor = {
                "top": monitor["top"] + int(h_mon * 0.05),
                "left": monitor["left"] + int(w_mon * 0.68),
                "width": int(w_mon * 0.32),
                "height": int(h_mon * 0.60)
            }

            img_bgra = np.array(sct.grab(roi_monitor))
            img_bgr = cv2.cvtColor(img_bgra, cv2.COLOR_BGRA2BGR)

            # --- Şablon Eşleme ---
            res = cv2.matchTemplate(img_bgr, template, cv2.TM_CCOEFF_NORMED)
            min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)
            h_tpl, w_tpl, _ = template.shape

            is_detected = False
            cx, cy = 0, 0

            # Şablon eşleşme skoru >= 0.88 olmalı (Etkinlik butonlarıyla karışmaması için)
            if max_val >= 0.88:
                is_detected = True
                cx = roi_monitor["left"] + max_loc[0] + (w_tpl // 2)
                cy = roi_monitor["top"] + max_loc[1] + (h_tpl // 2)

            if is_detected:
                print(f"[✉️ PM ALARMI] Fısıltı mektubu algılandı ({cx},{cy}) [Skor: {max_val:.2f}]! Interception ile 1 kere tıklanıyor...")

                # 1. Mektuba Interception Kernel Sürücüsü ile 1 kere tıkla
                try:
                    send_mouse_click_raw(cx, cy)
                except Exception:
                    _click_pos(cx, cy)

                # Aktif Bot Modülünü Pasife Al
                try:
                    disable_active_bot_modules(reason="Gelen Fısıltı/PM Mektubu Algılandı")
                except Exception:
                    pass

                # Ses Uyarısı Ver (Arka Planda) - cfg_captcha_alarm aktifse
                if cfg_captcha_alarm:
                    play_pm_voice()

                # 2. Pencerenin açılması için 0.6sn bekle
                time.sleep(0.6)

                # 3. Oyuncu İsmini Tanı ve Kaçıncı Mesajı Olduğuna Göre Yanıtı Seç
                reply_text = cfg_pm_reply_1
                try:
                    with mss.mss() as sct_n:
                        mon_n = sct_n.monitors[1]
                        img_n = cv2.cvtColor(np.array(sct_n.grab(mon_n)), cv2.COLOR_BGRA2BGR)
                        g_path = res_path("pm_gonder_btn.png")
                        if os.path.exists(g_path):
                            g_t = cv2.imread(g_path, cv2.IMREAD_COLOR)
                            if g_t is not None:
                                res_n = cv2.matchTemplate(img_n, g_t, cv2.TM_CCOEFF_NORMED)
                                _, max_n, _, loc_n = cv2.minMaxLoc(res_n)
                                print(f"[✉️ PM ALARMI] İsim kutusu taranıyor... Gönder eşleşme skoru: {max_n:.2f}")
                                if max_n >= 0.45:
                                    nx1 = max(0, loc_n[0] - 116)
                                    ny1 = max(0, loc_n[1] - 143)
                                    nx2 = min(img_n.shape[1], nx1 + 110)
                                    ny2 = min(img_n.shape[0], ny1 + 20)
                                    name_crop = img_n[ny1:ny2, nx1:nx2]
                                    if name_crop.size > 0:
                                        gray_n = cv2.cvtColor(name_crop, cv2.COLOR_BGR2GRAY)
                                        _, thresh_n = cv2.threshold(gray_n, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
                                        pts = cv2.findNonZero(thresh_n)
                                        if pts is not None:
                                            x, y, w, h = cv2.boundingRect(pts)
                                            text_crop = thresh_n[y:y+h, x:x+w] if (w > 4 and h > 4) else thresh_n
                                        else:
                                            text_crop = thresh_n

                                        resized_n = cv2.resize(text_crop, (16, 16))
                                        avg_n = resized_n.mean()
                                        hash_str = ''.join(str(b) for b in (resized_n > avg_n).astype(int).flatten())

                                        # Hamming Mesafesi Esnek Oyuncu Eşleştirme (45 bite kadar piksel farkı kabul edilir)
                                        MATCH_THRESHOLD = 45
                                        best_key = None
                                        min_dist = 999
                                        for saved_hash in pm_senders_history:
                                            dist = sum(c1 != c2 for c1, c2 in zip(hash_str, saved_hash))
                                            if dist < min_dist:
                                                min_dist = dist
                                                best_key = saved_hash

                                        if best_key is not None and min_dist <= MATCH_THRESHOLD:
                                            pm_senders_history[best_key] += 1
                                            count = pm_senders_history[best_key]
                                            print(f"[✉️ PM ALARMI] 👤 Tanıdık oyuncu algılandı! (Hash farkı: {min_dist} bit, Mesaj sayısı: {count})")
                                        else:
                                            pm_senders_history[hash_str] = 1
                                            count = 1
                                            print(f"[✉️ PM ALARMI] 👤 Yeni oyuncu kaydedildi! (Mesaj sayısı: 1)")

                                        if count == 1:
                                            reply_text = cfg_pm_reply_1
                                            print(f"[✉️ PM ALARMI] 📩 1. Yanıt seçildi: '{reply_text}'")
                                        elif count == 2:
                                            reply_text = cfg_pm_reply_2
                                            print(f"[✉️ PM ALARMI] 📩 2. Yanıt seçildi: '{reply_text}'")
                                        else:
                                            reply_text = cfg_pm_reply_3
                                            print(f"[✉️ PM ALARMI] 📩 3+. Yanıt seçildi: '{reply_text}'")
                except Exception as e_hash:
                    print(f"[PM ALARMI] İsim tanıma hatası: {e_hash}")

                # 4. Interception Kernel Sürücüsü ile Seçilen Yanıtı Yaz ve Enter/Gönder'e Tıkla
                try:
                    print(f"[✉️ PM ALARMI] Interception klavye sürücüsü ile yazılıyor: '{reply_text}'")
                    send_string_interception(reply_text)
                    time.sleep(0.2)
                    send_key_raw(28, 0) # Enter Down
                    time.sleep(0.05)
                    send_key_raw(28, 1) # Enter Up
                    time.sleep(0.3)

                    # Gönder butonunun şablonu ile konumunu bulup tıkla (Garanti olsun)
                    gonder_tpl_path = res_path("pm_gonder_btn.png")
                    if os.path.exists(gonder_tpl_path):
                        g_tpl = cv2.imread(gonder_tpl_path, cv2.IMREAD_COLOR)
                        if g_tpl is not None:
                            with mss.mss() as sct_g:
                                mon_g = sct_g.monitors[1]
                                img_g = cv2.cvtColor(np.array(sct_g.grab(mon_g)), cv2.COLOR_BGRA2BGR)
                                res_g = cv2.matchTemplate(img_g, g_tpl, cv2.TM_CCOEFF_NORMED)
                                _, max_g, _, loc_g = cv2.minMaxLoc(res_g)
                                if max_g >= 0.70:
                                    gh, gw, _ = g_tpl.shape
                                    gcx = mon_g["left"] + loc_g[0] + (gw // 2)
                                    gcy = mon_g["top"] + loc_g[1] + (gh // 2)
                                    print(f"[✉️ PM ALARMI] 'Gönder' butonuna tıklanıyor ({gcx},{gcy})...")
                                    send_mouse_click_raw(gcx, gcy)
                                    time.sleep(0.3)
                except Exception as e_write:
                    print(f"[PM ALARMI] Cevap yazma hatası: {e_write}")

                # 4. Sağ Üstteki 'X' Çarpı İkonuna Tıklayarak Pencereyi Kapat
                try:
                    time.sleep(0.3)
                    close_tpl_path = res_path("pm_window_close.png")
                    gonder_tpl_path = res_path("pm_gonder_btn.png")
                    closed_by_click = False

                    # A) Şablon Eşleme ile Sağ Üstteki 'X' Çarpı Butonunu Bul ve Tıkla
                    if os.path.exists(close_tpl_path):
                        c_tpl = cv2.imread(close_tpl_path, cv2.IMREAD_COLOR)
                        if c_tpl is not None:
                            with mss.mss() as sct_c:
                                mon_c = sct_c.monitors[1]
                                img_c = cv2.cvtColor(np.array(sct_c.grab(mon_c)), cv2.COLOR_BGRA2BGR)
                                res_c = cv2.matchTemplate(img_c, c_tpl, cv2.TM_CCOEFF_NORMED)
                                _, max_c, _, loc_c = cv2.minMaxLoc(res_c)
                                if max_c >= 0.58:
                                    ch_h, cw_w, _ = c_tpl.shape
                                    ccx = mon_c["left"] + loc_c[0] + (cw_w // 2)
                                    ccy = mon_c["top"] + loc_c[1] + (ch_h // 2)
                                    print(f"[✉️ PM ALARMI] 'X' kapatma butonuna tıklanıyor ({ccx},{ccy}) [Skor: {max_c:.2f}]...")
                                    send_mouse_click_raw(ccx, ccy)
                                    closed_by_click = True

                    # B) Eğer şablon eşleşmezse 'Gönder' butonunun konumundan 'X' butonunun yerini hesaplayıp tıkla
                    if not closed_by_click and os.path.exists(gonder_tpl_path):
                        g_tpl = cv2.imread(gonder_tpl_path, cv2.IMREAD_COLOR)
                        if g_tpl is not None:
                            with mss.mss() as sct_g:
                                mon_g = sct_g.monitors[1]
                                img_g = cv2.cvtColor(np.array(sct_g.grab(mon_g)), cv2.COLOR_BGRA2BGR)
                                res_g = cv2.matchTemplate(img_g, g_tpl, cv2.TM_CCOEFF_NORMED)
                                _, max_g, _, loc_g = cv2.minMaxLoc(res_g)
                                if max_g >= 0.55:
                                    gh, gw, _ = g_tpl.shape
                                    # X butonu Gönder butonunun 30px sağında ve 143px yukarısındadır
                                    rel_cx = mon_g["left"] + loc_g[0] + (gw // 2) + 30
                                    rel_cy = mon_g["top"] + loc_g[1] + (gh // 2) - 143
                                    print(f"[✉️ PM ALARMI] 'X' kapatma butonuna nispi konumdan tıklanıyor ({rel_cx},{rel_cy})...")
                                    send_mouse_click_raw(rel_cx, rel_cy)

                except Exception as e_close:
                    print(f"[PM ALARMI] Pencere kapatma hatası: {e_close}")

                # 5. Mesaj Yanıtlanıp Kapatıldıktan Sonra Önceki Bot Modülünü (Metin veya Balık) Otomatik Tekrar Aktif Et
                try:
                    root.after(0, restore_active_bot_modules)
                except Exception:
                    pass

                # 6. Tekrar algılamasın diye 3.5 saniye bekle
                time.sleep(3.5)
                return True
    except Exception:
        pass
    return False

def horse_menu_closer_loop():
    while True:
        if is_metin_mode_active():
            check_and_close_horse_menu()
        time.sleep(0.4)

def pm_detector_loop():
    while True:
        if is_running and cfg_pm_stop:
            check_and_handle_pm_letter()
        time.sleep(0.4)

t_horse = threading.Thread(target=horse_menu_closer_loop)
t_horse.daemon = True
t_horse.start()

t_captcha = threading.Thread(target=captcha_solver_loop)
t_captcha.daemon = True
t_captcha.start()

t_pm = threading.Thread(target=pm_detector_loop)
t_pm.daemon = True
t_pm.start()


# ==========================================
# --- MODERN VIP ARAYÜZ (GUI) TASARIMI ---
# ==========================================
BG_COLOR     = "#090A0F"   # Derin Siyah / Onyx Arka Plan
FG_COLOR     = "#F3F4F6"   # Parlak Beyaz Metin
ACCENT       = "#8B5CF6"   # Elektrik Mor Vurgu
ACCENT_CYAN  = "#06B6D4"   # Siber Mavi Vurgu
PANEL_COLOR  = "#0F111A"   # Panel Yüzeyi
CARD_COLOR   = "#141724"   # Kart Yüzeyi
CARD_HOVER   = "#1A1E2E"
BORDER_COLOR = "#23273B"   # İnce Koyu Kenarlık
SUCCESS      = "#10B981"   # Zümrüt Yeşili
DANGER       = "#EF4444"   # Canlı Kırmızı
WARNING      = "#F59E0B"   # Amber Sarı / Turuncu
INFO         = "#3B82F6"   # Safir Mavi

root = tk.Tk()
root.title(f"⚡ SyncMT2 Otomasyon Engine v{APP_VERSION}")

# Dinamik Ekran Boyutu & Responsive Yerleşim (Düşük çözünürlüklü ekranlar ve Windows DPI taşmasını önler)
try:
    screen_w = root.winfo_screenwidth()
    screen_h = root.winfo_screenheight()
    avail_h = screen_h - 100
    target_h = 680 if avail_h >= 680 else max(460, avail_h)
    target_w = 620 if screen_w >= 660 else max(480, screen_w - 40)
    pos_x = max(10, (screen_w - target_w) // 2)
    pos_y = max(10, (screen_h - target_h - 50) // 2)
    root.geometry(f"{target_w}x{target_h}+{pos_x}+{pos_y}")
except Exception:
    root.geometry("600x640")

root.configure(bg=BG_COLOR)
root.attributes('-topmost', True)
root.resizable(True, True) # Kullanıcı pencereyi dilediği gibi boyutlandırabilir
root.minsize(460, 380)

root.bind('<F11>', toggle_running)

try:
    keyboard.add_hotkey('f11', hotkey_toggle)
except Exception as e:
    print("Global kısayol ayarlanamadı:", e)

def add_waypoint():
    class POINT(ctypes.Structure):
        _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]
    pt = POINT()
    ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
    route_waypoints.append({"x": pt.x, "y": pt.y})
    print(f"[BİLGİ] Rota eklendi: X={pt.x}, Y={pt.y}")
    try:
        root.after(0, update_waypoint_ui)
    except:
        pass

def clear_waypoints():
    route_waypoints.clear()
    print("[BİLGİ] Rota temizlendi.")
    try:
        root.after(0, update_waypoint_ui)
    except:
        pass

def update_waypoint_ui():
    wp_label.config(text=f"📍 Kayıtlı Rota Noktası: {len(route_waypoints)}")

try:
    keyboard.add_hotkey('f7', add_waypoint)
    keyboard.add_hotkey('f8', clear_waypoints)
except:
    pass

# ---- AYARLAR ----
def apply_settings():
    global cfg_metin_enable, cfg_fish_enable
    global cfg_space, cfg_quote, cfg_hp, cfg_mp, cfg_target, cfg_item, cfg_revive, cfg_patrol, cfg_clearing, cfg_ch_change, cfg_pot_alarm, cfg_horse_mode, cfg_player_name, cfg_pm_stop, cfg_captcha_enable, cfg_captcha_alarm
    global cfg_metin_default, cfg_metin_hirs, cfg_metin_savas, cfg_metin_dovus, cfg_metin_siyah, cfg_metin_uzuntu, cfg_metin_ruh
    global cfg_hp_key, cfg_mp_key, cfg_use_coords, cfg_min_x, cfg_max_x, cfg_min_y, cfg_max_y
    global cfg_fish_bait_key, cfg_fish_rod_key, cfg_fish_delay, cfg_fish_delay_min, cfg_fish_delay_max, cfg_auto_bait, cfg_auto_open_fish, cfg_fish_armor_anim, cfg_multi_bait, cfg_multi_bait_slot, cfg_multi_bait_count
    global bot_state
    
    cfg_metin_enable = var_metin_enable.get()
    cfg_fish_enable  = var_fish_enable.get()
    cfg_fish_armor_anim = var_fish_armor_anim.get()
    cfg_multi_bait   = var_multi_bait.get()
    cfg_multi_bait_keys = var_multi_bait_keys.get().strip() if 'var_multi_bait_keys' in globals() else "alt+1, alt+2, alt+3, alt+4"
    
    if cfg_fish_enable:
        cfg_metin_enable = False
    elif cfg_metin_enable:
        cfg_fish_enable = False
    
    cfg_space   = var_space.get()
    cfg_quote   = var_quote.get()
    cfg_hp      = var_hp.get()
    cfg_mp      = var_mp.get()
    cfg_target  = var_target.get()
    cfg_item    = var_item.get()
    cfg_revive  = var_revive.get()
    cfg_patrol  = var_patrol.get()
    cfg_clearing = var_clearing.get()
    cfg_use_coords = var_use_coords.get()
    cfg_ch_change  = var_ch_change.get()
    cfg_pot_alarm  = var_pot_alarm.get()
    cfg_horse_mode = var_horse_mode.get()
    cfg_pm_stop    = var_pm_stop.get()
    cfg_captcha_enable = var_captcha_enable.get()
    cfg_captcha_alarm  = var_captcha_alarm.get()
    cfg_pm_reply_1 = var_pm_reply_1.get().strip() or "as"
    cfg_pm_reply_2 = var_pm_reply_2.get().strip() or "abi ben kardesiyim tam bilmiyorum oyunu ben."
    cfg_pm_reply_3 = var_pm_reply_3.get().strip() or "dedigim gibi kardesiyim ben abim aktif olunca yazarsaniz sevinirim iyi oyunlar."
    cfg_player_name = var_player_name.get().strip() or "Ali"
    
    try:
        cfg_min_x = int(var_min_x.get().strip())
        cfg_max_x = int(var_max_x.get().strip())
        cfg_min_y = int(var_min_y.get().strip())
        cfg_max_y = int(var_max_y.get().strip())
    except:
        pass
    
    cfg_metin_default = var_metin_default.get()
    cfg_metin_hirs    = var_metin_hirs.get()
    cfg_metin_savas   = var_metin_savas.get()
    cfg_metin_dovus   = var_metin_dovus.get()
    cfg_metin_siyah   = var_metin_siyah.get()
    cfg_metin_uzuntu  = var_metin_uzuntu.get()
    cfg_metin_ruh     = var_metin_ruh.get()
    
    cfg_hp_key = var_hp_key.get().strip() or 'f3'
    cfg_mp_key = var_mp_key.get().strip() or 'f2'
    
    cfg_fish_bait_key  = var_fish_bait_key.get().strip() or '2'
    cfg_fish_rod_key   = var_fish_rod_key.get().strip() or '3'
    cfg_fish_delay_min = var_fish_delay_min.get().strip() or '0.5'
    cfg_fish_delay_max = var_fish_delay_max.get().strip() or '1.5'
    cfg_fish_delay     = f"{cfg_fish_delay_min} - {cfg_fish_delay_max}"
    cfg_auto_bait      = var_auto_bait.get()
    cfg_auto_open_fish = var_auto_open_fish.get()

    if cfg_fish_enable:
        bot_state = "IDLE"

var_metin_enable = tk.BooleanVar(value=True)
var_fish_enable  = tk.BooleanVar(value=False)

def on_metin_toggle(*args):
    if var_metin_enable.get():
        var_fish_enable.set(False)
        reset_skills()
    apply_settings()

def on_fish_toggle(*args):
    if var_fish_enable.get():
        var_metin_enable.set(False)
    apply_settings()

var_metin_enable.trace_add("write", on_metin_toggle)
var_fish_enable.trace_add("write", on_fish_toggle)

var_space   = tk.BooleanVar(value=True)
var_quote   = tk.BooleanVar(value=True)
var_target  = tk.BooleanVar(value=True)
var_hp      = tk.BooleanVar(value=True)
var_mp      = tk.BooleanVar(value=True)
var_item    = tk.BooleanVar(value=True)
var_revive  = tk.BooleanVar(value=True)
var_patrol   = tk.BooleanVar(value=False)
var_clearing = tk.BooleanVar(value=True)
var_use_coords = tk.BooleanVar(value=False)
var_ch_change  = tk.BooleanVar(value=False)
var_pot_alarm  = tk.BooleanVar(value=True)
var_horse_mode = tk.BooleanVar(value=False)
var_pm_stop       = tk.BooleanVar(value=True)
var_captcha_enable = tk.BooleanVar(value=True)
var_captcha_alarm  = tk.BooleanVar(value=True)
var_pm_reply_1 = tk.StringVar(value="as")
var_pm_reply_2 = tk.StringVar(value="abi ben kardesiyim tam bilmiyorum oyunu ben.")
var_pm_reply_3 = tk.StringVar(value="dedigim gibi kardesiyim ben abim aktif olunca yazarsaniz sevinirim iyi oyunlar.")
var_player_name = tk.StringVar(value="Ali")
var_min_x    = tk.StringVar(value="750")
var_max_x    = tk.StringVar(value="900")
var_min_y    = tk.StringVar(value="750")
var_max_y    = tk.StringVar(value="900")
var_hp_key   = tk.StringVar(value="f3")
var_mp_key  = tk.StringVar(value="f2")

var_metin_default = tk.BooleanVar(value=True)
var_metin_hirs    = tk.BooleanVar(value=False)
var_metin_savas   = tk.BooleanVar(value=False)
var_metin_dovus   = tk.BooleanVar(value=False)
var_metin_siyah   = tk.BooleanVar(value=False)
var_metin_uzuntu  = tk.BooleanVar(value=False)
var_metin_ruh     = tk.BooleanVar(value=True)

# Balık Botu Değişkenleri
var_fish_bait_key  = tk.StringVar(value="2")
var_fish_rod_key   = tk.StringVar(value="3")
var_fish_delay_min = tk.StringVar(value="0.5")
var_fish_delay_max = tk.StringVar(value="1.5")
var_fish_delay     = tk.StringVar(value="0.5 - 1.5")
var_auto_bait      = tk.BooleanVar(value=True)
var_auto_open_fish = tk.BooleanVar(value=False)
var_fish_armor_anim = tk.BooleanVar(value=False)
var_multi_bait     = tk.BooleanVar(value=False)
var_multi_bait_keys = tk.StringVar(value="alt+1, alt+2, alt+3, alt+4")

def get_multi_bait_key_list():
    raw = var_multi_bait_keys.get() if 'var_multi_bait_keys' in globals() else cfg_multi_bait_keys
    keys = [k.strip().lower() for k in raw.split(',') if k.strip()]
    return keys if keys else ["alt+1", "alt+2", "alt+3", "alt+4"]

def update_multi_bait_ui():
    try:
        if 'lbl_multi_bait_status' in globals() and lbl_multi_bait_status:
            keys = get_multi_bait_key_list()
            total_slots = len(keys)
            idx = max(0, min(cfg_multi_bait_slot - 1, total_slots - 1))
            curr_key = keys[idx] if keys else "alt+1"
            rem = max(0, 200 - cfg_multi_bait_count)
            lbl_multi_bait_status.config(
                text=f"Aktif Tuş: [{curr_key.upper()}] (Slot {idx + 1}/{total_slots})  |  Kullanılan: {cfg_multi_bait_count}/200  (Kalan: {rem})"
            )
    except Exception:
        pass

def reset_multi_bait_counter():
    global cfg_multi_bait_slot, cfg_multi_bait_count
    cfg_multi_bait_slot = 1
    cfg_multi_bait_count = 0
    save_config()
    update_multi_bait_ui()
    keys = get_multi_bait_key_list()
    first_k = keys[0] if keys else "alt+1"
    print(f"[BALIK BOTU] 🔄 Yem sayacı sıfırlandı! İlk yem tuşuna dönüldü: [{first_k.upper()}] (Slot 1/{len(keys)} - 200/200).")

def get_random_fish_delay():
    """Balık çekme gecikmesini Min-Max aralığında rastgele hesaplar."""
    try:
        raw_min = var_fish_delay_min.get().strip() if 'var_fish_delay_min' in globals() else str(cfg_fish_delay_min).strip()
        raw_max = var_fish_delay_max.get().strip() if 'var_fish_delay_max' in globals() else str(cfg_fish_delay_max).strip()
        
        d_min = float(raw_min.replace(",", "."))
        d_max = float(raw_max.replace(",", "."))
        if d_min > d_max:
            d_min, d_max = d_max, d_min
        chosen = random.uniform(d_min, d_max)
        return chosen
    except Exception:
        return 1.2

# ==========================================
# SABİT BUTON ÇUBUĞU (ALT BAR - HER ZAMAN GÖRÜNÜR)
# ==========================================
bottom_bar = tk.Frame(root, bg="#08090D", pady=10, highlightthickness=1, highlightbackground=BORDER_COLOR)
bottom_bar.pack(side=tk.BOTTOM, fill=tk.X, padx=0)

bottom_inner = tk.Frame(bottom_bar, bg="#08090D")
bottom_inner.pack(fill=tk.X, padx=16)

btn_start = tk.Button(bottom_inner, text="▶  BOTU BAŞLAT (F11)",
                      bg=SUCCESS, fg="#06281E", activebackground="#0D9488", activeforeground="#FFFFFF",
                      font=("Segoe UI", 10, "bold"), bd=0, relief=tk.FLAT,
                      cursor="hand2", command=start_bot)
btn_start.pack(side=tk.LEFT, padx=(0, 6), ipady=8, expand=True, fill=tk.X)

btn_stop = tk.Button(bottom_inner, text="■  BOTU DURDUR",
                     bg=CARD_COLOR, fg="#4B5563", activebackground=DANGER, activeforeground="#FFFFFF",
                     font=("Segoe UI", 10, "bold"), bd=0, relief=tk.FLAT,
                     state=tk.DISABLED, cursor="hand2", command=stop_bot)
btn_stop.pack(side=tk.RIGHT, padx=(6, 0), ipady=8, expand=True, fill=tk.X)

# ==========================================
# KAYDIRMA ALANI (SCROLL CANVAS)
# ==========================================
canvas = tk.Canvas(root, bg=BG_COLOR, bd=0, highlightthickness=0)
scrollbar = tk.Scrollbar(root, orient="vertical", command=canvas.yview)
scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
canvas.configure(yscrollcommand=scrollbar.set)

scroll_frame = tk.Frame(canvas, bg=BG_COLOR)
scroll_win = canvas.create_window((0, 0), window=scroll_frame, anchor="nw")

def _on_frame_configure(event):
    canvas.configure(scrollregion=canvas.bbox("all"))
    canvas.itemconfig(scroll_win, width=canvas.winfo_width())

scroll_frame.bind("<Configure>", _on_frame_configure)
canvas.bind("<Configure>", lambda e: canvas.itemconfig(scroll_win, width=e.width))

def _on_mousewheel(event):
    canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
canvas.bind_all("<MouseWheel>", _on_mousewheel)

root_inner = scroll_frame

def make_card(parent=None, pady=(5, 5), padx=16):
    if parent is None:
        parent = root_inner
    f = tk.Frame(parent, bg=CARD_COLOR, bd=0, highlightthickness=1, highlightbackground=BORDER_COLOR)
    f.pack(fill=tk.X, padx=padx, pady=pady)
    return f

# ==========================================
# MODERN BİLGİ KUTUSU (TOOLTIP & MODAL) SİSTEMİ
# ==========================================
INFO_DESCRIPTIONS = {
    "Metin Botu Aktif": "Metin kesme otomasyonunu başlatır. Ekranda Metin taşlarını görüntü işleme ile tespit eder, hedefe koşar ve metni keser.",
    "Oto Vuruş (Boşluk)": "Metin keserken veya yaratıklarla savaşırken otomatik Boşluk (Space) tuşuna basarak karakterin kesintisiz saldırmasını sağlar.",
    "Oto Toplama (é)": "Yere düşen Yang, item ve cevherleri otomatik toplamak için kesintisiz olarak é tuşuna basar.",
    "Oto Metin Takibi": "Ekrandaki Metin taşlarının konumunu tespit edip fareyle üzerlerine tıklayarak karakteri hedefe kilitler.",
    "Oto Dirilme": "Karakter öldüğünde 'Burada Yeniden Başla' butonunu algılar, şehirde/burada otomatik canlanır ve pot basıp savaşa devam eder.",
    "Eşyaya Tıkla": "Ekranda yere düşen değerli eşya veya kutu şablonlarını tespit edip doğrudan fareyle tıklar.",
    "Devriye Modu": "Belirlenen F7 rota noktaları arasında devriye gezerek geniş harita alanında Metin aramanızı sağlar.",
    "Metin Etraf Turu": "Metin kesilirken 60 saniyede bir Metin'in etrafında 8 farklı yöne kısa turlar atarak yaratıkların engellerini temizler.",
    "Bölge Sınırı Kullan": "Karakterin belirtilen Min/Max X-Y harita koordinatlarının dışına çıkmasını ve haritada kaybolmasını engeller.",
    "CH Değiştir": "Metin kesildikten 10sn sonra veya ekranda 12sn metin bulunamadığında sıradaki kanala geçer (CH1->CH2->CH3->CH4).",
    "Pot Bitti Uyarısı": "Can veya Mana potu bittiğinde ve 4 saniye boyunca can dolmadığında sesli bip uyarısı vererek sizi uyarır.",
    "Atta Savaş (Ctrl+G)": "Savaşı at üzerinde sürdürür. Skil süresi dolduğunda Ctrl+G ile attan inip skili açar ve tekrar ata biner.",
    "PM Gelince Dur": "Biri size PM (fısıltı) gönderdiğinde ekranda beliren mektup ikonunu algılar, botu otomatik durdurur, sesli uyarı verir ve fısıltı penceresini açmak için mektuba tıklar.",
    "Bot Verify Sesli Uyarı": "Ekranda Bot Verify doğrulama penceresi algılandığında bot modüllerini derhal durdurur ve dikkat çekici yüksek sesli siren çalarak sizi uyarır.",
    "Balık Botu Aktif": "Balık tutma otomasyonunu başlatır. Baloncuk veya sohbet yazısını algılayıp oltayı otomatik çeker.",
    "Otomatik Yem Tak": "Her olta atışından önce yem tuşuna (2) basarak oltaya yeni yem takar.",
    "Balıkları Aç": "Envantere gelen balıklara sağ tıklayarak balıkları otomatik açar.",
    "MODÜLLER & OTOMASYON ÖZELLİKLERİ": "Metin botunun aktif çalıştırılacak modüllerini ve otomasyon fonksiyonlarını buradan açıp kapatabilirsiniz.",
    "HARİTA BÖLGE KOORDİNAT SINIRI": "Karakterin haritanın belirlenen sınırı dışına çıkmasını önlemek için koordinat alanlarını kısıtlar.",
    "CAN & MANA POT AYARLARI": "Karakterin canı veya manası düştüğünde ekrandaki piksel rengine göre otomatik F3/F2 pot basmasını sağlar. F6 ile piksel ayarlanır.",
    "HEDEF METİN SEÇİMİ": "Aranacak metin şablonlarını seçmenizi sağlar. Seçilen şablonlar ekranda otomatik tespit edilir.",
    "YETENEK & SKİL YÖNETİCİSİ": "Hava Kılıcı, Öfke vb. skillerin belirlediğiniz süre aralıklarında (cooldown) otomatik olarak açılmasını sağlar.",
    "BALIK BOTU OTOMASYONU": "Balık tutma otomasyonunun ana kontrol modüllerini içerir.",
    "BALIK TUTMA TUŞ & ZAMANLAMA AYARLARI": "Olta çekme süresini Min ve Max saniyeleri arasında rastgele belirleyerek anti-bot tespitini engeller."
}

def show_info_popup(title, text):
    popup = tk.Toplevel(root)
    popup.title(f"Bilgi: {title}")
    popup.geometry("400x260")
    popup.configure(bg="#0B0C14")
    popup.attributes('-topmost', True)
    popup.resizable(False, False)
    popup.transient(root)
    popup.grab_set()

    root_x = root.winfo_x()
    root_y = root.winfo_y()
    root_w = root.winfo_width()
    root_h = root.winfo_height()
    pos_x = root_x + (root_w // 2) - 200
    pos_y = root_y + (root_h // 2) - 130
    popup.geometry(f"400x260+{pos_x}+{pos_y}")

    h_frame = tk.Frame(popup, bg="#141724", highlightthickness=1, highlightbackground=BORDER_COLOR)
    h_frame.pack(fill=tk.X, padx=12, pady=(12, 6))

    tk.Label(h_frame, text=f"💡  {title}", font=("Segoe UI", 11, "bold"), bg="#141724", fg=FG_COLOR, anchor="w").pack(side=tk.LEFT, padx=10, pady=8)

    body_frame = tk.Frame(popup, bg="#141724", highlightthickness=1, highlightbackground=BORDER_COLOR)
    body_frame.pack(fill=tk.BOTH, expand=True, padx=12, pady=4)

    msg = tk.Message(body_frame, text=text, font=("Segoe UI", 9), bg="#141724", fg="#D1D5DB", width=360, justify="left")
    msg.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

    btn_close = tk.Button(popup, text="ANLADIM", command=popup.destroy,
                          bg=ACCENT, fg="#FFFFFF", activebackground="#7C3AED", activeforeground="#FFFFFF",
                          font=("Segoe UI", 9, "bold"), bd=0, relief=tk.FLAT, cursor="hand2", pady=6)
    btn_close.pack(fill=tk.X, padx=12, pady=(4, 12))

def section_label(parent=None, text=""):
    if parent is None:
        parent = root_inner
    f = tk.Frame(parent, bg=BG_COLOR)
    f.pack(fill=tk.X, padx=18, pady=(12, 3))
    
    tk.Frame(f, bg=ACCENT, width=3, height=12).pack(side=tk.LEFT, padx=(0, 6))
    tk.Label(f, text=text, font=("Segoe UI", 9, "bold"),
             bg=BG_COLOR, fg="#9CA3AF").pack(side=tk.LEFT)

    clean_text = text.replace(" (ALAN KISITLAMA)", "").replace(" (ŞABLON LİSTESİ)", "").strip()
    if clean_text in INFO_DESCRIPTIONS or text in INFO_DESCRIPTIONS:
        info_t = text if text in INFO_DESCRIPTIONS else clean_text
        info_d = INFO_DESCRIPTIONS[info_t]
        info_btn = tk.Button(
            f, text="?", command=lambda t=info_t, d=info_d: show_info_popup(t, d),
            bg="#1E1B4B", fg=ACCENT_CYAN, activebackground=ACCENT, activeforeground="#FFFFFF",
            font=("Segoe UI", 8, "bold"), bd=0, relief=tk.FLAT, cursor="hand2",
            width=2, pady=1, highlightthickness=1, highlightbackground=BORDER_COLOR
        )
        info_btn.pack(side=tk.LEFT, padx=(6, 0))

# ==========================================
# BAŞLIK & LOGO BANNER
# ==========================================
header = tk.Frame(root_inner, bg=BG_COLOR)
header.pack(fill=tk.X, padx=16, pady=(14, 6))

title_frame = tk.Frame(header, bg=BG_COLOR)
title_frame.pack(side=tk.LEFT)

tk.Label(title_frame, text="⚡ SyncMT2",
         font=("Segoe UI Black", 18), bg=BG_COLOR, fg=FG_COLOR).pack(anchor="w")
tk.Label(title_frame, text="Metin2 Otomasyon Sistemi",
         font=("Segoe UI", 9), bg=BG_COLOR, fg="#6B7280").pack(anchor="w")

badge_frame = tk.Frame(header, bg="#1E1B4B", highlightthickness=1, highlightbackground=ACCENT)
badge_frame.pack(side=tk.RIGHT, pady=4)
tk.Label(badge_frame, text=f"v{APP_VERSION} PRO", font=("Segoe UI", 8, "bold"), bg="#1E1B4B", fg=ACCENT_CYAN, padx=8, pady=3).pack()

# İnce modern ayırıcı çizgi
sep = tk.Frame(root_inner, bg=BORDER_COLOR, height=1)
sep.pack(fill=tk.X, padx=16, pady=(2, 6))

# ==========================================
# CANLI DURUM PANELI
# ==========================================
status_card = make_card(root_inner, pady=(2, 6))
status_inner = tk.Frame(status_card, bg=CARD_COLOR)
status_inner.pack(fill=tk.X, padx=14, pady=10)

status_dot   = tk.Label(status_inner, text="●", font=("Segoe UI", 13), bg=CARD_COLOR, fg=DANGER)
status_dot.pack(side=tk.LEFT, padx=(0, 6))
status_label = tk.Label(status_inner, text="DURUM: BEKLİYOR",
                        font=("Segoe UI", 10, "bold"), bg=CARD_COLOR, fg=DANGER)
status_label.pack(side=tk.LEFT)

hint_badge = tk.Frame(status_inner, bg="#111827", highlightthickness=1, highlightbackground=BORDER_COLOR)
hint_badge.pack(side=tk.RIGHT)
tk.Label(hint_badge, text="Kısayol: [F11]", font=("Segoe UI", 8, "bold"), bg="#111827", fg="#9CA3AF", padx=8, pady=2).pack()

toggle_update_funcs = []

def refresh_all_visuals():
    for fn in toggle_update_funcs:
        try:
            fn()
        except:
            pass

# ==========================================
# TOGGLE BUTON FACTORY (2 SÜTUNLU MODERN DÜZEN)
# ==========================================
def create_toggle_button(parent, text_base, variable, row, col, padx=(6, 6)):
    cell = tk.Frame(parent, bg=CARD_COLOR)
    cell.grid(row=row, column=col, sticky="ew", padx=padx, pady=4)
    cell.columnconfigure(0, weight=1)

    def toggle():
        variable.set(not variable.get())
        apply_settings()
        update_visuals()

    def update_visuals():
        if variable.get():
            btn.config(bg="#0B261D", fg=SUCCESS, relief=tk.FLAT,
                       highlightbackground=SUCCESS, highlightthickness=1,
                       text=f"  ✔  {text_base}")
        else:
            btn.config(bg="#11131F", fg="#6B7280", relief=tk.FLAT,
                       highlightbackground=BORDER_COLOR, highlightthickness=1,
                       text=f"  ✖  {text_base}")

    btn = tk.Button(
        cell, text=f"  ✖  {text_base}", command=toggle,
        bg="#11131F", fg="#6B7280",
        activebackground="#0B261D", activeforeground=SUCCESS,
        font=("Segoe UI", 9), cursor="hand2", bd=0,
        anchor="w", pady=6,
        highlightthickness=1, highlightbackground=BORDER_COLOR
    )
    btn.pack(side=tk.LEFT, fill=tk.X, expand=True)

    if text_base in INFO_DESCRIPTIONS:
        info_d = INFO_DESCRIPTIONS[text_base]
        info_btn = tk.Button(
            cell, text="?", command=lambda t=text_base, d=info_d: show_info_popup(t, d),
            bg="#1E1B4B", fg=ACCENT_CYAN, activebackground=ACCENT, activeforeground="#FFFFFF",
            font=("Segoe UI", 9, "bold"), bd=0, relief=tk.FLAT, cursor="hand2",
            width=2, pady=5, highlightthickness=1, highlightbackground=BORDER_COLOR
        )
        info_btn.pack(side=tk.RIGHT, padx=(4, 0))

    toggle_update_funcs.append(update_visuals)
    update_visuals()
    return btn

# ==========================================
# SEKMELER (MODERN SEGMENTED CONTROL)
# ==========================================
tab_card = make_card(root_inner, pady=(6, 4))
tab_bar = tk.Frame(tab_card, bg=CARD_COLOR)
tab_bar.pack(fill=tk.X, padx=6, pady=6)

def switch_tab(tab_name):
    if tab_name == "metin":
        btn_tab_metin.config(bg=ACCENT, fg="#FFFFFF", font=("Segoe UI", 9, "bold"))
        btn_tab_fish.config(bg="#11131F", fg="#9CA3AF", font=("Segoe UI", 9))
        metin_tab_container.pack(fill=tk.X, expand=True)
        fish_tab_container.pack_forget()
        var_metin_enable.set(True)
        var_fish_enable.set(False)
    else:
        btn_tab_fish.config(bg=ACCENT_CYAN, fg="#000000", font=("Segoe UI", 9, "bold"))
        btn_tab_metin.config(bg="#11131F", fg="#9CA3AF", font=("Segoe UI", 9))
        fish_tab_container.pack(fill=tk.X, expand=True)
        metin_tab_container.pack_forget()
        var_fish_enable.set(True)
        var_metin_enable.set(False)
    apply_settings()

btn_tab_metin = tk.Button(tab_bar, text="⚔️  METİN BOTU & SAVAŞ", command=lambda: switch_tab("metin"),
                          bg=ACCENT, fg="#FFFFFF", font=("Segoe UI", 9, "bold"), bd=0, relief=tk.FLAT, cursor="hand2", pady=7)
btn_tab_metin.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(0, 3))

btn_tab_fish = tk.Button(tab_bar, text="🎣  BALIK BOTU", command=lambda: switch_tab("fish"),
                         bg="#11131F", fg="#9CA3AF", font=("Segoe UI", 9), bd=0, relief=tk.FLAT, cursor="hand2", pady=7)
btn_tab_fish.pack(side=tk.RIGHT, expand=True, fill=tk.X, padx=(3, 0))

# Sekme Konteynerleri
metin_tab_container = tk.Frame(root_inner, bg=BG_COLOR)
metin_tab_container.pack(fill=tk.X, expand=True)

fish_tab_container = tk.Frame(root_inner, bg=BG_COLOR)

# ==========================================
# MODÜLLER PANELİ (METİN SEKMESİ İÇİNDE)
# ==========================================
section_label(metin_tab_container, "MODÜLLER & OTOMASYON ÖZELLİKLERİ")
opts_card = make_card(metin_tab_container)
opts_frame = tk.Frame(opts_card, bg=CARD_COLOR)
opts_frame.pack(fill=tk.X, padx=10, pady=10)
opts_frame.columnconfigure(0, weight=1)
opts_frame.columnconfigure(1, weight=1)

create_toggle_button(opts_frame, "Metin Botu Aktif",   var_metin_enable, 0, 0)
create_toggle_button(opts_frame, "Oto Vuruş (Boşluk)", var_space,        0, 1)
create_toggle_button(opts_frame, "Oto Toplama (é)",    var_quote,        1, 0)
create_toggle_button(opts_frame, "Oto Metin Takibi",   var_target,       1, 1)
create_toggle_button(opts_frame, "Oto Dirilme",        var_revive,       2, 0)
create_toggle_button(opts_frame, "Eşyaya Tıkla",       var_item,         2, 1)
create_toggle_button(opts_frame, "Devriye Modu",       var_patrol,       3, 0)
create_toggle_button(opts_frame, "Metin Etraf Turu",   var_clearing,     3, 1)
create_toggle_button(opts_frame, "Bölge Sınırı Kullan",var_use_coords,   4, 0)
create_toggle_button(opts_frame, "CH Değiştir",        var_ch_change,    4, 1)
create_toggle_button(opts_frame, "Pot Bitti Uyarısı",  var_pot_alarm,    5, 0)
create_toggle_button(opts_frame, "Atta Savaş (Ctrl+G)", var_horse_mode,  5, 1)

# Karakter / İtem Sahibi İsmi Alanı
pname_frame = tk.Frame(opts_frame, bg="#0B0C14", highlightthickness=1, highlightbackground=BORDER_COLOR)
pname_frame.grid(row=6, column=0, columnspan=2, sticky="ew", padx=6, pady=(6, 2))

tk.Label(pname_frame, text="👤 İtem Sahibi İsmi:", font=("Segoe UI", 8, "bold"), bg="#0B0C14", fg="#9CA3AF").pack(side=tk.LEFT, padx=(8, 4), pady=4)
entry_pname = tk.Entry(pname_frame, textvariable=var_player_name, width=12, bg="#141724", fg=FG_COLOR, insertbackground=FG_COLOR,
                       font=("Segoe UI", 9, "bold"), relief=tk.FLAT, justify="center", highlightthickness=1, highlightbackground=BORDER_COLOR)
entry_pname.pack(side=tk.LEFT, padx=4, pady=4)
entry_pname.bind("<FocusOut>", lambda ev: apply_settings())

tk.Label(pname_frame, text="(Örn: Ali → Oyunda 'Ali's' olarak taranır)", font=("Segoe UI", 8), bg="#0B0C14", fg="#6B7280").pack(side=tk.LEFT, padx=(6, 0))

# Rota noktaları bilgi çubuğu
wp_frame = tk.Frame(opts_frame, bg="#0B0C14", highlightthickness=1, highlightbackground=BORDER_COLOR)
wp_frame.grid(row=7, column=0, columnspan=2, sticky="ew", padx=6, pady=(4, 2))

wp_label = tk.Label(wp_frame, text="📍 Kayıtlı Rota Noktası: 0",
                    font=("Segoe UI", 8, "bold"), bg="#0B0C14", fg=INFO)
wp_label.pack(side=tk.LEFT, padx=10, pady=5)

tk.Label(wp_frame, text="Nokta Ekle: [F7]  |  Rotayı Temizle: [F8]",
         font=("Segoe UI", 8), bg="#0B0C14", fg="#6B7280").pack(side=tk.RIGHT, padx=10, pady=5)

# ==========================================
# PM (FISILTI) OTOMATİK CEVAP VE KORUMA PANELİ (GENEL AYAR)
# ==========================================
section_label(root_inner, "📩 PM (FISILTI) OTOMATİK CEVAP & KORUMA")
pm_card = make_card(root_inner)
pm_frame = tk.Frame(pm_card, bg=CARD_COLOR)
pm_frame.pack(fill=tk.X, padx=10, pady=10)

pm_top = tk.Frame(pm_frame, bg=CARD_COLOR)
pm_top.pack(fill=tk.X, padx=4, pady=(2, 6))
pm_top.columnconfigure(0, weight=1)
pm_top.columnconfigure(1, weight=1)
create_toggle_button(pm_top, "📩 PM Koruma & Oto Cevap", var_pm_stop, 0, 0)
create_toggle_button(pm_top, "🔔 Bot Verify Sesli Uyarı", var_captcha_alarm, 0, 1)

# 1. Yanıt
r1_f = tk.Frame(pm_frame, bg="#0B0C14", highlightthickness=1, highlightbackground=BORDER_COLOR)
r1_f.pack(fill=tk.X, padx=4, pady=3)
tk.Label(r1_f, text="1. Mesaj (İlk Yazana):", font=("Segoe UI", 8, "bold"), bg="#0B0C14", fg=ACCENT_CYAN, width=20, anchor="w").pack(side=tk.LEFT, padx=8, pady=4)
e_r1 = tk.Entry(r1_f, textvariable=var_pm_reply_1, bg="#141724", fg=FG_COLOR, insertbackground=FG_COLOR, font=("Segoe UI", 9), relief=tk.FLAT)
e_r1.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=6, pady=4)
e_r1.bind("<FocusOut>", lambda ev: apply_settings())

# 2. Yanıt
r2_f = tk.Frame(pm_frame, bg="#0B0C14", highlightthickness=1, highlightbackground=BORDER_COLOR)
r2_f.pack(fill=tk.X, padx=4, pady=3)
tk.Label(r2_f, text="2. Mesaj (2. Kez Yazana):", font=("Segoe UI", 8, "bold"), bg="#0B0C14", fg=WARNING, width=20, anchor="w").pack(side=tk.LEFT, padx=8, pady=4)
e_r2 = tk.Entry(r2_f, textvariable=var_pm_reply_2, bg="#141724", fg=FG_COLOR, insertbackground=FG_COLOR, font=("Segoe UI", 9), relief=tk.FLAT)
e_r2.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=6, pady=4)
e_r2.bind("<FocusOut>", lambda ev: apply_settings())

# 3. Yanıt
r3_f = tk.Frame(pm_frame, bg="#0B0C14", highlightthickness=1, highlightbackground=BORDER_COLOR)
r3_f.pack(fill=tk.X, padx=4, pady=3)
tk.Label(r3_f, text="3. Mesaj (3+. Kez Yazana):", font=("Segoe UI", 8, "bold"), bg="#0B0C14", fg=DANGER, width=20, anchor="w").pack(side=tk.LEFT, padx=8, pady=4)
e_r3 = tk.Entry(r3_f, textvariable=var_pm_reply_3, bg="#141724", fg=FG_COLOR, insertbackground=FG_COLOR, font=("Segoe UI", 9), relief=tk.FLAT)
e_r3.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=6, pady=4)
e_r3.bind("<FocusOut>", lambda ev: apply_settings())

# ==========================================
# HARİTA BÖLGE KOORDİNAT SINIRI PANELİ
# ==========================================
section_label(metin_tab_container, "HARİTA BÖLGE KOORDİNAT SINIRI (ALAN KISITLAMA)")
coord_card = make_card(metin_tab_container)
coord_frame = tk.Frame(coord_card, bg=CARD_COLOR)
coord_frame.pack(fill=tk.X, padx=10, pady=10)

c_inputs = tk.Frame(coord_frame, bg=CARD_COLOR)
c_inputs.pack(fill=tk.X, padx=4, pady=2)
for i in range(4): c_inputs.columnconfigure(i, weight=1)

for idx, (lbl, var) in enumerate([("Min X:", var_min_x), ("Max X:", var_max_x), ("Min Y:", var_min_y), ("Max Y:", var_max_y)]):
    f = tk.Frame(c_inputs, bg="#0B0C14", highlightthickness=1, highlightbackground=BORDER_COLOR, padx=8, pady=4)
    f.grid(row=idx//2, column=idx%2, padx=6, pady=4, sticky="ew")
    tk.Label(f, text=lbl, font=("Segoe UI", 8, "bold"), bg="#0B0C14", fg="#9CA3AF").pack(side=tk.LEFT)
    e = tk.Entry(f, textvariable=var, width=7, bg="#141724", fg=FG_COLOR, insertbackground=FG_COLOR,
                 font=("Segoe UI", 9, "bold"), relief=tk.FLAT, justify="center")
    e.pack(side=tk.RIGHT, padx=(4, 0))
    e.bind("<FocusOut>", lambda ev: apply_settings())

# ==========================================
# POT AYARLARI PANELİ
# ==========================================
section_label(metin_tab_container, "CAN & MANA POT AYARLARI")
pot_card = make_card(metin_tab_container)
pot_frame = tk.Frame(pot_card, bg=CARD_COLOR)
pot_frame.pack(fill=tk.X, padx=10, pady=10)

def make_pot_row(parent, row, label_text, label_color, var_enable, var_key, calib_cmd, btn_color):
    create_toggle_button(parent, label_text, var_enable, row, 0, padx=(6, 4))

    key_frame = tk.Frame(parent, bg="#0B0C14", highlightthickness=1, highlightbackground=BORDER_COLOR, padx=8, pady=3)
    key_frame.grid(row=row, column=1, sticky="ew", padx=4, pady=4)
    tk.Label(key_frame, text="Tuş:", font=("Segoe UI", 8),
             bg="#0B0C14", fg="#6B7280").pack(side=tk.LEFT)
    entry = tk.Entry(key_frame, textvariable=var_key, width=5,
                     bg="#141724", fg=FG_COLOR, insertbackground=FG_COLOR,
                     font=("Segoe UI", 9, "bold"), relief=tk.FLAT, justify="center")
    entry.pack(side=tk.RIGHT, padx=(4, 0))
    entry.bind("<FocusOut>", lambda e: apply_settings())

    btn = tk.Button(parent, text="🎯 AYARLA", command=calib_cmd,
                    bg=btn_color, fg="#FFFFFF", activebackground="#FFFFFF", activeforeground="#000000",
                    font=("Segoe UI", 8, "bold"), bd=0, relief=tk.FLAT, cursor="hand2",
                    padx=10, pady=5)
    btn.grid(row=row, column=2, padx=(4, 6), pady=4)

def set_calibration_hp():
    global calibration_mode
    calibration_mode = "hp"
    print("[AYAR] Lütfen fareyi CAN barında pot basılmasını istediğiniz noktaya getirip F6'ya basın.")

def set_calibration_mp():
    global calibration_mode
    calibration_mode = "mp"
    print("[AYAR] Lütfen fareyi MANA barında pot basılmasını istediğiniz noktaya getirip F6'ya basın.")

pot_frame.columnconfigure(0, weight=2)
pot_frame.columnconfigure(1, weight=1)
pot_frame.columnconfigure(2, weight=1)

make_pot_row(pot_frame, 0, "Can Potu Otomasyonu", DANGER,  var_hp, var_hp_key, set_calibration_hp, DANGER)
make_pot_row(pot_frame, 1, "Mana Potu Otomasyonu", INFO, var_mp, var_mp_key, set_calibration_mp, INFO)

pot_info = tk.Frame(pot_frame, bg="#0B0C14", highlightthickness=1, highlightbackground=BORDER_COLOR)
pot_info.grid(row=2, column=0, columnspan=3, sticky="ew", padx=6, pady=(6, 2))
tk.Label(pot_info, text="💡 Piksel Kalibrasyonu: F6  |  Varsayılan Tuşlar: F3 (Can) / F2 (Mana)",
         font=("Segoe UI", 8), bg="#0B0C14", fg="#6B7280").pack(side=tk.LEFT, padx=10, pady=4)

# ==========================================
# HEDEF METİN PANELİ
# ==========================================
section_label(metin_tab_container, "HEDEF METİN SEÇİMİ (ŞABLON LİSTESİ)")
metin_card = make_card(metin_tab_container)
metin_frame = tk.Frame(metin_card, bg=CARD_COLOR)
metin_frame.pack(fill=tk.X, padx=10, pady=10)
metin_frame.columnconfigure(0, weight=1)
metin_frame.columnconfigure(1, weight=1)

create_toggle_button(metin_frame, "Genel (hedef.png)", var_metin_default, 0, 0)
create_toggle_button(metin_frame, "Hırs Metni",        var_metin_hirs,    0, 1)
create_toggle_button(metin_frame, "Savaş Metni",       var_metin_savas,   1, 0)
create_toggle_button(metin_frame, "Dövüş Metni",       var_metin_dovus,   1, 1)
create_toggle_button(metin_frame, "Siyah Metin",       var_metin_siyah,   2, 0)
create_toggle_button(metin_frame, "Üzüntü Metni",      var_metin_uzuntu,  2, 1)
create_toggle_button(metin_frame, "Ruh Metni",         var_metin_ruh,     3, 0)

# ==========================================
# YETENEK YÖNETİCİSİ PANELİ
# ==========================================
section_label(metin_tab_container, "YETENEK & SKİL YÖNETİCİSİ")
skills_card = make_card(metin_tab_container)
skills_frame = tk.Frame(skills_card, bg=CARD_COLOR)
skills_frame.pack(fill=tk.X, padx=10, pady=10)

header_row = tk.Frame(skills_frame, bg="#0B0C14", highlightthickness=1, highlightbackground=BORDER_COLOR)
header_row.pack(fill=tk.X, padx=4, pady=(0, 6))

tk.Label(header_row, text="DURUM", font=("Segoe UI", 8, "bold"), bg="#0B0C14", fg="#9CA3AF", width=10, anchor="center").pack(side=tk.LEFT, padx=4, pady=4)
tk.Label(header_row, text="TUŞ", font=("Segoe UI", 8, "bold"), bg="#0B0C14", fg="#9CA3AF", width=8, anchor="center").pack(side=tk.LEFT, padx=4, pady=4)
tk.Label(header_row, text="SÜRE (sn)", font=("Segoe UI", 8, "bold"), bg="#0B0C14", fg="#9CA3AF", width=12, anchor="center").pack(side=tk.LEFT, padx=4, pady=4)
tk.Label(header_row, text="YETENEK ADI", font=("Segoe UI", 8, "bold"), bg="#0B0C14", fg="#9CA3AF", anchor="w").pack(side=tk.LEFT, padx=8, pady=4)

def create_skill_toggle(parent, variable):
    def toggle():
        variable.set(not variable.get())
        update_v()
    def update_v():
        if variable.get():
            btn.config(text="✔ AKTİF", fg=SUCCESS, bg="#0B261D", highlightbackground=SUCCESS)
        else:
            btn.config(text="✖ PASİF", fg="#6B7280", bg="#11131F", highlightbackground=BORDER_COLOR)
    btn = tk.Button(parent, text="✖ PASİF", command=toggle,
                    font=("Segoe UI", 8, "bold"), width=9, bd=0, cursor="hand2", relief=tk.FLAT,
                    highlightthickness=1, highlightbackground=BORDER_COLOR,
                    bg="#11131F", fg="#6B7280", pady=3)
    btn.pack(side=tk.LEFT, padx=4)
    toggle_update_funcs.append(update_v)  # refresh_all_visuals() çağrıldığında güncelle
    update_v()
    return btn


for i in range(5):
    var_en   = tk.BooleanVar(value=False)
    var_key  = tk.StringVar(value="")
    var_cool = tk.StringVar(value="")
    
    skills_config.append({
        "enabled": var_en,
        "key": var_key,
        "cooldown": var_cool,
        "last_cast": 0
    })
    
    row_frame = tk.Frame(skills_frame, bg=CARD_COLOR)
    row_frame.pack(fill=tk.X, padx=4, pady=3)
    
    create_skill_toggle(row_frame, var_en)
    
    e_k = tk.Entry(row_frame, textvariable=var_key, width=6,
                   bg="#0B0C14", fg=FG_COLOR, insertbackground=FG_COLOR,
                   font=("Segoe UI", 9, "bold"), relief=tk.FLAT, justify="center",
                   highlightthickness=1, highlightbackground=BORDER_COLOR)
    e_k.pack(side=tk.LEFT, padx=4)
    
    e_c = tk.Entry(row_frame, textvariable=var_cool, width=9,
                   bg="#0B0C14", fg=FG_COLOR, insertbackground=FG_COLOR,
                   font=("Segoe UI", 9, "bold"), relief=tk.FLAT, justify="center",
                   highlightthickness=1, highlightbackground=BORDER_COLOR)
    e_c.pack(side=tk.LEFT, padx=4)
    
    tk.Label(row_frame, text=f"✨ {i+1}. Yetenek (Skil)",
             font=("Segoe UI", 9), bg=CARD_COLOR, fg="#9CA3AF").pack(side=tk.LEFT, padx=8)

# ==========================================
# BALIK BOTU SEKMESİ İÇERİĞİ (fish_tab_container)
# ==========================================
section_label(fish_tab_container, "BALIK BOTU OTOMASYONU")
fish_opts_card = make_card(fish_tab_container)
fish_opts_frame = tk.Frame(fish_opts_card, bg=CARD_COLOR)
fish_opts_frame.pack(fill=tk.X, padx=10, pady=10)
fish_opts_frame.columnconfigure(0, weight=1)
fish_opts_frame.columnconfigure(1, weight=1)

create_toggle_button(fish_opts_frame, "Balık Botu Aktif",        var_fish_enable,     0, 0)
create_toggle_button(fish_opts_frame, "Otomatik Yem Tak",       var_auto_bait,       0, 1)
create_toggle_button(fish_opts_frame, "Balıkları Aç",           var_auto_open_fish,  1, 0)
create_toggle_button(fish_opts_frame, "Zırh Giyme Animasyonu", var_fish_armor_anim, 1, 1)
create_toggle_button(fish_opts_frame, "🪱 Çoklu Yem (Özel Sıralı / 200'lük)", var_multi_bait, 2, 0)

section_label(fish_tab_container, "ÇOKLU YEM YÖNETİMİ (ÖZEL TUŞ SIRASI)")
multi_bait_card = make_card(fish_tab_container)
multi_bait_frame = tk.Frame(multi_bait_card, bg=CARD_COLOR)
multi_bait_frame.pack(fill=tk.X, padx=10, pady=10)

# 1. Tuş Sırası Giriş Satırı
keys_row = tk.Frame(multi_bait_frame, bg="#0B0C14", highlightthickness=1, highlightbackground=BORDER_COLOR)
keys_row.pack(fill=tk.X, padx=4, pady=(2, 8))
tk.Label(keys_row, text="Tuş Sırası (virgülle ayırın):", font=("Segoe UI", 9, "bold"), bg="#0B0C14", fg=ACCENT_CYAN, width=24, anchor="w").pack(side=tk.LEFT, padx=8, pady=5)
e_multi_keys = tk.Entry(keys_row, textvariable=var_multi_bait_keys, bg="#141724", fg=FG_COLOR, insertbackground=FG_COLOR, font=("Segoe UI", 9, "bold"), relief=tk.FLAT)
e_multi_keys.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=6, pady=5)
e_multi_keys.bind("<FocusOut>", lambda ev: (apply_settings(), update_multi_bait_ui()))

# 2. Canlı Durum ve Sıfırlama Butonu
status_row = tk.Frame(multi_bait_frame, bg=CARD_COLOR)
status_row.pack(fill=tk.X, padx=4, pady=2)

lbl_multi_bait_status = tk.Label(
    status_row,
    text=f"Aktif Tuş: [ALT+1] (Slot 1/4)  |  Kullanılan: {cfg_multi_bait_count}/200  (Kalan: {200 - cfg_multi_bait_count})",
    font=("Segoe UI", 9, "bold"), bg=CARD_COLOR, fg=ACCENT_CYAN
)
lbl_multi_bait_status.pack(side=tk.LEFT, padx=(2, 12))

btn_reset_multi = tk.Button(
    status_row, text="🔄 Sayacı Sıfırla (Başa Dön)",
    bg="#1F2937", fg="#F3F4F6", activebackground=ACCENT_CYAN, activeforeground="#000000",
    font=("Segoe UI", 8, "bold"), bd=0, relief=tk.FLAT,
    cursor="hand2", command=reset_multi_bait_counter
)
btn_reset_multi.pack(side=tk.RIGHT, padx=4, ipady=3, ipadx=8)

section_label(fish_tab_container, "ZIRH GİYME ANİMASYONU (SAĞ TIK)")
armor_cfg_card = make_card(fish_tab_container)
armor_cfg_frame = tk.Frame(armor_cfg_card, bg=CARD_COLOR)
armor_cfg_frame.pack(fill=tk.X, padx=10, pady=10)

btn_armor_pos = tk.Button(armor_cfg_frame, text="🛡️ Zırh Konum Kaydet",
                          bg="#1F2937", fg="#F3F4F6", activebackground=ACCENT_CYAN, activeforeground="#000000",
                          font=("Segoe UI", 9, "bold"), bd=0, relief=tk.FLAT,
                          cursor="hand2", command=start_armor_calibration)
btn_armor_pos.pack(side=tk.LEFT, padx=(4, 12), ipady=4, ipadx=8)

lbl_armor_pos = tk.Label(armor_cfg_frame, text="Zırh Konumu: Ayarlanmadı",
                         font=("Segoe UI", 9, "bold"), bg=CARD_COLOR, fg="#9CA3AF")
lbl_armor_pos.pack(side=tk.LEFT, padx=4)

section_label(fish_tab_container, "BALIK TUTMA TUŞ & ZAMANLAMA AYARLARI")
fish_cfg_card = make_card(fish_tab_container)
fish_cfg_frame = tk.Frame(fish_cfg_card, bg=CARD_COLOR)
fish_cfg_frame.pack(fill=tk.X, padx=10, pady=10)

f_row1 = tk.Frame(fish_cfg_frame, bg=CARD_COLOR)
f_row1.pack(fill=tk.X, pady=4)
tk.Label(f_row1, text="Yem Tuşu:", font=("Segoe UI", 9, "bold"), bg=CARD_COLOR, fg=FG_COLOR).pack(side=tk.LEFT, padx=(4, 6))
entry_bait = tk.Entry(f_row1, textvariable=var_fish_bait_key, width=6, bg="#0B0C14", fg=FG_COLOR, insertbackground=FG_COLOR,
                      font=("Segoe UI", 9, "bold"), relief=tk.FLAT, justify="center", highlightthickness=1, highlightbackground=BORDER_COLOR)
entry_bait.pack(side=tk.LEFT)
entry_bait.bind("<FocusOut>", lambda ev: apply_settings())

tk.Label(f_row1, text="Olta Atış Tuşu:", font=("Segoe UI", 9, "bold"), bg=CARD_COLOR, fg=FG_COLOR).pack(side=tk.LEFT, padx=(16, 6))
entry_rod = tk.Entry(f_row1, textvariable=var_fish_rod_key, width=6, bg="#0B0C14", fg=FG_COLOR, insertbackground=FG_COLOR,
                     font=("Segoe UI", 9, "bold"), relief=tk.FLAT, justify="center", highlightthickness=1, highlightbackground=BORDER_COLOR)
entry_rod.pack(side=tk.LEFT)
entry_rod.bind("<FocusOut>", lambda ev: apply_settings())

f_row2 = tk.Frame(fish_cfg_frame, bg=CARD_COLOR)
f_row2.pack(fill=tk.X, pady=4)

tk.Label(f_row2, text="Min Gecikme (sn):", font=("Segoe UI", 9, "bold"), bg=CARD_COLOR, fg=FG_COLOR).pack(side=tk.LEFT, padx=(4, 4))
entry_fmin = tk.Entry(f_row2, textvariable=var_fish_delay_min, width=5, bg="#0B0C14", fg=FG_COLOR, insertbackground=FG_COLOR,
                      font=("Segoe UI", 9, "bold"), relief=tk.FLAT, justify="center", highlightthickness=1, highlightbackground=BORDER_COLOR)
entry_fmin.pack(side=tk.LEFT)
entry_fmin.bind("<FocusOut>", lambda ev: apply_settings())

tk.Label(f_row2, text="Max Gecikme (sn):", font=("Segoe UI", 9, "bold"), bg=CARD_COLOR, fg=FG_COLOR).pack(side=tk.LEFT, padx=(12, 4))
entry_fmax = tk.Entry(f_row2, textvariable=var_fish_delay_max, width=5, bg="#0B0C14", fg=FG_COLOR, insertbackground=FG_COLOR,
                      font=("Segoe UI", 9, "bold"), relief=tk.FLAT, justify="center", highlightthickness=1, highlightbackground=BORDER_COLOR)
entry_fmax.pack(side=tk.LEFT)
entry_fmax.bind("<FocusOut>", lambda ev: apply_settings())

section_label(fish_tab_container, "BALIK DURUMU & İSTATİSTİK")
fish_stat_card = make_card(fish_tab_container)
fish_stat_frame = tk.Frame(fish_stat_card, bg=CARD_COLOR)
fish_stat_frame.pack(fill=tk.X, padx=10, pady=10)

lbl_fish_stat = tk.Label(fish_stat_frame, text="🎣 Balık Botu Hazır\nTutulan Balık: 0  |  Kaçırılan: 0",
                         font=("Segoe UI", 9, "bold"), bg=CARD_COLOR, fg=ACCENT_CYAN, justify="left")
lbl_fish_stat.pack(anchor="w", padx=6, pady=4)

# ==========================================
# UPDATE_UI (YENİDEN TANIMLA - MODERN GÖRSEL RENKLER)
# ==========================================
def update_ui():
    if is_running:
        status_dot.config(fg=SUCCESS)
        status_label.config(text="DURUM: AKTİF — BOT ÇALIŞIYOR", fg=SUCCESS)
        btn_start.config(state=tk.DISABLED, bg="#11131F", fg="#4B5563")
        btn_stop.config(state=tk.NORMAL, bg=DANGER, fg="#FFFFFF")
    else:
        status_dot.config(fg=DANGER)
        status_label.config(text="DURUM: BEKLİYOR", fg=DANGER)
        btn_start.config(state=tk.NORMAL, bg=SUCCESS, fg="#06281E")
        btn_stop.config(state=tk.DISABLED, bg="#11131F", fg="#4B5563")

# ==========================================
# KAYDETME / YÜKLEME
# ==========================================
def get_config_path():
    if getattr(sys, 'frozen', False):
        appdata = os.getenv('APPDATA')
        if appdata:
            cfg_dir = os.path.join(appdata, 'SyncMT2')
            os.makedirs(cfg_dir, exist_ok=True)
            return os.path.join(cfg_dir, 'config.json')
        return os.path.join(os.path.dirname(sys.executable), 'config.json')
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.json')

CONFIG_FILE = get_config_path()
is_loading_config = False

def save_config(*args):
    if is_loading_config:
        return
    apply_settings()
    data = {
        "modules": {
            "metin_enable":  var_metin_enable.get(),
            "space":         var_space.get(),
            "quote":         var_quote.get(),
            "target":        var_target.get(),
            "revive":        var_revive.get(),
            "hp":            var_hp.get(),
            "mp":            var_mp.get(),
            "item":          var_item.get(),
            "patrol":        var_patrol.get(),
            "clearing":      var_clearing.get(),
            "use_coords":    var_use_coords.get(),
            "ch_change":     var_ch_change.get(),
            "pot_alarm":     var_pot_alarm.get(),
            "horse_mode":    var_horse_mode.get(),
            "pm_stop":        var_pm_stop.get(),
            "player_name":   var_player_name.get(),
            "min_x":         var_min_x.get(),
            "max_x":         var_max_x.get(),
            "min_y":         var_min_y.get(),
            "max_y":         var_max_y.get(),
            "fish_enable":   var_fish_enable.get(),
            "fish_bait_key": var_fish_bait_key.get(),
            "fish_rod_key":  var_fish_rod_key.get(),
            "fish_delay_min":var_fish_delay_min.get(),
            "fish_delay_max":var_fish_delay_max.get(),
            "fish_delay":    var_fish_delay_min.get() + " - " + var_fish_delay_max.get(),
            "auto_bait":     var_auto_bait.get(),
            "auto_open_fish":var_auto_open_fish.get(),
            "fish_armor_anim":var_fish_armor_anim.get(),
            "captcha_enable": var_captcha_enable.get(),
            "captcha_alarm": var_captcha_alarm.get(),
            "multi_bait":    var_multi_bait.get(),
            "multi_bait_keys": var_multi_bait_keys.get().strip() or "alt+1, alt+2, alt+3, alt+4",
            "multi_bait_slot": cfg_multi_bait_slot,
            "multi_bait_count": cfg_multi_bait_count,
            "pm_reply_1":    var_pm_reply_1.get(),
            "pm_reply_2":    var_pm_reply_2.get(),
            "pm_reply_3":    var_pm_reply_3.get(),
            "armor_pos":     cfg_armor_pos,
            "metin_default": var_metin_default.get(),
            "metin_hirs":    var_metin_hirs.get(),
            "metin_savas":   var_metin_savas.get(),
            "metin_dovus":   var_metin_dovus.get(),
            "metin_siyah":   var_metin_siyah.get(),
            "metin_uzuntu":  var_metin_uzuntu.get(),
            "metin_ruh":     var_metin_ruh.get(),
            "hp_key":        var_hp_key.get(),
            "mp_key":        var_mp_key.get(),
        },
        "skills":   [],
        "hp_pixel": hp_pixel,
        "mp_pixel": mp_pixel
    }
    
    for skill in skills_config:
        data["skills"].append({
            "enabled":  skill["enabled"].get(),
            "key":      skill["key"].get(),
            "cooldown": skill["cooldown"].get()
        })
        
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
    except:
        pass

def load_config():
    global is_loading_config
    if not os.path.exists(CONFIG_FILE):
        return
        
    is_loading_config = True
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            
        mods = data.get("modules", {})
        # Metin/Balık mutex: ikisi aynı anda aktif olamaz, her ikisi de False olabilir
        _fish_val  = mods.get("fish_enable",  False)
        _metin_val = mods.get("metin_enable", False)
        if _fish_val and not _metin_val:
            var_fish_enable.set(True)
            var_metin_enable.set(False)
        elif _metin_val and not _fish_val:
            var_metin_enable.set(True)
            var_fish_enable.set(False)
        else:
            # Her ikisi de False (veya geçersiz durum) — her ikisini de False yap
            var_metin_enable.set(False)
            var_fish_enable.set(False)
        if "space"         in mods: var_space.set(mods["space"])
        if "quote"         in mods: var_quote.set(mods["quote"])
        if "target"        in mods: var_target.set(mods["target"])
        if "revive"        in mods: var_revive.set(mods["revive"])
        if "hp"            in mods: var_hp.set(mods["hp"])
        if "mp"            in mods: var_mp.set(mods["mp"])
        if "item"          in mods: var_item.set(mods["item"])
        if "patrol"        in mods: var_patrol.set(mods["patrol"])
        if "clearing"      in mods: var_clearing.set(mods["clearing"])
        if "use_coords"    in mods: var_use_coords.set(mods["use_coords"])
        if "ch_change"     in mods: var_ch_change.set(mods["ch_change"])
        if "pot_alarm"     in mods: var_pot_alarm.set(mods["pot_alarm"])
        if "horse_mode"    in mods: var_horse_mode.set(mods["horse_mode"])
        if "pm_stop"        in mods: var_pm_stop.set(mods["pm_stop"])
        if "player_name"   in mods: var_player_name.set(mods["player_name"])
        if "min_x"         in mods: var_min_x.set(mods["min_x"])
        if "max_x"         in mods: var_max_x.set(mods["max_x"])
        if "min_y"         in mods: var_min_y.set(mods["min_y"])
        if "max_y"         in mods: var_max_y.set(mods["max_y"])
        if "fish_enable"   in mods: pass  # Zaten yukarida mutex ile yuklendi
        if "fish_bait_key" in mods: var_fish_bait_key.set(mods["fish_bait_key"])
        if "fish_rod_key"  in mods: var_fish_rod_key.set(mods["fish_rod_key"])
        if "fish_delay_min"in mods: var_fish_delay_min.set(mods["fish_delay_min"])
        if "fish_delay_max"in mods: var_fish_delay_max.set(mods["fish_delay_max"])
        if "fish_delay"    in mods: var_fish_delay.set(mods["fish_delay"])
        if "auto_bait"     in mods: var_auto_bait.set(mods["auto_bait"])
        if "auto_open_fish"in mods: var_auto_open_fish.set(mods["auto_open_fish"])
        if "fish_armor_anim"in mods: var_fish_armor_anim.set(mods["fish_armor_anim"])
        if "captcha_enable" in mods: var_captcha_enable.set(mods["captcha_enable"])
        if "captcha_alarm" in mods: var_captcha_alarm.set(mods["captcha_alarm"])
        if "multi_bait"    in mods: var_multi_bait.set(mods["multi_bait"])
        if "multi_bait_keys" in mods: var_multi_bait_keys.set(mods["multi_bait_keys"])
        if "multi_bait_slot" in mods:
            global cfg_multi_bait_slot
            cfg_multi_bait_slot = int(mods.get("multi_bait_slot", 1))
        if "multi_bait_count" in mods:
            global cfg_multi_bait_count
            cfg_multi_bait_count = int(mods.get("multi_bait_count", 0))
        update_multi_bait_ui()
        if "pm_reply_1"   in mods: var_pm_reply_1.set(mods["pm_reply_1"])
        if "pm_reply_2"   in mods: var_pm_reply_2.set(mods["pm_reply_2"])
        if "pm_reply_3"   in mods: var_pm_reply_3.set(mods["pm_reply_3"])
        if "armor_pos"     in mods and mods["armor_pos"]:
            global cfg_armor_pos
            cfg_armor_pos = mods["armor_pos"]
            if isinstance(cfg_armor_pos, dict) and "x" in cfg_armor_pos and "y" in cfg_armor_pos:
                if 'lbl_armor_pos' in globals() and lbl_armor_pos:
                    lbl_armor_pos.config(text=f"Zırh Konumu: X={cfg_armor_pos['x']}, Y={cfg_armor_pos['y']}", fg=SUCCESS)
        if "metin_default" in mods: var_metin_default.set(mods["metin_default"])
        if "metin_hirs"    in mods: var_metin_hirs.set(mods["metin_hirs"])
        if "metin_savas"   in mods: var_metin_savas.set(mods["metin_savas"])
        if "metin_dovus"   in mods: var_metin_dovus.set(mods["metin_dovus"])
        if "metin_siyah"   in mods: var_metin_siyah.set(mods["metin_siyah"])
        if "metin_uzuntu"  in mods: var_metin_uzuntu.set(mods["metin_uzuntu"])
        if "metin_ruh"     in mods: var_metin_ruh.set(mods["metin_ruh"])
        if "hp_key"        in mods: var_hp_key.set(mods["hp_key"])
        if "mp_key"        in mods: var_mp_key.set(mods["mp_key"])
        
        global hp_pixel, mp_pixel
        hp_pixel = data.get("hp_pixel")
        mp_pixel = data.get("mp_pixel")
        
        apply_settings()
        
        loaded_skills = data.get("skills", [])
        for i, skill in enumerate(loaded_skills):
            if i < len(skills_config):
                skills_config[i]["enabled"].set(skill.get("enabled", False))
                skills_config[i]["key"].set(skill.get("key", ""))
                skills_config[i]["cooldown"].set(skill.get("cooldown", ""))
        # Skills yüklendikten sonra tüm toggle butonlarının görselini güncelle
        try:
            refresh_all_visuals()
        except Exception:
            pass
    except Exception as e:
        print("[HATA] Config yükleme hatası:", e)
    finally:
        is_loading_config = False

# Trace – her değişiklikte kaydet
for skill in skills_config:
    skill["key"].trace_add("write", save_config)
    skill["cooldown"].trace_add("write", save_config)
    skill["enabled"].trace_add("write", save_config)

for v in [var_space, var_quote, var_target, var_revive, var_hp, var_mp,
          var_item, var_patrol, var_clearing, var_use_coords, var_ch_change, var_pot_alarm, var_horse_mode, var_pm_stop, var_player_name,
          var_metin_enable,
          var_metin_default, var_metin_hirs, var_metin_savas, var_metin_dovus, var_metin_siyah, var_metin_uzuntu, var_metin_ruh,
          var_hp_key, var_mp_key, var_min_x, var_max_x, var_min_y, var_max_y,
          var_fish_enable, var_fish_bait_key, var_fish_rod_key, var_fish_delay_min, var_fish_delay_max, var_fish_delay, var_auto_bait, var_auto_open_fish, var_fish_armor_anim,
          var_captcha_enable, var_captcha_alarm, var_multi_bait, var_multi_bait_keys,
          var_pm_reply_1, var_pm_reply_2, var_pm_reply_3]:
    v.trace_add("write", save_config)

# Yükleme
load_config()

# Toggle buton görsellerini yenile
refresh_all_visuals()

root.mainloop()
