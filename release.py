#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SyncMT2 Otomatik Versiyonlama & Git/GitHub Release Yöneticisi
Kullanım:
  python release.py           (Etkileşimli menü)
  python release.py patch -m "Küçük hata düzeltmeleri"
  python release.py minor -m "Yeni özellikler eklendi"
  python release.py major -m "Büyük güncelleme"
  python release.py 3.6.0 -m "Özel versiyon"
"""

import os
import sys
import re
import subprocess
import argparse

VISION_FILE = "vision.py"
ISS_FILES = ["SyncMT2_Setup.iss", "NartsVIPBot_Setup.iss"]

def run_cmd(cmd, check=True):
    """Terminal komutunu çalıştırır ve çıktısını döndürür."""
    res = subprocess.run(cmd, shell=True, text=True, capture_output=True)
    if check and res.returncode != 0:
        print(f"\n[HATA] Komut başarısız: {cmd}")
        print(f"Detay: {res.stderr.strip() or res.stdout.strip()}")
        sys.exit(res.returncode)
    return res.stdout.strip()

def get_current_version():
    """vision.py içerisinden mevcut APP_VERSION değerini okur."""
    if not os.path.exists(VISION_FILE):
        print(f"[HATA] {VISION_FILE} bulunamadı!")
        sys.exit(1)
    with open(VISION_FILE, "r", encoding="utf-8") as f:
        content = f.read()
    m = re.search(r'APP_VERSION\s*=\s*["\']([^"\']+)["\']', content)
    if m:
        return m.group(1)
    return "1.0.0"

def calculate_next_version(current, bump_type):
    """SemVer kuralına göre sonraki versiyonu hesaplar."""
    parts = current.split(".")
    while len(parts) < 3:
        parts.append("0")
    try:
        major, minor, patch = int(parts[0]), int(parts[1]), int(parts[2])
    except ValueError:
        major, minor, patch = 1, 0, 0

    bump = bump_type.lower().strip()
    if bump == "patch":
        return f"{major}.{minor}.{patch + 1}"
    elif bump == "minor":
        return f"{major}.{minor + 1}.0"
    elif bump == "major":
        return f"{major + 1}.0.0"
    elif re.match(r"^\d+(\.\d+)*$", bump):
        return bump
    else:
        print(f"[HATA] Geçersiz versiyon veya tür: {bump_type}")
        sys.exit(1)

def update_files_version(new_version):
    """vision.py ve .iss kurulum dosyalarındaki versiyon numaralarını günceller."""
    # 1. vision.py
    with open(VISION_FILE, "r", encoding="utf-8") as f:
        content = f.read()
    new_content = re.sub(
        r'APP_VERSION\s*=\s*["\'][^"\']+["\']',
        f'APP_VERSION = "{new_version}"',
        content
    )
    with open(VISION_FILE, "w", encoding="utf-8") as f:
        f.write(new_content)
    print(f"  ✔ {VISION_FILE} -> v{new_version}")

    # 2. .iss dosyaları (varsa)
    for iss in ISS_FILES:
        if os.path.exists(iss):
            with open(iss, "r", encoding="utf-8", errors="ignore") as f:
                iss_c = f.read()
            iss_c = re.sub(r'AppVersion=[^\r\n]+', f'AppVersion={new_version}', iss_c)
            with open(iss, "w", encoding="utf-8") as f:
                f.write(iss_c)
            print(f"  ✔ {iss} -> AppVersion={new_version}")

def get_remote_url():
    """Git remote origin adresini alır."""
    try:
        url = run_cmd("git remote get-url origin", check=False)
        return url
    except Exception:
        return ""

def main():
    sys.stdout.reconfigure(encoding="utf-8") if hasattr(sys.stdout, "reconfigure") else None

    # Git yüklü mü kontrol et
    run_cmd("git --version")

    current_ver = get_current_version()
    print("=" * 60)
    print("⚡ SyncMT2 Otomatik Versiyonlama ve GitHub Yayınlayıcı")
    print("=" * 60)
    print(f"📌 Mevcut Versiyon: v{current_ver}\n")

    parser = argparse.ArgumentParser(description="SyncMT2 Otomatik Versiyonlama")
    parser.add_argument("bump", nargs="?", default=None, help="patch | minor | major ya da özel versiyon (örn: 3.6.0)")
    parser.add_argument("-m", "--message", default="", help="Versiyon / sürüm açıklama notu")
    args = parser.parse_args()

    bump_input = args.bump
    message = args.message

    # Argüman verilmemişse etkileşimli mod aç
    if not bump_input:
        next_patch = calculate_next_version(current_ver, "patch")
        next_minor = calculate_next_version(current_ver, "minor")
        next_major = calculate_next_version(current_ver, "major")

        print("Lütfen yapılacak sürüm artışını seçin:")
        print(f"  [1] Patch  (v{current_ver} -> v{next_patch}) [Küçük düzeltmeler / bugfix]")
        print(f"  [2] Minor  (v{current_ver} -> v{next_minor}) [Yeni özellikler / eklentiler]")
        print(f"  [3] Major  (v{current_ver} -> v{next_major}) [Büyük sürüm / mimari değişim]")
        print("  [4] Özel versiyon numarası girin")
        print("  [0] İptal")

        choice = input("\nSeçiminiz (1-4, Varsayılan: 1): ").strip() or "1"
        if choice == "0":
            print("İşlem iptal edildi.")
            return
        elif choice == "1":
            bump_input = "patch"
        elif choice == "2":
            bump_input = "minor"
        elif choice == "3":
            bump_input = "major"
        elif choice == "4":
            bump_input = input("Özel versiyon numarasını yazın (örn: 3.6.0): ").strip()
        else:
            bump_input = "patch"

    new_version = calculate_next_version(current_ver, bump_input)

    if not message:
        message = input(f"\nSürüm v{new_version} için değişiklik notunu yazın: ").strip()
        if not message:
            message = f"Release v{new_version}"

    tag_name = f"v{new_version}"
    print(f"\n🚀 Sürüm Hazırlanıyor: {tag_name}")
    print(f"📝 Değişiklik Notu: {message}")
    print("-" * 60)

    # 1. Dosyalardaki versiyonları güncelle
    print("[1/5] Dosyalarda versiyon numaraları güncelleniyor...")
    update_files_version(new_version)

    # 2. Değişiklikleri Git'e ekle
    print("[2/5] Git değişiklikleri hazırlanıyor (git add)...")
    run_cmd("git add -A")

    # 3. Commit oluştur
    print("[3/5] Git commit oluşturuluyor...")
    commit_msg = f"chore(release): {tag_name} - {message}"
    run_cmd(f'git commit -m "{commit_msg}"')

    # 4. Git Etiketi (Tag) oluştur
    print(f"[4/5] Git etiketi oluşturuluyor ({tag_name})...")
    run_cmd(f'git tag -a {tag_name} -m "{message}"')

    # 5. GitHub'a Push et
    print("[5/5] GitHub'a gönderiliyor (git push & git push --tags)...")
    run_cmd("git push origin main")
    run_cmd("git push origin --tags")

    print("\n" + "=" * 60)
    print(f"🎉 TEBRİKLER! {tag_name} BAŞARIYLA YAYINLANDI!")
    print("=" * 60)
    remote_url = get_remote_url()
    if "github.com" in remote_url:
        clean_url = remote_url.replace(".git", "").replace("git@", "https://").replace("github.com:", "github.com/")
        print(f"🔗 GitHub Sürüm Sayfası:")
        print(f"   {clean_url}/releases/tag/{tag_name}")
    print(f"📌 Git Etiketi: {tag_name}")
    print(f"📄 Not: {message}")
    print("=" * 60)

if __name__ == "__main__":
    main()
