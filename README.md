<div align="center">

# U L T R O N

**INTELLIGENT DESKTOP SYSTEM**

Um assistente de IA para Windows, com interface holográfica, interação por voz e automação de tarefas.

[**Download para Windows**](https://github.com/Sinisterzs/Ultron/releases) · [**Documentação**](#documentação-e-desenvolvimento) · [**Código-fonte**](https://github.com/Sinisterzs/Ultron)

![Python](https://img.shields.io/badge/Python-3.11--3.13-151515?style=flat-square&logo=python&logoColor=white)
![PyQt6](https://img.shields.io/badge/Interface-PyQt6-151515?style=flat-square)
![Windows](https://img.shields.io/badge/Plataforma-Windows_x64-151515?style=flat-square&logo=windows&logoColor=white)
![Status](https://img.shields.io/badge/Status-Em_desenvolvimento-631c2b?style=flat-square)

</div>

---

## Uma interface para conversar e agir

O **ULTRON** é um assistente pessoal desktop, desenvolvido em **Python e PyQt6**, que combina conversação com IA, comandos de voz, integrações com serviços e ferramentas de automação em uma experiência visual própria.

Sua interface utiliza uma identidade escura e vermelha, com elementos holográficos, um núcleo visual reativo e navegação integrada. O objetivo do projeto é evoluir de um assistente que responde perguntas para um sistema capaz de auxiliar em tarefas reais no computador, com controle do usuário sobre ações sensíveis.

> **Projeto em desenvolvimento.** Recursos e integrações dependem de configuração, permissões, hardware e serviços externos. Nem todos os fluxos foram validados em uma instalação limpa do Windows.

<!-- Quando houver uma captura oficial do aplicativo no repositório, adicione-a aqui.
Exemplo: ![Interface do ULTRON](docs/assets/ultron-interface.png)
Não aponte para um arquivo que ainda não existe. -->

## Recursos

| Sistema | O que oferece |
| --- | --- |
| **IA e voz** | Conversação por voz com Gemini Live e suporte a push-to-talk. |
| **Interface holográfica** | HUD em PyQt6, visualização reativa e opções de personalização visual. |
| **Automação desktop** | Ferramentas para tarefas de sistema, arquivos, navegador e mídia, conforme permissões e disponibilidade. |
| **Integrações** | Spotify com fluxo de autorização PKCE e outras funcionalidades configuráveis. |
| **Memória** | Armazenamento persistente de informações e preferências do assistente. |
| **Dashboard** | Interface remota para recursos compatíveis. |
| **Atualizações** | Aviso de versão disponível, download verificado e opção de reiniciar quando o usuário decidir. |

## Download e instalação

### Windows x64

Acesse a página de [**Releases**](https://github.com/Sinisterzs/Ultron/releases) e baixe o instalador **`ULTRON-Setup.exe`** da versão desejada.

O instalador apresenta a configuração inicial e prepara um runtime Python privado com as dependências do aplicativo. **Não é necessário instalar Python manualmente** para usar o Setup; é necessária conexão com a internet.

O Chromium utilizado pela automação web é um download opcional, solicitado separadamente.

**Antes de instalar:**

- O instalador ainda **não possui assinatura digital**.
- A instalação completa em um Windows limpo ainda precisa ser validada.
- Cada usuário deve fornecer sua própria chave de API Gemini; integrações como Spotify são opcionais.
- Nenhuma credencial pessoal é distribuída com o projeto.

### Dados e atualizações

As credenciais são armazenadas após a preparação e protegidas pelo **Windows DPAPI**, vinculadas à conta local. As preferências e a memória ficam na área de dados do usuário, fora da pasta de instalação.

O aplicativo verifica a disponibilidade de atualizações enquanto está aberto. Após o download, o usuário escolhe **Reiniciar agora** ou **Depois**. O processo de atualização preserva a instalação anterior para possibilitar restauração em caso de falha.

> **Compatibilidade de atualização:** versões anteriores à **0.1.1** exigem instalar manualmente uma vez o Setup mais recente para habilitar o atualizador atual. A atualização completa entre versões em outro computador ainda precisa de validação, e o procedimento exige espaço para duas instalações.

## Executar pelo código-fonte

Use **Python 3.11 a 3.13** no Windows e execute na raiz do repositório:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe ultron_entry.py
```

Para habilitar a automação web, instale os navegadores do Playwright:

```powershell
.\.venv\Scripts\python.exe -m playwright install chromium
```

As credenciais e outros dados privados devem permanecer fora do controle de versão. O `.gitignore` contém exclusões conhecidas, mas é importante revisar os arquivos antes de publicar alterações.

## Arquitetura e desenvolvimento

O ULTRON combina uma aplicação desktop em PyQt6 com módulos para voz, modelos de IA, automação, memória e integrações. O **launcher** atua como ponto de entrada e inicia a aplicação principal em outro processo.

```text
Ultron/
├── actions/       # Ações e automações
├── core/          # Componentes centrais
├── dashboard/     # Interface de dashboard
├── installer/     # Instalador e atualização
├── memory/        # Persistência e configuração
├── plugins/       # Extensões
├── providers/     # Serviços e modelos
├── tests/         # Testes automatizados
├── tools/         # Ferramentas de desenvolvimento
├── launcher.py    # Inicialização
├── main.py        # Aplicação principal
├── ui.py          # Interface desktop
└── ui_sidebar.py  # Componentes de navegação
```

### Testes

```powershell
.\.venv\Scripts\python.exe -X utf8 -m unittest discover -s tests -p "test_*.py" -q
```

Os testes automatizados incluem dados fictícios e mocks. **Resultados positivos não garantem conectividade real** com todos os serviços externos nem a ausência de falhas em todas as máquinas.

### Documentação e desenvolvimento

- [AGENTS.md](AGENTS.md) — contexto técnico e orientações para agentes e desenvolvedores.
- [Instalador](installer/README.md) — build, armazenamento e limitações.
- [Validação do instalador](installer/VALIDACAO.md) — verificações da prévia.
- [Validação de WhatsApp](docs/whatsapp-validation.md) — escopo e verificações da integração.

O build do Setup pode ser realizado localmente ou pelo workflow de Windows. O envio de uma tag pode criar um rascunho de release quando ainda não houver um.

## Estado do projeto

O ULTRON está em desenvolvimento ativo. As prioridades incluem melhorar a estabilidade, ampliar as automações, refinar a experiência de voz e validar os processos de instalação e atualização em diferentes ambientes.

Para acompanhar novas versões, consulte as [Releases](https://github.com/Sinisterzs/Ultron/releases).

## Origem, licença e créditos

O ULTRON é derivado do projeto [**MARK LVI**, de FatihMakes](https://github.com/FatihMakes/Mark-LVI).

A licença original **Creative Commons Attribution–NonCommercial 4.0 (CC BY-NC 4.0)** é preservada em [LICENSE](LICENSE), incluindo os requisitos de atribuição e as **restrições de uso comercial**. A publicação deste repositório não altera esses termos.

O modelo de face **MediaPipe** mantém sua atribuição original, conforme as referências no código e no projeto de origem.

---

<div align="center">

**ULTRON** · *Built to evolve.*

</div>
