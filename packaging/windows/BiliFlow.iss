; Values are supplied by scripts.package_installers, from the same full payload as ZIP.
[Setup]
AppId={{390aa6e8-8afd-4b5e-af65-e10892d29a71}
AppName=BiliFlow
AppVersion={#AppVersion}
VersionInfoVersion={#NumericVersion}
AppPublisher=BiliFlow
AppPublisherURL=https://github.com/itsVicOC/bilibili-downloader
DefaultDirName={localappdata}\Programs\BiliFlow
DefaultGroupName=BiliFlow
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
UninstallFilesDir={app}\uninst
UninstallDisplayIcon={app}\BilibiliDownloader\BilibiliDownloader.exe
AppMutex=Local\BiliFlow.Runtime
SetupMutex=Local\BiliFlow.Setup
CloseApplications=no
RestartApplications=no
OutputDir={#OutputDir}
OutputBaseFilename=BilibiliDownloader-Windows-full-{#ReleaseId}-setup
SetupIconFile=..\..\bilibili_downloader\gui\assets\app_icon.ico
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
DisableProgramGroupPage=yes

[Languages]
Name: "chinesesimplified"; MessagesFile: "ChineseSimplified.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; Flags: unchecked

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}\BilibiliDownloader"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#SourceDir}\biliflow-updater.exe"; DestDir: "{app}\uninst"; DestName: "biliflow-maintenance.exe"; Flags: ignoreversion
Source: "biliflow-installed"; DestDir: "{app}"; DestName: ".biliflow-installed"; Flags: ignoreversion

[Icons]
Name: "{userprograms}\BiliFlow"; Filename: "{app}\BilibiliDownloader\BilibiliDownloader.exe"; WorkingDir: "{app}"
Name: "{userdesktop}\BiliFlow"; Filename: "{app}\BilibiliDownloader\BilibiliDownloader.exe"; WorkingDir: "{app}"; Tasks: desktopicon

[UninstallRun]
Filename: "{app}\uninst\biliflow-maintenance.exe"; Parameters: "--remove-managed-files ""{app}\BilibiliDownloader"""; Flags: runhidden waituntilterminated

[Code]
function InitializeUninstall(): Boolean;
begin
  CreateMutex('Local\BiliFlow.Setup');
  Result := True;
end;
