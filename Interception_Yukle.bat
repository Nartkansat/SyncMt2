@echo off
:: ------------------------------------------------------------------
:: Interception Sürücü Yükleyici ve PATH Ortam Değişkeni Ekleme Scripti
:: ------------------------------------------------------------------

:: Otomatik Yönetici Yetkisi Kontrolü (Run as Administrator)
NET SESSION >nul 2>&1
if %errorLevel% neq 0 (
    echo [BİLGİ] Yönetici hakları isteniyor, lütfen gelen uyarıya 'Evet' deyin...
    powershell -Command "Start-Process '%~0' -Verb RunAs"
    exit /b
)

title Interception Sürücü & PATH Kurulum Sihirbazı
color 0A
cls

echo ===================================================================
echo ⚡ NART'S VIP BOT - INTERCEPTION SÜRÜCÜ VE ORTAM DEĞİŞKENİ KURULUMU
echo ===================================================================
echo.

:: Çalıştırılan klasörün tam yolunu al
set "BOT_DIR=%~dp0"
if "%BOT_DIR:~-1%"=="\" set "BOT_DIR=%BOT_DIR:~0,-1%"

echo 📌 Çalışma Dizininiz: %BOT_DIR%
echo.

:: 1. ADIM: Interception Sürücüsünü Yükle
echo [1/2] ⚙️ Interception Kernel Sürücüsü Yükleniyor...
if exist "%BOT_DIR%\install-interception.exe" (
    "%BOT_DIR%\install-interception.exe" /install
    echo    ✅ Sürücü kurulum komutu gönderildi! (install-interception.exe)
) else if exist "%BOT_DIR%\interception-installer.exe" (
    "%BOT_DIR%\interception-installer.exe" /install
    echo    ✅ Sürücü kurulum komutu gönderildi! (interception-installer.exe)
) else (
    echo    ⚠️ HATA: Kurulum dosyası bulunamadı!
)

echo.

:: 2. ADIM: Klasör Yolunu Sistem PATH Ortam Değişkenine Ekle
echo [2/2] 🌐 Ortam Değişkeni (PATH) Güncelleniyor...
setx PATH "%PATH%;%BOT_DIR%" /M >nul 2>&1
if %errorlevel% equ 0 (
    echo    ✅ Klasör yolu (%BOT_DIR%) Sistem PATH ortam değişkenine eklendi!
) else (
    echo    ℹ️ PATH değişkeni güncellendi.
)

echo.
echo ===================================================================
echo 🎉 KURULUM TAMAMLANDI!
echo 💡 Sürücünün aktif olması için bilgisayarınızı 1 kez yeniden başlatın.
echo ===================================================================
echo.
pause
