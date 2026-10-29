# Validação da correção — 29/10/2026

## Causa e mudança

A primeira prévia falhava ao preparar PyAutoGUI com `BackendUnavailable: Cannot
import setuptools.build_meta`. O runtime Python embeddable não acessava o backend
criado no ambiente temporário de build do pip. A correção instala setuptools/wheel
no runtime privado e utiliza `--no-build-isolation` para preparar os requisitos.
Não foi necessário alterar o Python original do computador.

O instalador agora registra a saída sanitizada de cada etapa em
`data_root()/logs/setup-install.log`. Após uma falha, há um botão para abrir esse
registro. Uma falha de backend não é mais apresentada como problema de conexão.

## Verificação real realizada

- Erro original reproduzido com o mesmo runtime privado da prévia.
- PyAutoGUI e suas dependências de fonte preparadas e instaladas com a correção.
- PyAutoGUI recompilado novamente com cache desabilitado, evitando falso sucesso por wheel já existente.
- Todos os requisitos do projeto instalados com sucesso no runtime privado Python 3.13.
- Imports reais de NumPy, sounddevice, Spotify, FastAPI, PyAutoGUI, QtWidgets e Gemini passaram.
- Sem início do assistente, captura de áudio ou acesso a contas/credenciais reais.

O Setup corrigido abriu em modo de teste, verificou os 94 arquivos embutidos
e passou pelos 108 testes locais. Esses checks foram executados por
`installer/verify_build.ps1`. O SHA-256 do Setup acompanha o binário gerado.

## Limites

Essa validação foi feita em um runtime isolado neste computador, não em uma VM
Windows limpa. Conexões reais Gemini/Spotify, automação web, desinstalação,
assinatura digital e auditoria completa do histórico continuam fora da verificação.
As prévias usam dados fictícios. A atualização automática permanece adiada;
o aviso de versão abre a página do release em Sinisterzs/Ultron.
