; Branding is editable here. Build the application with ULTRON.spec first.
#ifndef AppVersion
  #define AppVersion "0.1.0-preview"
#endif
#ifndef BuildRoot
  #define BuildRoot "..\dist\ULTRON"
#endif
#define AppName "ULTRON"

[Setup]
AppId={{2DE9C30B-C7BB-4B8D-91C4-AD42AC1D6E23}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=ULTRON Project
DefaultDirName={localappdata}\Programs\ULTRON
DefaultGroupName=ULTRON
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
WizardStyle=modern
WizardSizePercent=115
SetupIconFile=..\config\jarvis.ico
LicenseFile=..\LICENSE
OutputDir=..\release
OutputBaseFilename=ULTRON-Setup-{#AppVersion}
Compression=lzma2
SolidCompression=yes
UninstallDisplayIcon={app}\ULTRON.exe
DisableProgramGroupPage=yes
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Messages]
WelcomeLabel1=Seu assistente. Do seu jeito.
WelcomeLabel2=Este assistente instalará o ULTRON neste computador.%n%nNa primeira abertura, você configura sua chave de IA e as integrações opcionais.%n%nNenhuma credencial pessoal é incluída neste instalador.
FinishedHeadingLabel=O ULTRON está instalado.
FinishedLabel=Abra o aplicativo para fazer a primeira configuração com segurança na sua conta.

[Tasks]
Name: "desktopicon"; Description: "Criar um atalho na área de trabalho"; GroupDescription: "Atalhos:"; Flags: unchecked

[Files]
Source: "{#BuildRoot}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\ULTRON"; Filename: "{app}\ULTRON.exe"; WorkingDir: "{app}"
Name: "{autodesktop}\ULTRON"; Filename: "{app}\ULTRON.exe"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\ULTRON.exe"; Description: "Abrir o ULTRON e configurar minha conta"; Flags: nowait postinstall skipifsilent

; Deliberately no [UninstallDelete] for user data or credentials.
