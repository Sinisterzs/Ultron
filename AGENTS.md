# Contexto do projeto para agentes de IA — MARK LVI / ULTRON

Referência inicial para entender e alterar este repositório. Conferido por leitura
do código em **29/10/2026**. Este documento não comprova funcionamento de serviços
externos nem substitui a leitura dos arquivos envolvidos na alteração.

## Política operacional do Codex

Estas regras complementam os contratos técnicos abaixo; não substituem segurança, autorização humana nem validação.

- Execute tarefas pequenas diretamente. Para mudanças complexas, planeje em poucos passos e mantenha o plano atualizado somente quando necessário.
- Antes de editar, consulte `git status --short` e o diff pertinente. Preserve trabalho local, inclusive arquivos não rastreados.
- Limite a leitura a arquivos afetados, chamadores, contratos e testes relevantes. Não faça varreduras repetitivas sem evidência de necessidade.
- Faça a menor alteração coerente que resolva a causa; não expanda escopo ou refatore módulos não relacionados.
- Tenha autonomia para mudanças reversíveis dentro do pedido. Peça autorização antes de apagar dados, substituir mudanças do usuário, publicar, fazer push, criar release/tag, executar operações externas sensíveis ou mudar escopo significativamente.
- Execute testes direcionados proporcionais ao risco e informe o que foi ou não validado. Não execute aplicações, instaladores, downloads ou integração real como simples teste.
- Em tarefas interrompidas, identifique o que já foi concluído por meio do estado do repositório e dos resultados disponíveis; não recomece nem repita testes sem necessidade.
- Conclua ao atingir o objetivo e validar o escopo; não continue refinando indefinidamente.
- Resumo final conciso: alterações, arquivos, testes/resultados, riscos e pendências. Não afirme sucesso sem evidências.
- Economia de tokens é secundária à correção, segurança e clareza. Evite relatar raciocínio extenso ou executar ferramentas redundantes, mas não omita verificações necessárias.

**Escopo de instruções:** arquivos `AGENTS.md` em `core/`, `installer/` e `tests/` detalham regras específicas. Ao trabalhar nessas áreas, leia o arquivo correspondente se ainda não estiver no contexto da sessão; regras específicas complementam esta política sem revogar controles de segurança.

## 1. O que o aplicativo faz

É um assistente pessoal desktop em Python, com interface holográfica PyQt6.
O código e o README usam os nomes MARK LVI, JARVIS e ULTRON; a interface atual
exibe ULTRON. Não confundir diferenças de nome com aplicativos separados.

As funcionalidades implementadas incluem:

- Conversação por voz com Gemini Live, captura/reprodução de áudio, transcrições,
  interrupções, sincronização visual da fala e proteção contra eco da própria voz.
- Alternativa configurável com reconhecimento de fala, LLM e síntese de voz em
  componentes separados, inclusive modelos locais e APIs compatíveis com OpenAI.
- Interface animada, cristal/avatar, temas, navegação, métricas de hardware,
  entrada de texto, seleção de áudio e painéis de configurações.
- Push-to-talk, wake word opcional e detector de palmas.
- Memória persistente, resumo de sessão, briefing e monitoramento de assuntos.
- Ações de desktop, arquivos, navegador, busca, clima, vídeo, mensagens e outras
  integrações, expostas ao modelo por ferramentas descobertas em tempo de execução.
- Dashboard remoto FastAPI com páginas estáticas, autenticação e pareamento.

Uma funcionalidade estar no código não significa que esteja habilitada ou
disponível: depende de configurações, credenciais, bibliotecas, hardware,
permissões e serviços externos. O projeto não é inteiramente offline.

## 2. Ambiente e execução

- O projeto é Python desktop, não um frontend Node/React. Não há build npm.
- `setup.py` é um script de instalação, não uma declaração setuptools de pacote.
- O instalador exige Python 3.11 e declara 3.13 como maior versão testada.
  Use um interpretador compatível; isso não garante toda combinação de dependências.
- A máquina desta inspeção é Windows; há caminhos específicos para Windows,
  macOS e Linux. Não remover as condições de plataforma.
- A worktree do instalador não copia `.venv/`. Criar um ambiente próprio ou indicar
  explicitamente um interpretador preparado. Na primeira validação foi usado,
  sem instalar nada nele, o ambiente da cópia original.

Comandos a partir da raiz, no PowerShell:

```powershell
# Exemplos depois de preparar um ambiente próprio nesta worktree.
.\.venv\Scripts\python.exe --version

# Iniciar a interface pelo launcher atual.
.\.venv\Scripts\python.exe launcher.py

# Iniciar diretamente a aplicação principal.
.\.venv\Scripts\python.exe main.py
```

Em uma instalação nova, `python setup.py` instala dependências e componentes do
Playwright. Alternativa manual: `python -m pip install -r requirements.txt` e
`python -m playwright install chromium`. Instalação baixa arquivos e altera o
ambiente; não é uma verificação somente de leitura.

Executar a aplicação pode conectar serviços, capturar áudio e gravar configurações.
Não usar inicialização real como se fosse um teste unitário sem efeitos.

## 3. Pontos de entrada e mapa do código

| Arquivo ou área | Responsabilidade |
|---|---|
| `launcher.py` | Janela de inicialização; cria processo separado para `main.py` e acompanha estado real do boot. |
| `ultron_entry.py` | Entrada empacotável: sem argumentos abre launcher; `--app` inicia o principal; `--preview-setup` abre somente a prévia do wizard. |
| `ui_setup.py` | Wizard de primeira configuração; emite dados apenas ao concluir, sem iniciar voz por si só. |
| `core/app_paths.py`, `core/config_store.py` | Recursos/dados separados e armazenamento atômico de configuração com credenciais protegidas. |
| `core/ip_geolocation.py` | Localização aproximada por IP, lazy e em cache de memória, usada apenas como pista regional de pesquisa. |
| `core/location_preferences.py`, `core/location_settings.py` | Preferência regional confirmada, moeda derivada do país por Qt/CLDR e cartão de localização em Ajustes. |
| `core/search_sources.py` | Perfis de domínio por assunto/país para buscas de ofertas e imóveis, sem inferir reputação ou confirmação de preço. |

Pesquisas `search`/`price` classificadas como hardware/imóveis usam perfis BR:
KaBuM/Terabyte/Amazon e QuintoAndar/ZAP/VivaReal, respectivamente. DDG recebe
filtro de domínios e os resultados são novamente filtrados por hostname exato
ou subdomínio; perfil vazio de resultados não expande para agregadores/lojas
desconhecidas. `expand_sources=true` exige pedido explícito do usuário.
`site` explícito prevalece; `country` explícito ou país nomeado na consulta
prevalece à preferência manual/IP. País/assunto sem perfil recebe busca
regional identificada como sem perfil conhecido; notícias não usam o perfil.
Não prometer portais populares de cada cidade nem confundir preferência de
domínio com oferta/pagamento verificado. Módulo incluído por `core/*.py`.

`get_search_location()` prioriza a preferência manual em `search_location`,
salva com `core.config_store.update_config` preservando os outros campos e a
proteção de credenciais. Sem override, usa o IP aproximado. Cidade, estado
opcional e país são confirmados pelo usuário; moeda não é editável, deriva
da base CLDR do Qt. Não deduzir cidade física por idioma/fuso. Ajustes consulta
localização e salva/reset em worker ao exibir/interagir com o cartão; sem
rede no import/boot ou thread Qt. Voltar ao automático limpa o override.
O contexto regional continua subordinado à região explícita na pesquisa.
Os módulos ficam em `core/*.py`, já cobertos pela allowlist do payload.
| `core/offer_verifier.py` | Verificação HTTP limitada de ofertas específicas por HTML/JSON-LD, sem navegador, credenciais ou armazenamento de páginas. |

O verificador limita a resposta recebida a 750 KB e a descompressão gzip a
3 MB, respeita charset declarado e recusa codificações não suportadas. A
extração HTML reconhece campos da oferta principal Amazon BR e o vendedor
explicitamente declarado na KaBuM, complementando JSON-LD. Condição de
pagamento só acompanha o preço quando está no mesmo pequeno bloco e o valor
coincide; na ausência dessa evidência retorna `payment_condition=not confirmed`.
Somas de parcelas usam Decimal em `calculated_total`, explicitamente calculado;
`declared_total` é reservado ao total rotulado pela loja. KaBuM pode fornecer
`embedded_regular_price`, com identidade/vendedor/preço Pix/parcelas conferidos
no `__NEXT_DATA__`; divergências de arredondamento são preservadas.
Timeout de 5 s é por operação de socket,
não um prazo global de toda pesquisa; estoque/checkout não são comprovados.
Os adaptadores `_amazon_offer`/`_kabum_offer` compartilham a validação `_offer`.
Amazon associa os blocos irmãos da oferta principal ao ASIN do widget de
parcelamento; valores de parcela e total declarado seguem em `installments`,
separados de `cash_price`/`cash_methods`, sem calcular total por multiplicação.
| `installer/` | Spec PyInstaller, script de build, configuração Inno Setup e documentação do rascunho. |
| `bootstrap_entry.py`, `installer/Bootstrap.spec` | Setup online único: interface própria e runtime privado com bibliotecas baixadas na preparação final. |
| `core/install_manager.py`, `core/runtime_lock.py` | Download verificado, instalação no runtime privado e bloqueio para não sobrescrever a aplicação em execução. |
| `core/updates.py`, `ui_updates.py`, `release_config.json` | Consulta de releases, aviso discreto e atualização com clique e helper separado. |
| `main.py` | `main()` e `JarvisLive`: áudio, sessão, ferramentas, integração com UI, reconexão e encerramento. |
| `ui.py` | `JarvisUI`, `MainWindow`, `HudCanvas`, overlays, dispositivos, configurações e renderização. |
| `ui_sidebar.py` | Navegação/dock; animações, cache e diagnósticos próprios. |
| `ui_titlebar.py`, `ui_theme.py`, `ui_activity.py` | Barra de título, tema e painel de atividades. |
| `core/crystal_pulse.py` | `HoloCrystal` e visual do cristal. |
| `crystal_pulse.py` | Reexporta `HoloCrystal` e `SPAN`; há caminho alternativo de importação na UI. |
| `core/avatar.py`, `avatar_mesh.py`, `eye.py`, `orb.py`, `viseme.py` | Outros componentes visuais, geometria e articulação da fala. |
| `core/gemini.py`, `core/prompt.txt` | Seleção/fallback de modelos Gemini e template de prompt. |
| `core/action_loader.py`, `core/plugin_loader.py` | Descoberta, validação e despacho de ferramentas. |
| `core/lazyimport.py` | Importação adiada de bibliotecas para reduzir custo de inicialização. |
| `core/outcome.py`, `confirm.py`, `undo.py` | Resultado verificável, confirmação humana e desfazer. |
| `core/audio_devices.py`, `echo.py`, `hotkey.py`, `wake_word.py`, `clap_wake.py` | Áudio, eco, atalhos globais e ativação. |
| `actions/` | Ferramentas incorporadas: sistema, arquivos, navegador, busca, mensagens, mídia etc. |
| `plugins/` | Plugins descobertos dinamicamente; existem Spotify e um template nesta cópia. |
| `providers/` | Contratos e implementações configuráveis de STT/LLM/TTS/engine. |
| `memory/config_manager.py` | Leitura/escrita de configurações, inclusive providers. |
| `memory/memory_manager.py` | Memória persistente, busca e resumos. |
| `dashboard/server.py`, `dashboard/static/` | Servidor remoto e arquivos HTML/JavaScript servidos por ele. |
| `core/whatsapp_web.py`, `whatsapp_desktop.py`, `whatsapp_driver.py` | Automação WhatsApp e contrato do driver. |
| `tests/`, `tools/`, `docs/whatsapp-validation.md` | Testes e ferramentas/documentação de validação WhatsApp. |
| `prototypes/` | Experimentos e validações separados; não são a aplicação principal. |

Os caminhos de `core/` abreviados na tabela pertencem a essa mesma pasta.
As variantes antigas de launcher da cópia de desenvolvimento não integram esta
publicação. Use `ultron_entry.py` ou `launcher.py` como entrada.

## 4. Fluxo de inicialização e concorrência

1. No código-fonte, `launcher.py` inicia `main.py` pelo mesmo `sys.executable`.
   No pacote, inicia `ULTRON.exe --app` em outro processo, preservando o launcher.
2. O launcher passa `MARK_LVI_BOOT_STATUS`, apontando para um JSON temporário.
   `main.py` publica fases reais; `hud_shown` indica que a janela foi exibida,
   não que todos os serviços de voz já estão conectados.
3. `main()` constrói `JarvisUI`; a UI permanece na thread do Qt.
4. Uma thread `MarkLVI-Async` executa o loop asyncio da sessão. A inicialização
   respeita o estado de prontidão da configuração da UI.
5. O fechamento coordena cancelamento, serviços e término do worker antes de
   liberar a janela; preservar essa sequência ao mudar boot ou shutdown.

Não criar outro `QApplication` nem outro loop Qt no fluxo principal. Atualizações
de widgets devem passar pelo mecanismo de sinais/slots ou despacho da UI;
workers não devem modificar widgets diretamente. Não colocar rede, instalação,
model loading ou espera bloqueante na thread da interface.

`HudCanvas` possui pacing/timer compartilhado e sinal `pacedFrame`. Antes de
introduzir outra animação, verificar como a atual compartilha a cadência e evita
repaint excessivo. Não adicionar timers concorrentes por conveniência.

No Windows, `main.py` também adapta `subprocess.Popen` para evitar janelas de
console. Uma mudança em subprocessos deve considerar esse comportamento global.

## 5. Ferramentas, plugins e providers: contratos importantes

- O carregador executa módulos de `actions/*.py` e descobre suas declarações
  `TOOL`; o fluxo não depende apenas de imports explícitos em `main.py`.
- Uma ação declara nome, descrição, parâmetros e handler. Inspecionar o loader
  e uma ação semelhante antes de criar outra; parâmetros de contexto são
  encaminhados conforme a assinatura aceita pelo handler.
- Plugins seguem o contrato de `core/plugin_loader.py` e a configuração de
  habilitação. Usar `plugins/_template.py` como referência, verificando o loader.
- Preservar `core.lazyimport` e imports locais de dependências pesadas. Descobrir
  uma ferramenta não deve carregar antecipadamente todas as bibliotecas externas.
- Metadados internos como `tier` e `brief` são retirados por `strip_meta()` antes
  de enviar declarações à API. Não encaminhar campos internos ao Gemini.
- `providers/registry.py` usa uma lista explícita `_MODULES`, por categoria;
  adicionar só um arquivo nessa pasta não garante descoberta do provider.
- Providers declaram `PROVIDER`; os contratos estão em `providers/base.py`.
  Os novos engines se adaptam aos eventos e métodos esperados pela sessão
  existente; não pressupor que mudar o engine autoriza reescrever toda a sessão.
- O caminho padrão Gemini evita carregar providers desnecessariamente. Preservar
  a inicialização adiada e as capacidades declaradas, inclusive suporte a visão.
- `core/outcome.py` diferencia `done`, `unverified`, `failed` e `ask`. Uma chamada
  aceita ou um clique tentado não comprovam sucesso. Relatar evidência real.
- Preservar a confirmação humana de `core/confirm.py`, os recursos de undo e as
  verificações/deduplicação de mensagens; não simular confirmação pelo modelo.

## 6. Bibliotecas e nomes de importação

`requirements.txt` é a referência de instalação e dos limites de versão. A lista
abaixo mapeia os pacotes declarados para seus imports usuais. Nem todo extra
declarado tem plugin correspondente presente nesta cópia.

| Área | Distribuição pip → import |
|---|---|
| UI e áudio | `PyQt6` → `PyQt6`; `sounddevice` → `sounddevice`; `numpy` → `numpy` |
| Gemini e HTTP | `google-genai` → `google.genai`; `httpx` → `httpx`; `requests` → `requests` |
| Busca e páginas | `beautifulsoup4` → `bs4`; `ddgs` → `ddgs`; `playwright` → `playwright` |
| Automação | `pyautogui` → `pyautogui`; `pyperclip` → `pyperclip`; `pygetwindow` → `pygetwindow` |
| Imagem e captura | `pillow` → `PIL`; `opencv-python` → `cv2`; `mss` → `mss` |
| Sistema | `psutil` → `psutil`; `send2trash` → `send2trash`; `pynvml` → `pynvml` |
| Documentos | `python-pptx` → `pptx`; `python-docx` → `docx`; `pdfplumber` → `pdfplumber`; `PyPDF2` → `PyPDF2` |
| Dashboard | `fastapi` → `fastapi`; `uvicorn[standard]` → `uvicorn`; `cryptography` → `cryptography`; `python-multipart` para formulários; `qrcode[pil]` → `qrcode` |
| Vídeo | `yt-dlp` → `yt_dlp`; `youtube-transcript-api` → `youtube_transcript_api` |
| Extras declarados | `google-api-python-client` → `googleapiclient`; `google-auth-oauthlib` → `google_auth_oauthlib`; `tinytuya` → `tinytuya`; `paho-mqtt` → `paho.mqtt`; `openpyxl` → `openpyxl`; `spotipy` → `spotipy` |
| Windows | `comtypes` → `comtypes`; `pycaw` → `pycaw`; `win10toast` → `win10toast`; `pywin32` fornece `win32com` e outros módulos Win32; `wmi` → `wmi`; `pywinauto` → `pywinauto` |

Os pacotes exclusivos de Windows têm marcadores `sys_platform == "win32"` no
requirements. QtMultimedia/QtMultimediaWidgets fazem parte do ecossistema PyQt6;
não migrar a aplicação para PySide6 por causa de arquivos de experimentos.
Playwright precisa de seus navegadores além do pacote Python. `yt-dlp` está
intencionalmente sem limite de versão no requirements por mudanças do YouTube.

### Opcionais, fallbacks e código de caminhos antigos

- `faster-whisper` / `faster_whisper`: reconhecimento local; modelos são downloads.
- `piper-tts` / `piper`: voz neural local; vozes também precisam estar disponíveis.
- `openwakeword` / `openwakeword`: wake word e respectivos modelos, opt-in.
- `pandas`, `pydub` e `mediapipe`: extras citados no requirements, não instalados
  pela lista principal; pydub pode depender do executável ffmpeg.
- `av` (PyAV): fallback de decodificação MP3 no provider ElevenLabs, não garantido
  pelo requirements. Não confundir com a negociação de áudio PCM desse provider.
- Busca possui fallback que tenta o nome antigo `duckduckgo_search`.
- Existem `core/stt.py`, `core/tts.py`, `core/llm_client.py` e `core/installer.py`
  com comentários de versões antigas MARK XL. Seus imports opcionais incluem
  `vosk`, `torch`, `edge_tts` (pip `edge-tts`), `kokoro`, `miniaudio` e `soundfile`.
  Isso não significa que sejam usados no fluxo Gemini atual.
- `core/installer.py` contém instalação condicional desses motores antigos;
  `core/tts.py` também contém lógica de compatibilidade/upgrade Kokoro. Não chamar
  esses caminhos durante uma simples inspeção de imports.

Biblioteca padrão usada amplamente: `asyncio`, `threading`, `queue`, `subprocess`,
`pathlib`, `json`, `time`, `datetime`, `os`, `sys`, `platform`, `math`, `re`,
`importlib`, `inspect`, `dataclasses`, `typing`, `unittest` etc. Esses nomes não
devem virar dependências pip. Imports dentro de funções e imports dinâmicos também
contam; varredura estática não prova quais pacotes estão instalados ou ativos.

## 7. Dados, caminhos e assets

- Configuração central: `data_root()/config/api_keys.json`, via
  `core/config_store.py` e `memory/config_manager.py`. No Windows, `data_root()`
  é `%LOCALAPPDATA%/ULTRON`; testes podem definir `ULTRON_DATA_DIR` absoluto.
  O arquivo contém preferências e referências para um bloco de credenciais
  protegido com DPAPI do usuário. Nunca fazer `json.load`/`write_text` diretamente
  para acessar ou salvar configurações: usar `load_config`/`save_config`.
  Preservar campos existentes ao salvar. Não há fallback de segredos em texto simples.
- Memória pessoal: `data_root()/memory/long_term.json`, via `memory/memory_manager.py`.
- Spotify sem Client Secret usa PKCE. Tokens são salvos como `oauth_cache`
  protegido na configuração, sem arquivo de cache OAuth em texto simples.
- Certificados e perfil de navegador WhatsApp podem existir em `config/certs/`
  e `config/whatsapp_web/`; não são arquivos descartáveis de exemplo.
- Não incluir chaves, tokens, perfis de navegador ou memória pessoal em commits,
  logs, relatórios e testes. `.gitignore` documenta esses dados locais.
- Recursos instalados usam `resource_root()` ou caminhos relativos a `__file__`;
  dados graváveis usam `data_root()`. Preservar a separação no modo `sys.frozen`.
- `core/face_model.obj`, `config/jarvis.ico` e `dashboard/static/*` são assets;
  ausência de import Python não indica ausência de uso.
- `main.py` passa a string `face.png` para `JarvisUI`; esse arquivo não está na
  raiz desta inspeção. Verificar o consumidor e seus fallbacks antes de concluir
  que seja necessário baixar ou criar uma imagem.
- Logs e diagnósticos podem ser recriados. A UI atual escreve medições próprias
  em `data_root()/logs/d24_18_cached_dock_diagnostics.csv`; não confundir isso com os antigos
  protótipos D24 removidos.

## 8. Validação adequada e limites

Não importar `main`, `ui` ou executar `setup.py` só para testar sintaxe. Para
verificação estática sem importar a aplicação, usar `ast.parse` nos arquivos
alterados. `py_compile` também verifica sintaxe, mas cria bytecode em disco.

Testes WhatsApp existentes:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_whatsapp_desktop.py" -v
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_whatsapp_web.py" -v
```

Esses testes exercitam os caminhos com mocks; não comprovam envio real ou
compatibilidade com toda versão do WhatsApp. A validação manual está em
`docs/whatsapp-validation.md`. Não fazer envio real como efeito colateral de teste.

Existe `providers/_tests.py`, com runner próprio; ler os testes e seus requisitos
antes de executá-lo. Não pressupor que `pytest` ou um comando de build genérico
estejam configurados para todo o repositório.

O rascunho do instalador tem testes adicionais em
`tests/test_installation_foundation.py` (dados fictícios, mocks e Qt offscreen).
`tools/render_setup_preview.py` gera imagens sem importar `main.py` ou `ui.py`
e sem salvar configuração. O baseline empacotado ainda não inclui motores locais
opcionais; não executar pip usando o executável congelado. Ver `installer/README.md`
para limitações, build e validações ainda pendentes.

O Setup online usa `installer/Bootstrap.spec` e `installer/build-online.ps1`.
Seu Python privado permite instalar bibliotecas; isso não autoriza executar
`ULTRON-Setup.exe -m pip`. O bootstrap prepara setuptools/wheel no
próprio runtime e instala os requisitos com `--no-build-isolation`, pois a
distribuição embeddable não encontra o backend temporário usado pelo pip.
Preservar essa ordem e o log sanitizado `data_root()/logs/setup-install.log`. Manter o payload por allowlist e hashes. Não publicar
nem ligar consultas a um GitHub upstream presumido: configurar o repositório
do proprietário em `release_config.json`. O workflow produz rascunho de release.
O cartão de atualização não pode tomar foco nem bloquear a UI. O clique
explícito em Baixar e reiniciar autoriza download verificado e helper separado;
nunca baixar/executar sem esse clique. O usuário prefere preto puro e destaques vermelhos.

Mudanças visuais precisam de inspeção da UI; testes estáticos não comprovam
renderização, FPS, foco ou fluidez. Mudanças de áudio precisam de validação com
dispositivo e engine selecionados. Declarar o que foi realmente testado.

## 9. Estado local e limpeza já realizada

Esta cópia contém alterações locais de funcionalidades e interface; não é uma
cópia intacta do upstream. Antes de editar, conferir `git status` e `git diff`,
preservando alterações existentes que não pertencem à tarefa.

Por solicitação do usuário foram removidos backups aninhados/avulsos, `j.py`,
`prototypes.zip`, protótipos D18/D24 da raiz, o launcher demonstrativo D20O.1,
`test_crystal_standalone.py`, `test_d16_integration.py` e resultados antigos de
diagnósticos. Não recriar esses arquivos nem usá-los como dependências presumidas.
A pasta `prototypes/` permaneceu e ainda tem experimentos e assets próprios.

Antes de uma implementação: ler este contexto, os arquivos envolvidos, seus
chamadores e contratos; confirmar nomes reais e disponibilidade das dependências;
fazer a menor alteração coerente; validar os caminhos afetados. Não inferir
inutilidade de arquivo somente pela ausência de import explícito.

Atualizar este documento quando arquitetura, dependências ou pontos de entrada
mudarem. `requirements.txt` e o código atual têm precedência factual sobre esta
fotografia do projeto.


### Navegação do dock inferior

`BottomNavBar` emite `pageRequested` para páginas; não reenviar o clique oculto
nessa rota, pois Ajustes pode chamar `request_page` e causar recursão. Controles
usa o clique checkable sem pré-seleção; popups usam `popup_anchor` da célula
pintada e devem ficar acima do dock, dentro da janela. Os testes offscreen em
`tests/test_bottom_navigation.py` cobrem esses contratos sem iniciar o app.


### Atualizador com clique (0.1.1)

A consulta passa a repetir a cada cinco minutos enquanto o app está aberto.
`core/update_download.py` baixa o asset exato do repositório configurado e exige
SHA-256 informado pelo GitHub. O helper é o próprio Setup com `--apply-update`,
executado independentemente; só fecha o app após o helper confirmar prontidão.
O encerramento continua passando pelo CloseCoordinator, sem force kill.
`core/update_apply.py` aguarda o processo sair, adquire o lock, prepara runtime/app
em pasta irmã, mantém a instalação anterior e faz troca de pastas com recuperação
em falhas de promoção. Dados e credenciais externos não entram na troca.
O bootstrap pode recuperar uma interrupção entre renames ao executar novamente
um Setup normal. As pastas anteriores/de preparação são mantidas, exigindo espaço
extra; isso não implementa rollback automático de falhas após o HUD reabrir.
A UI do helper está em `ui_update_install.py`; não importar `main` para testá-la.
Versões antigas precisam receber esse suporte uma vez pelo Setup manual.


### Digitação do log por quadro (0.1.2)

`LogWidget.bind_hud_clock` compartilha `HudCanvas.pacedFrame`. O texto mantém
6 ms nominais por caractere com relógio monotônico, mas insere um lote por
quadro em uma única edição do documento e faz uma atualização de rolagem.
A pausa de 20 ms entre mensagens também usa esse relógio; não reintroduzir
um timer por letra. O sinal `entry_completed` continua emitindo texto, categoria
e HTML uma vez por mensagem para `ActivityPage`. Testes isolam o widget por AST
sem importar main/ui nem iniciar áudio. Menos alterações de documento não
comprovam ganho de FPS global; os painéis em perspectiva permanecem iguais.


### Confirmação e promoção Windows (0.1.3)

Download e execução agora são etapas distintas. `download_update` não cria
processos; `start_update` só é chamado após Reiniciar agora, revalida o hash e
cria uma tentativa independente. Depois mantém o app aberto e um botão discreto
permite retomar durante a sessão. O helper continua esperando a saída real.
A promoção mantém o diretório ULTRON no lugar e move somente app/runtime/exe,
com retry limitado e rollback por componente; o journal schema 2 recupera falhas
parciais e o schema antigo continua suportado. Não remover arquivos pessoais da
raiz nem modificar a instalação atual durante testes. Acumular melhorias locais;
somente gerar Setup/publicar quando o usuário autorizar explicitamente. A release
0.1.3 foi autorizada expressamente por corrigir a falha do atualizador.

### Cache dos painéis em perspectiva (melhoria local)

`PerspectiveSideView` mantém a imagem de saída supersampled e usa
`QGraphicsProxyWidget.ItemCoordinateCache` para reutilizar pixels dos widgets.
O DPR da imagem é 1,5: somente escalar o painter deixaria o cache nativo em 1×.
O cache do item respeita regiões nativas alteradas, mesmo quando a perspectiva
faz o Qt anunciar dano no proxy inteiro; a composição transformada ainda pode
cobrir todo o painel. Não afirmar atualização de apenas uma linha nem ganho de
FPS global sem medir. O sinal `scene.changed` encaminha dano ao viewport porque
o paintEvent customizado usa `scene.render`. A imagem de saída é recriada ao
mudar geometria/DPR/transformação e liberada no encerramento. A invalidação dos
pixels de widgets, incluindo tema, rolagem e seleção, continua a cargo do Qt.
`tests/test_perspective_rendering.py` exercita os widgets reais por AST/offscreen,
sem importar main/ui ou iniciar serviços, e compara a saída parcial com uma
composição completa usando o mesmo cache nativo. Cache de pixels pode alterar
antialiasing em relação ao render direto; revisar legibilidade também na UI real.
Essa melhoria não altera a digitação nem adiciona timers ou preparação no Setup.

### Repintura do HUD e diagnóstico de cadência (melhoria local)

`HudCanvas.paintEvent` sempre restaura os pixels solicitados pelo Qt. Somente
um quadro autorizado pela cadência, ou cache inválido, chama `_paint_frame`;
hover/expose usa a última QImage transparente, sem avançar animação ou contar
um novo quadro. O blit exclui a região dos filhos para preservar o botão FPS.
O cache considera tamanho, DPR, modelo e paleta; o timer compartilhado continua
único. A imagem usa pixels físicos para evitar perda de resolução em telas HiDPI.

`core/hud_diagnostics.py` mantém amostras limitadas e separa os alvos 47/60.
O relatório `data_root()/logs/hud-frame-diagnostics.csv` contém FPS de quadros
gerados, p50/p95/p99 dos intervalos, atrasos e slots perdidos, custo de render,
blit e pintura total, restaurações, memória do cache e RSS do processo. Não mede
apresentação física na tela/GPU. Usa o timer de relatório existente (5 s) e
aboutToQuit; não grava arquivos nem consulta RSS em paintEvent. Não prometer
cadência estável no app completo com base apenas em uma medição isolada.
`tests/test_hud_frame_cache.py` carrega a classe por AST e usa cristal/Qt reais,
sem main/ui, configuração pessoal ou áudio. `tools/benchmark_hud_rendering.py`
compara o caminho direto anterior com o cache em fixture offscreen e grava em
`tools/reports/hud-cache/`; aceita `--seconds` entre 1 e 30 por cenário.

### Ícones do aplicativo e do Setup (registro histórico; rever após mudanças)

Na inspeção anterior, o desenho indicado pelo usuário estava em `config/jarvis.png`; `jarvis.ico` era uma
conversão ICO real com tamanhos 16–256, preservando o PNG original. Não apenas
renomear PNG para ICO. O registro anterior indicava que `core/app_icon.py` aplicava o mesmo recurso ao app, launcher,
Setup e helper; no bootstrap procura também `payload/app/config/jarvis.ico`.
Na inspeção anterior, os specs e o Inno usavam esse ICO; o atalho criado pelo Setup online referencia
o ícone instalado em `app/config`. A separação posterior dos ícones do Setup e do aplicativo estava em andamento; conferir o diff atual antes de editar. Esses recursos só passam a um novo executável
ou instalador após um build expressamente autorizado. Não gerar Setup/publicar
como efeito colateral da mudança de asset.

### Conversa holográfica compacta (melhoria local)

`ui_chat.py` contém `HoloChat`/`ChatBubble`: o chat aprovado fica junto ao cristal
em telas amplas e usa o espaço inferior direito em janelas estreitas, sem cobrir
o cristal ou o rótulo de estado. É filho da página inicial, ancorado ao stack do
HUD, sem entrar no cache do HUD nem nos proxies em perspectiva. Não adicionar
timer para posicionamento/digitação. Mudanças de tamanho usam eventos do Qt;
ao mostrar câmera/vídeo, o chat é ocultado e seu histórico continua recebendo
mensagens. O painel tem até 280×240 pixels lógicos; recolher mantém o cabeçalho.

O Activity Log visível saiu da coluna direita, fazendo upload/entrada/controles
subirem ao topo. O `LogWidget` permanece oculto como fonte de digitação e da
página Atividade. `entry_started(text, category)` e
`entry_progress(visible_text, category, finished)` alimentam os balões usando
a mesma cadência de 6 ms/caractere em lotes por quadro. `entry_completed` e seu
HTML continuam emitindo uma vez por entrada. Somente Você/Ultron aparecem no
chat; SYS/Plugin/erros permanecem na Atividade. Não interpretar transcrição como
HTML nem criar uma segunda rota que duplique mensagens.

Respostas longas mostram até quatro linhas, com Ler mais/Ler menos dentro da
altura fixa e área rolável do painel. A prévia já recolhida é reutilizada durante
a digitação. O histórico visível é limitado a 100 mensagens; Atividade mantém
seu limite próprio. A rolagem segue o fim até o usuário subir/expandir um balão;
novas mensagens oferecem um botão para retomar. Testes funcionais ficam em
`tests/test_holo_chat.py`; `tools/render_chat_preview.py` monta componentes reais
por AST/Qt offscreen em duas larguras, sem main/ui, voz ou configuração pessoal.
O novo módulo integra a allowlist do payload; não gerar Setup como validação.

O chat se oculta após 4 segundos sem atividade. `HoloChat.bind_hud_clock` usa
o mesmo `HudCanvas.pacedFrame`, sem criar QTimer. Digitação ativa, fala do
assistente e cursor sobre o painel suspendem o prazo; eventos de interação dos
filhos (balões, scrollbar, Ler mais, minimizar) o renovam. Novas mensagens de
conversa reexibem o painel sem limpar o histórico; mensagens SYS não o reabrem.
Câmera/vídeo continuam respeitando a ocultação do chat. O estado LISTENING por
si só não conta como fala: ele também representa silêncio com o microfone ativo.

### Release 0.1.6 — CORE STATUS, painel de notícias retrátil e dock vetorial plano

Publicação autorizada pelo usuário. `ui_core_status.py` (`CoreStatusPanel`) fica no topo da coluna central da home e usa `HudCanvas.pacedFrame`, sem `QTimer` próprio. O seletor `47/60 FPS` foi movido para a página `MOTOR` e o texto `HUD xx.x/47 FPS` não é mais pintado no `HudCanvas`. `ui_news.py` (`NewsBriefingPanel`) apresenta o briefing e buscas `mode="news"` recolhido com 2 itens ou expandido com lista rolável. `ui_dock.py` (`FlatDock`) substitui a projeção curva por um dock vetorial plano em `BottomNavBar`, alinhado ao centro horizontal de `_hud_cam_stack` em modo janela e maximizado e preservando o cursor de clique sobre os ícones. `ui_core_status.py`, `ui_news.py` e `ui_dock.py` integram a allowlist de `installer/prepare_payload.py`.
