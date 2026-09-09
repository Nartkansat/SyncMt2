@echo off
:: ------------------------------------------------------------------
:: Interception Sürücü Kaldırma (Uninstall) Scripti
:: ------------------------------------------------------------------

:: Otomatik Yönetici Yetkisi Kontrolü (Run as Administrator)
NET SESSION >nul 2>&1
if %errorLevel% neq 0 (
    echo [BİLGİ] Yönetici hakları isteniyor, lütfen gelen uyarıya 'Evet' deyin...
    powershell -Command "Start-Process '%~0' -Verb RunAs"
    exit /b
)

title Interception Sürücü Kaldırma Sihirbazı
color 0C
cls

echo ===================================================================
echo 🗑️ SYNC MT2 - INTERCEPTION SÜRÜCÜSÜNÜ KALDIRMA (UNINSTALL)
echo ===================================================================
echo.

:: Çalıştırılan klasörün tam yolunu al
set "BOT_DIR=%~dp0"
if "%BOT_DIR:~-1%"=="\" set "BOT_DIR=%BOT_DIR:~0,-1%"

echo 📌 Çalışma Dizininiz: %BOT_DIR%
echo.

:: Interception Sürücüsünü Kaldır (/uninstall)
echo [1/1] ⚙️ Interception Kernel Sürücüsü Kaldırılıyor (/uninstall)...
if exist "%BOT_DIR%\install-interception.exe" (
    "%BOT_DIR%\install-interception.exe" /uninstall
    echo    ✅ Sürücü kaldırma komutu başarıyla gönderildi!
) else if exist "%BOT_DIR%\interception-installer.exe" (
    "%BOT_DIR%\interception-installer.exe" /uninstall
    echo    ✅ Sürücü kaldırma komutu başarıyla gönderildi!
) else (
    echo    ⚠️ HATA: 'install-interception.exe' veya 'interception-installer.exe' bu klasörde bulunamadı!
)

echo.
echo ===================================================================
echo 🎉 KALDIRMA İŞLEMİ TAMAMLANDI!
echo 💡 Sürücünün sistemden tamamen kaldırılması için bilgisayarınızı 1 kez yeniden başlatın.
echo ===================================================================
echo.
pause
