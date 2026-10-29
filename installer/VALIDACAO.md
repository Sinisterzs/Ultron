# Validação do rascunho — 29/10/2026

- Artefato: `dist/ULTRON-Setup.exe`, Windows x64, 37.612.716 bytes.
- SHA-256 disponível em `dist/ULTRON-Setup.exe.sha256`.
- 105 testes locais passaram (armazenamento, caminhos, Qt, preparação, releases e regressões WhatsApp com mocks).
- O executável abriu o wizard em modo offscreen e verificou os hashes de 94 arquivos do payload.
- Esse teste não instalou o aplicativo, não usou a rede, não criou configuração e não iniciou o assistente.
- O runtime privado Python e o bootstrap pip foram baixados separadamente em `.installer-checks/`, com os hashes fixos conferidos; o pip iniciou nesse runtime.
- As prévias mostram dados fictícios. A barra na imagem de preparação é uma demonstração visual; o fluxo real usa bytes recebidos ou estado indeterminado.
- Release configurado para `Sinisterzs/Ultron`. Não houve push, criação de release ou publicação no GitHub.
- Atualizações mantêm o aviso discreto e o link para GitHub. O atualizador automático foi adiado por decisão do usuário.
- A falha de abertura do primeiro build foi corrigida removendo a ICU incompatível capturada do PATH do Poppler e harmonizando o runtime C++ do Qt.

## Ainda não validado

Instalação completa em Windows limpo, resolução de todas as bibliotecas no runtime
de destino, conexões reais Gemini/Spotify, áudio, automação web, desinstalação,
upgrade transacional, assinatura digital e auditoria completa de segredos no
conteúdo/histórico do repositório. Este é um Setup de testes, não uma certificação
de prontidão para distribuição pública.
