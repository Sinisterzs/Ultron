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


## Limpeza temporária — 30/10/2026 (preview.3)

Após o aviso de remoção no Windows, a pasta temporária inspecionada continha
somente `PyQt6/Qt6/plugins/styles/qmodernwindowsstyle.dll`. O bootstrap usa
Fusion explicitamente: o plugin nativo não utilizado foi retirado do pacote.
Ao abrir o runtime instalado, o bootstrap também retira caminhos Qt herdados,
remove entradas do bundle do PATH e restaura temporariamente a busca de DLLs
do Windows. Isso evita que o processo independente retenha recursos do Setup.
Dois testes novos verificam o ambiente do filho e a restauração após falha.
A suíte agora tem 110 testes. A reprodução no PC do destinatário ainda precisa
ser confirmada; não se deve atribuir todo bloqueio de arquivo à mesma causa.


## Navegação — 30/10/2026 (0.1.0)

Ajustes recursava porque o clique de compatibilidade chamava request_page(),
que reenviava o mesmo clique. As páginas agora emitem somente pageRequested.
Controles agora deixa o botão checkable alternar o próprio estado, sem selecionar
antes do clique, e o painel usa a posição real da célula no dock inferior.
A navegação para outra página fecha o painel de controles.

Três regressões exercitam cliques Qt offscreen: Ajustes sem recursão, Controles
abrindo/fechando e geometria em três tamanhos. O método real de posicionamento é
extraído por AST sem importar a aplicação principal. Inspeção visual usa um painel
representativo: não comprova todos os controles reais nem serviços de voz.
A suíte total tem 113 testes. Publicação normal solicitada pelo proprietário;
a validação completa em Windows limpo continua pendente.
