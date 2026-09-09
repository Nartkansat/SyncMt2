; =====================================================================
; SyncMT2 Otomasyon Engine - Inno Setup Kurulum Senaryosu (Tek Parça Setup)
; =====================================================================

[Setup]
AppName=SyncMT2 Otomasyon Engine
AppVersion=3.6.0
AppPublisher=SyncMT2
DefaultDirName={autopf}\SyncMT2
DefaultGroupName=SyncMT2
OutputDir=dist_setup
OutputBaseFilename=SyncMT2_Setup_v3.5
Compression=lzma2/ultra64
SolidCompression=yes
PrivilegesRequired=admin
ArchitecturesInstallIn64BitMode=x64compatible

[Files]
; Derlenmiş Ana Bot EXE (main.exe) ve Sürücü Yükleyicileri
Source: "dist\main.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "install-interception.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "interception.dll"; DestDir: "{app}"; Flags: ignoreversion
Source: "config.json"; DestDir: "{app}"; Flags: ignoreversion onlyifdoesntexist

[Icons]
Name: "{autoprograms}\SyncMT2 Otomasyon"; Filename: "{app}\main.exe"
Name: "{autodesktop}\SyncMT2 Otomasyon"; Filename: "{app}\main.exe"

[Registry]
; Kurulum Yapılan Klasörü Otomatik Olarak Windows PATH Ortam Değişkenine Ekle
Root: HKLM; Subkey: "SYSTEM\CurrentControlSet\Control\Session Manager\Environment"; \
    ValueType: expandsz; ValueName: "Path"; ValueData: "{olddata};{app}"; \
    Check: NeedsAddPath('{app}')

[Code]
function NeedsAddPath(Param: string): boolean;
var
  OrigPath: string;
begin
  if not RegQueryStringValue(HKEY_LOCAL_MACHINE,
    'SYSTEM\CurrentControlSet\Control\Session Manager\Environment',
    'Path', OrigPath) then
  begin
    Result := True;
    exit;
  end;
  Result := Pos(Uppercase(Param), Uppercase(OrigPath)) = 0;
end;

[Run]
; 1. Kurulum Esnasında Interception Sürücüsünü Arka Planda Sessizce Yükle
Filename: "{app}\install-interception.exe"; Parameters: "/install"; StatusMsg: "Interception Klavye/Fare Sürücüsü Yükleniyor..."; Flags: runhidden waituntilterminated

; 2. Kurulum Bitince Botu Çalıştırma Seçeneği
Filename: "{app}\main.exe"; Description: "SyncMT2 Otomasyonunu Başlat"; Flags: postinstall nowait skipifsilent
