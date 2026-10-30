# ULTRON

Assistente pessoal desktop em Python/PyQt6, baseado no [MARK LVI de FatihMakes](https://github.com/FatihMakes/Mark-LVI), com interface personalizada e um instalador online para Windows x64.

## Baixar e instalar

Baixe **ULTRON-Setup.exe** em [Releases](https://github.com/Sinisterzs/Ultron/releases).
As versões atuais são publicadas como releases normais. O executável ainda não
tem assinatura digital; a instalação completa em Windows limpo permanece pendente.

O Setup tem interface preta e vermelha e pede sua configuração inicial. Na etapa
final, baixa um runtime Python privado e instala as bibliotecas necessárias.
Você precisa de internet; não precisa instalar Python manualmente no PC de destino.
Chromium para automação web é um download opcional explícito.

Nenhuma chave pessoal acompanha o projeto ou o Setup. Cada pessoa informa sua
própria chave Gemini e, se desejar, configura o Spotify. As credenciais são salvas
somente após a preparação, protegidas pelo Windows DPAPI para a conta local.
Preferências e memória ficam fora da pasta instalada, na área de dados do usuário.

Versões anteriores à 0.1.1 precisam receber o novo Setup manualmente uma vez
para habilitar o atualizador. Nas atualizações futuras, não é preciso repetir
o wizard de credenciais. A instalação anterior é mantida; é necessário espaço
para duas instalações. A atualização completa entre versões em outro PC ainda
precisa ser validada.

## Recursos

- Conversação por voz com Gemini Live, interface holográfica e temas.
- Áudio, push-to-talk e integrações de sistema, arquivos, busca, navegador e mídia.
- Spotify com autorização no navegador via PKCE, sujeito às regras da API Spotify.
- Memória persistente e dashboard remoto.
- Aviso discreto de nova versão, com consulta periódica enquanto o app está aberto.
- Clique em Baixar atualização: download verificado no próprio app. Ao concluir,
  escolha Reiniciar agora ou Depois. A aplicação só fecha após a confirmação.
- O helper mantém a pasta principal no lugar e promove app/runtime/launcher,
  com restauração em falhas e reabertura pelo launcher.

A disponibilidade depende de credenciais, hardware, permissões e serviços externos.
O launcher continua sendo a entrada e inicia a aplicação principal em outro processo.

## Executar pelo código

Use Python 3.11–3.13 em um ambiente próprio:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe ultron_entry.py
```

Para usar automação web pelo código, prepare também os navegadores Playwright:

```powershell
.\.venv\Scripts\python.exe -m playwright install chromium
```

As chaves e demais dados locais não devem ser commitados. O arquivo `.gitignore`
contém as exclusões conhecidas, mas não substitui revisão dos arquivos antes de publicar.

## Desenvolvimento, testes e build

- [Contexto para agentes e desenvolvedores](AGENTS.md)
- [Instalador: build, armazenamento e limitações](installer/README.md)
- [Validação da prévia](installer/VALIDACAO.md)
- [Validação WhatsApp](docs/whatsapp-validation.md)

```powershell
.\.venv\Scripts\python.exe -X utf8 -m unittest discover -s tests -p "test_*.py" -q
```

Os testes usam dados fictícios e mocks; não comprovam conectividade real de todos
os serviços. O build do Setup pode ser gerado localmente ou pelo workflow de
Windows. Enviar uma tag cria um rascunho de release quando ele ainda não existe.

## Licença e créditos

Projeto derivado do MARK LVI de **FatihMakes**. A licença original **CC BY-NC 4.0**
é preservada em [LICENSE](LICENSE), incluindo atribuição e restrição de uso comercial.
Publicar o código neste repositório não muda essas condições. O modelo de face
MediaPipe mantém sua atribuição original; veja os comentários no código e o projeto upstream.
