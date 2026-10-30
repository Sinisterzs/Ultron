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


## Atualização por clique — 30/10/2026 (0.1.1)

Corrigida a consulta única no boot e a espera anterior de até 24 horas. Há timer
de cinco minutos, sem requisições sobrepostas. Adicionados download com asset e
hash vinculados ao repositório, cancelamento, handshake e espera do processo,
staging em pasta irmã, lock, promoção com restauração em erro e recuperação do
intervalo entre renames. O clique conserva o encerramento existente e o launcher.

Os testes usam pastas temporárias, fixtures, rede simulada e um processo Windows
real que encerra sozinho. Exercitam falha de staging/promoção, recuperação,
cancelamento, adulteração, falta de confirmação e emissão Qt somente por clique.
O smoke do executável exercita troca real de pastas fictícias sem usar o app
instalado. Ainda não houve uma atualização completa entre releases em VM limpa,
nem validação de falhas de energia ou rollback após falha do HUD. Isso deve ser
confirmado antes de assumir compatibilidade com todos os PCs.

Resultado local final desta implementação: 126 testes passaram e o executável
verificou 97 arquivos de payload, incluindo a troca da fixture e a prévia do helper.


## Digitação agrupada — 30/10/2026 (0.1.2)

Somente o LogWidget foi alterado: usa o relógio já existente do HUD e calcula
lotes pelo tempo monotônico, preservando a taxa nominal de 6 ms por caractere.
Sem mudanças no renderer em perspectiva, cristal ou efeitos da barra.

Seis regressões Qt verificam taxa a 47/60 FPS, uma alteração por quadro,
recuperação após atraso, fila/pausa, HTML do histórico, Unicode, ociosidade e
conexão única do relógio. Na comparação controlada de 1.508 caracteres, o
código anterior fez 1.509 alterações do documento; o novo fez 426 a 47 FPS
(-71,8%) e 543 a 60 FPS (-64,0%), com a mesma duração nominal de 9,048 s.
A prévia isolada foi inspecionada. Esses números não medem o FPS do app inteiro;
a percepção em fala/mensagens reais precisa ser confirmada na instalação.

Também foi construída a MainWindow real em Qt offscreen com perfil fictício,
rede e subprocessos bloqueados e serviços opcionais de boot desativados. O
texto percorreu o sinal pacedFrame real e chegou ao histórico de Atividade.
O teste não importou main nem iniciou voz; a janela renderizada foi inspecionada.
