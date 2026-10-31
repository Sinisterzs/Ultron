<div align="center">

<img src="docs/assets/ultron-header.svg" alt="ULTRON — Personal AI System" width="100%">

**Assistente pessoal de IA para Windows.**  
Voz em tempo real, interface holográfica e automações para o desktop.

![Windows](https://img.shields.io/badge/Windows-111111?style=flat-square&logo=windows11&logoColor=ff304d)
![Python](https://img.shields.io/badge/Python-111111?style=flat-square&logo=python&logoColor=ff304d)
![PyQt6](https://img.shields.io/badge/PyQt6-111111?style=flat-square&logo=qt&logoColor=ff304d)
![Gemini](https://img.shields.io/badge/Gemini_Live-111111?style=flat-square&logo=googlegemini&logoColor=ff304d)

[**Download**](https://github.com/Sinisterzs/Ultron/releases) · [**Documentação**](docs/) · [**Código-fonte**](https://github.com/Sinisterzs/Ultron)

</div>

---

## Sobre

**ULTRON** é um assistente desktop desenvolvido em **Python/PyQt6**, baseado no [MARK LVI, de FatihMakes](https://github.com/FatihMakes/Mark-LVI). Combina conversação por voz, interface personalizável e integrações com ferramentas e serviços do Windows.

O projeto está em desenvolvimento. Algumas funções dependem de credenciais próprias, permissões do sistema e serviços externos.

## Funcionalidades

- **Voz e IA:** conversação com Gemini Live e suporte a push-to-talk.
- **Interface:** HUD holográfico, temas e animações.
- **Automações:** integração com sistema, arquivos, navegador e mídia.
- **Extensões:** plugins e integração opcional com Spotify via PKCE.
- **Memória:** persistência de informações e dashboard remoto.
- **Atualizações:** verificação de novas versões e download pelo aplicativo, com confirmação antes de reiniciar.

## Instalação

Baixe o **`ULTRON-Setup.exe`** na página de [Releases](https://github.com/Sinisterzs/Ultron/releases).

O instalador prepara um runtime Python privado e as dependências necessárias. **É preciso conexão com a internet**, mas não é necessário instalar Python manualmente. O navegador Chromium para automação web é opcional.

> **Estado atual:** o instalador ainda não tem assinatura digital. A instalação em um Windows limpo e o fluxo completo de atualização em outro computador ainda precisam de validação.

Cada usuário informa sua própria chave Gemini e, opcionalmente, configura o Spotify. As credenciais são protegidas pelo **Windows DPAPI** na conta local; não são distribuídas com o projeto. Memória e preferências permanecem na área de dados do usuário, fora da pasta de instalação.

**Atualizações:** instalações anteriores à versão `0.1.1` precisam executar uma vez o Setup mais recente para habilitar o atualizador. O processo mantém a instalação anterior durante a troca, portanto necessita de espaço temporário adicional.

## Executar pelo código

Requer **Windows** e **Python 3.11–3.13**:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe ultron_entry.py
```

Para preparar a automação web opcional:

```powershell
.\.venv\Scripts\python.exe -m playwright install chromium
```

Nunca publique suas chaves ou arquivos locais de configuração no GitHub.

## Desenvolvimento

```powershell
.\.venv\Scripts\python.exe -X utf8 -m unittest discover -s tests -p "test_*.py" -q
```

Os testes usam mocks e dados fictícios; não comprovam conectividade real com todos os serviços.

Mais informações: [AGENTS.md](AGENTS.md) · [Instalador](installer/README.md) · [Validação do instalador](installer/VALIDACAO.md) · [WhatsApp](docs/whatsapp-validation.md)

## Licença e créditos

Derivado do **[MARK LVI](https://github.com/FatihMakes/Mark-LVI)**, de **FatihMakes**. Mantida a licença original **[CC BY-NC 4.0](LICENSE)**, incluindo a atribuição e a restrição de uso comercial. A publicação do código não altera essas condições. O modelo facial MediaPipe mantém sua atribuição original, conforme os comentários do código e o projeto upstream.

---

<div align="center">
  <sub>ULTRON · PERSONAL AI SYSTEM</sub>
</div>
