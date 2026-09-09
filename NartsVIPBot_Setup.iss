; =====================================================================
; NART's VIP Bot - Inno Setup Kurulum Senaryosu (Tek Parça Setup)
; =====================================================================

[Setup]
AppName=NART's VIP Bot Metin2
AppVersion=3.6.0
AppPublisher=NART
DefaultDirName={autopf}\NartsVIPBot
DefaultGroupName=NartsVIPBot
OutputDir=dist_setup
OutputBaseFilename=NartsVIPBot_Setup_v3.5
Compression=lzma2/ultra64
SolidCompression=yes
PrivilegesRequired=admin
ArchitecturesInstallIn64BitMode=x64compatible

[Files]
; Derlenmiş Ana Bot EXE ve Sürücü Yükleyici
Source: "dist\NartsVIPBot.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "install-interception.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "interception.dll"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\NART's VIP Bot"; Filename: "{app}\NartsVIPBot.exe"
Name: "{autodesktop}\NART's VIP Bot"; Filename: "{app}\NartsVIPBot.exe"

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
Filename: "{app}\NartsVIPBot.exe"; Description: "NART's VIP Bot'u Başlat"; Flags: postinstall nowait skipifsilent
