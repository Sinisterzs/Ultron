# Instalação do kit no Codex para Windows

## Estrutura

```text
Ultron/                     ← raiz do repositório Git
├── AGENTS.md               ← substitui o atual após fazer backup/revisar diff
├── PROMPTS_CODEX.md        ← biblioteca de prompts; não é carregada automaticamente
├── core/
│   └── AGENTS.md
├── installer/
│   └── AGENTS.md
└── tests/
    └── AGENTS.md
```

## Aplicar

1. Feche ou encerre a sessão atual do Codex; faça backup do `AGENTS.md` atual e preserve quaisquer alterações locais.
2. Extraia este ZIP e copie os arquivos mantendo a estrutura **dentro da raiz do repositório Ultron**, onde fica a pasta `.git`.
3. Confira no VS Code/Explorer que `core/AGENTS.md`, `installer/AGENTS.md` e `tests/AGENTS.md` estão realmente dentro dessas pastas. Não crie uma pasta extra `ULTRON_Codex_Kit` dentro do repositório.
4. Abra o projeto Ultron no aplicativo Codex para Windows e inicie **uma nova sessão** apontada para a raiz do repositório.
5. Pergunte ao Codex: `Diga quais instruções do AGENTS.md da raiz estão ativas e resuma a política operacional. Não modifique arquivos.`
6. Quando pedir alterações em `installer/`, `core/` ou `tests/`, peça também para ele conferir o `AGENTS.md` correspondente. Para conferir a descoberta automática de instruções aninhadas, inicie uma sessão cujo diretório de trabalho seja a subpasta pertinente.

## Como a descoberta funciona

O Codex procura orientações globais em `~/.codex/AGENTS.md` e, para o projeto, combina as instruções da raiz do repositório com as pastas **no caminho até o diretório de trabalho da sessão**. Um `AGENTS.override.md` no mesmo diretório tem precedência sobre `AGENTS.md`. Arquivos de subpastas fora do caminho de descoberta não precisam estar pré-carregados em uma sessão iniciada na raiz: por isso o `AGENTS.md` principal pede que sejam consultados ao trabalhar em áreas específicas.

Existe um limite padrão de 32 KiB para o conjunto de instruções de projeto carregadas no início da sessão. Este kit mantém a raiz abaixo desse limite, mas o total pode excedê-lo quando incluir instruções aninhadas. Para verificar truncamento, peça uma lista de fontes ao Codex; se necessário, reduza o texto ou configure `project_doc_max_bytes` em `~/.codex/config.toml`, respeitando o tamanho dos arquivos e a documentação da sua versão.

## Comandos úteis no PowerShell

```powershell
# Na raiz do repositório
 git status --short
 git diff -- AGENTS.md
 git add AGENTS.md core/AGENTS.md installer/AGENTS.md tests/AGENTS.md PROMPTS_CODEX.md
 git commit -m "docs: organiza instrucoes do Codex e prompts do Ultron"
```

Apenas faça commit quando revisar o diff. `PROMPTS_CODEX.md` é um catálogo para copiar manualmente; não vira regra automática só por existir.

## Verificação sugerida

No Codex: `Sem editar arquivos, indique o arquivo AGENTS.md principal, quais instruções específicas de installer se aplicariam ao Setup e quais operações exigem minha autorização.`

Referência de descoberta e configuração: https://learn.chatgpt.com/docs/agent-configuration/agents-md
