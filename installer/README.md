# Instalador online ULTRON — preto e vermelho

O caminho principal agora é `Bootstrap.spec`: gera **um único `ULTRON-Setup.exe`**
com interface PyQt6 própria, sem o wizard visual padrão do Windows. Ele contém
o assistente e uma lista explícita de fontes/assets; baixa o runtime privado e
as bibliotecas durante a etapa final. Precisa de internet nessa primeira instalação.

Fluxo: boas-vindas → Gemini → Spotify opcional → preparar ambiente → salvar
credenciais protegidas → abrir o launcher → iniciar o programa principal.
O ambiente é instalado em `%LOCALAPPDATA%/Programs/ULTRON`, separado dos dados
em `%LOCALAPPDATA%/ULTRON`. Não muda PATH, associações de Python ou a instalação
Python de outro projeto. O atalho fica no menu Iniciar.

O runtime e o bootstrap pip usam URLs HTTPS e SHA-256 fixos em `runtime.json`.
As fontes são verificadas contra o manifesto embutido. Antes das bibliotecas, o
Setup prepara setuptools/wheel no runtime privado. Os pacotes de fonte usam
`--no-build-isolation`, pois o Python embeddable ignora os caminhos temporários
de build que o pip normalmente utiliza. Isso corrige a falha de PyAutoGUI com
`Cannot import setuptools.build_meta`. Saídas sanitizadas das etapas ficam em
`data_root()/logs/setup-install.log`, acessível pelo botão de registro após falha. A instalação das bibliotecas
usa `requirements.txt` e o índice PyPI, no runtime privado. Cancelamento, falha de
rede ou erro de integridade não avançam para salvar as credenciais. Uma instalação
incompleta pode deixar arquivos temporários/componentes para uma nova tentativa.
Não há porcentagem fictícia: downloads com tamanho conhecido mostram bytes reais;
pip e outras etapas de duração desconhecida mostram progresso indeterminado.

O runtime selecionado é Python 3.13.17, último pacote binário 3.13 disponível
na conferência; 3.13.18 é uma atualização de segurança distribuída só em fonte.
Antes de distribuir além de testes, revisar a versão do runtime e validar uma
versão mantida com todas as dependências. As versões não estão congeladas em um
lockfile: o build ainda é experimental e exige teste de instalação limpa.

## Gerar o Setup único

Em um Python com PyQt6 e PyInstaller:

```powershell
python -m pip install "PyQt6>=6.6,<7" "pyinstaller>=6,<7"
.\installer\build-online.ps1 -Python python
```

Saída: `dist/ULTRON-Setup.exe` e seu arquivo SHA-256. O build não instala o
aplicativo no perfil do desenvolvedor. `.build-tools/`, quando existe, é usada
apenas para ferramentas locais desta worktree.

O build prepara primeiro `dist/ULTRON.exe`, um launcher pequeno e independente
com o ícone do aplicativo (`config/jarvis.ico`). Esse arquivo é incluído e
verificado por hash no Setup, cujo ícone é `config/setup.ico`. A atualização
preserva o launcher preparado, sem substituí-lo pelo próprio Setup. O download
para o usuário continua sendo um único `ULTRON-Setup.exe`.

O workflow compara os recursos de ícone dos dois executáveis e executa o Setup
em modo de smoke test offscreen, com diretórios fictícios e sem instalação,
credenciais, voz ou rede, antes de criar o rascunho de release.

## Aviso discreto de atualização

`release_config.json` contém versão e `github_repository` no formato `usuario/repo`.
Enquanto esse campo estiver vazio, não há consulta de rede e nenhum repositório
upstream é presumido. Para configurar uma distribuição:

```powershell
python installer/configure_release.py --repository usuario/repositorio --version 0.1.0
```

O aplicativo consulta o último release normal em uma thread de fundo a cada
cinco minutos enquanto está aberto. Não toma foco nem interrompe a conversa.
O botão **Baixar atualização** exige clique explícito e baixa o asset exato do
repositório configurado e verifica o SHA-256 dos metadados oficiais do GitHub.
Se o asset não tiver hash verificável, oferece somente a página do release.

Ao concluir o download, o cartão pergunta **Reiniciar agora** ou **Depois**.
Depois mantém o aplicativo aberto; um botão discreto **Atualização pronta**
permite retomar durante a sessão. Nenhum helper inicia antes dessa confirmação.
O hash é conferido novamente ao reiniciar e cada tentativa tem marcadores próprios.

O helper separado é o próprio Setup no modo `--apply-update`. Antes de fechar o
app, o download espera a prontidão do helper. O app encerra pelo coordenador
existente; o helper espera o processo sair, sem matá-lo, e adquire o lock.
Prepara runtime/bibliotecas em uma pasta irmã antes da troca. A pasta principal
instalada permanece no lugar: somente app, runtime e ULTRON.exe são promovidos,
com tentativas curtas em bloqueios temporários. Configuração de instalação e
outros arquivos na raiz permanecem. A versão anterior é restaurada se qualquer
promoção falhar. O journal schema 2 permite recuperar movimentos parciais ao
executar novamente um Setup normal; o formato antigo continua sendo reconhecido. Não há
rollback automático se a nova aplicação falhar após ser iniciada. Credenciais e
memória externas não são regravadas e o wizard não é repetido na atualização.
São necessários espaço para duas instalações e rede para preparar dependências.
Pastas de backup/staging ficam disponíveis para recuperação ou inspeção.

Versões anteriores à 0.1.1 precisam ser substituídas uma vez pelo novo Setup;
a publicação não pode acrescentar esse recurso a um processo antigo já aberto.
Os executáveis continuam sem assinatura de código; o hash é uma verificação de
integridade vinculada aos metadados HTTPS do repositório, não uma assinatura.

O workflow `.github/workflows/windows-setup.yml` prepara builds no GitHub e,
quando você envia uma tag de versão, cria um **rascunho de release** com o Setup.
Revisar e publicar manualmente. Nada foi enviado ao GitHub durante o desenvolvimento.
O código pode ficar no repositório e o executável como asset do release, evitando
commitar binários grandes no histórico.

Referências de implementação: [releases GitHub](https://docs.github.com/en/rest/releases/releases),
[runtime Python](https://www.python.org/downloads/release/python-31317/).

Alvo inicial: Windows x64. O instalador instala por usuário, sem administrador.
O atalho inicia o launcher; este inicia o mesmo executável com `--app` em outro
processo e acompanha o protocolo de boot existente. Não há Python externo no
computador de destino depois do empacotamento.

## Prévia sem voz, rede ou salvamento

```powershell
python ultron_entry.py --preview-setup
```

A prévia depende apenas do PyQt6. O botão final não grava dados e não inicia o
assistente. Clicar no link para obter uma chave abre o site no navegador.
O layout está em `ui_setup.py`; cores, tipografia, cartões e textos podem ser
editados ali. A janela do instalador é configurada separadamente em `setup.iss`.

## Armazenamento

`core/app_paths.py` separa recursos instalados de dados do usuário. No Windows,
os dados ficam em `%LOCALAPPDATA%\ULTRON`; `ULTRON_DATA_DIR` permite um diretório
absoluto separado para testes. Não há importação automática de dados da cópia
original. A nova instalação pede as credenciais do novo usuário.

`core/config_store.py` preserva as APIs de configuração e protege os campos de
credenciais com DPAPI por usuário no Windows. Preferências comuns continuam
legíveis no JSON; campos secretos viram referências para o bloco protegido.
JSON e `.env` sem criptografia não são cofres. Não há fallback em texto simples
se a proteção falhar. Outros sistemas usam um backend nativo explícito de keyring.
O armazenamento não protege contra um processo malicioso executado como o mesmo
usuário. Copiar o JSON para outro usuário/PC não transfere as chaves.

Spotify usa PKCE quando não há Client Secret legado; os tokens também passam
pelo armazenamento protegido. A autorização ocorre no primeiro uso no navegador.
Requer aplicativo cadastrado, redirect URI correto e acesso permitido pelo Spotify.

## Build empacotado alternativo (rascunho anterior)

Em um ambiente Python 3.11–3.13 com as dependências do projeto:

```powershell
python -m pip install -r requirements.txt
python -m pip install "pyinstaller>=6,<7"
.\installer\build.ps1 -Python python -AppOnly
# Para gerar o Setup, instale Inno Setup e indique seu compilador:
.\installer\build.ps1 -Python python -Iscc "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
```

Saídas: `dist/ULTRON/` e `release/ULTRON-Setup-0.1.0-preview.exe`.
O spec contém uma lista explícita de recursos; nunca empacota a pasta inteira do
projeto, seus JSONs pessoais, `.venv`, logs, memórias ou perfis de navegador.

## Limites deste rascunho

- Build gerado e abertura do executável validada em modo de teste: 94 arquivos
  embutidos conferidos, sem instalação, rede, voz ou credenciais. 105 testes
  locais passaram. A instalação completa em Windows limpo continua pendente.
- A chave Gemini tem validação local de preenchimento, não validação pela API.
- O onboarding começa por Gemini; outros engines são configurados no painel existente.
- Áudio é configurado depois na interface existente, não no wizard deste rascunho.
- O baseline congelado alternativo não inclui Whisper/Piper/wake word; os botões de instalação via pip
  são bloqueados na versão congelada. O suporte a componentes opcionais requer
  um pacote próprio, não executar `ULTRON.exe -m pip`.
- No Setup online, Chromium é um download opcional explícito na etapa final.
  Falha desse download impede concluir essa seleção; não é anunciada prontidão falsa.
- Existe aviso de atualização, mas não substituição automática de arquivos.
- Não há assinatura digital nem certificação do instalador.
- O Inno permanece apenas como alternativa ao Setup online de interface própria.
- Preservar licença e atribuições do projeto e das dependências distribuídas.

Antes de publicar: auditoria de segredos em conteúdo/histórico, build com ambiente
controlado, instalação em VM sem Python, verificação de launcher/shutdown, áudio,
dashboard, Spotify e proteção de credenciais; depois revisar desinstalação e upgrade.

O Setup online ainda não registra desinstalador. Remoção/upgrade transacional e
assinatura digital continuam pendentes. A licença atual do código é CC BY-NC 4.0:
publicar o código não altera suas condições nem permite reclassificá-lo como
licença de código aberto permissiva; preservar o LICENSE e as atribuições.
