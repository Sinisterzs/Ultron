# ULTRON × Codex — Biblioteca de prompts

> Prompts prontos para copiar no Codex Windows. Substitua os trechos entre `[COLCHETES]`. Os arquivos `AGENTS.md` já contêm as regras duradouras; estes prompts descrevem **a tarefa do momento**.

## Como escolher o modelo e o esforço de raciocínio

Recomendações práticas para o Codex Windows; **não são uma garantia de menor consumo de créditos**. A disponibilidade varia com a conta e a versão do aplicativo. Se um modelo não aparecer no seletor, use a alternativa indicada.

| Modelo | Quando usar | Esforço inicial |
|---|---|---|
| **GPT-6 Luna** | Textos curtos, documentação, tarefas repetitivas, pequenas edições | **Baixo** |
| **GPT-6.1 Terra** | Correções localizadas, interface de escopo pequeno, revisão objetiva | **Baixo** ou **Médio** |
| **GPT-6.1 Sol** | Implementação de features, refatoração, release, debugging e performance | **Médio** |
| **GPT-6 Astra** | Bugs difíceis, arquitetura crítica, problemas que outros modelos não resolveram | **Baixo** ou **Médio**, aumentando se necessário |

**Regra para gastar menos:** comece pelo modelo mais leve que consegue resolver a tarefa corretamente; suba de nível se faltar capacidade, não só porque o resultado ficou longo. Testes de build, leitura de muitos arquivos e tarefas multi-etapas também podem consumir mais uso. O preço de API por token **não é** uma conversão direta para créditos do Codex na assinatura.

### Seleção rápida por prompt

| Prompt | Modelo indicado | Esforço | Alternativa |
|---|---|---|---|
| 01 — Bug | **Terra** (simples) / **Sol** (complexo) | Baixo / Médio | Astra Médio se persistir |
| 02 — Refatoração | **Sol** | Médio | Astra Baixo para contratos críticos |
| 03 — Setup/release | **Sol** | Médio | Astra Baixo/Médio para falhas difíceis |
| 04 — README/changelog | **Luna** | Baixo | Terra Baixo |
| 05 — Performance | **Sol** | Médio | Astra Médio para concorrência complexa |
| 06 — Interface PyQt6 | **Terra** (localizada) / **Sol** (arquitetural) | Baixo / Médio | Astra Baixo se envolver múltiplos sistemas |
| 07 — Revisão de diff | **Terra** (pequeno) / **Sol** (grande) | Médio | Astra Médio para revisão de segurança crítica |
| 08 — Modo econômico | **Qualquer modelo** | Preferir Baixo inicialmente | Aplicar como complemento, não como modelo |
| 09 — Feature nova | **Sol** | Médio | Terra Baixo se for muito pequena; Astra Médio se crítica |

---

## Índice

1. Corrigir bug específico
2. Refatorar sem quebrar contratos
3. Continuar Setup/release interrompido
4. README + changelog
5. Análise de performance
6. Mudança visual de PyQt6
7. Revisão de diff antes de commit
8. Modo econômico (complemento opcional)
9. Criar feature com escopo definido

---

## 01 · Correção de bug

> **Modelo recomendado:** GPT-6.1 Terra · Baixo para bug isolado; GPT-6.1 Sol · Médio se envolver vários módulos. Se continuar difícil, GPT-6 Astra · Médio.


```text
Corrija o bug a seguir no Ultron: [DESCREVA SINTOMA E COMO REPRODUZIR].
Primeiro identifique a causa raiz no código atual. Consulte só arquivos, chamadores e testes relacionados. Preserve contratos e mudanças locais. Faça a menor correção robusta possível, adicione ou ajuste um teste relevante quando fizer sentido e execute validação dirigida. Não amplie escopo.
Ao final, diga causa raiz, arquivos alterados, testes/resultados e limitações.
```

## 02 · Refatoração limitada

> **Modelo recomendado:** GPT-6.1 Sol · Médio. Para alterações muito simples, Terra · Médio; para concorrência/contratos críticos, Astra · Baixo ou Médio.


```text
Refatore apenas [MÓDULO/ARQUIVOS] com objetivo de [META].
Preserve comportamento observável, APIs, concorrência, inicialização e compatibilidade com plugins/providers. Identifique duplicações ou complexidade real antes de editar. Não faça reescrita geral, novas dependências ou otimizações sem evidência. Valide com testes relacionados e resuma riscos restantes.
```

## 03 · Retomar Setup/release interrompido

> **Modelo recomendado:** GPT-6.1 Sol · Médio, para continuar o Setup interrompido sem refazer trabalho. Se houver falha arquitetural difícil, Astra · Baixo/Médio.


```text
Retome o trabalho interrompido no Setup/ícones/release do Ultron a partir do estado ATUAL do repositório. Antes de editar, verifique git status/diff, arquivos de installer e testes já executados ou registrados. A tarefa anterior relatou 164 testes aprovados, mas isso não comprova o estado atual: verifique apenas o que for necessário.
Separe claramente concluído, pendente e incerto. Preserve arquivos alterados ou não rastreados. Não refaça implementação concluída. Confirme no código se os ícones de aplicativo e Setup estão separados corretamente, valide o fluxo afetado com testes direcionados e indique pendências de build/instalação manual.
Não crie tag, push ou release; não execute instalador real nem gere artefato final sem autorização. Entregue resumo curto e objetivo.
```

## 04 · README + changelog

> **Modelo recomendado:** GPT-6 Luna · Baixo. Alternativa: GPT-6.1 Terra · Baixo.


```text
Atualize README e changelog do Ultron somente com fatos verificáveis no repositório e no histórico Git disponível. Preserve links válidos, explique requisitos/instalação, diferencie funções disponíveis de opcionais e planejadas. Não invente funcionalidades ou resultados. Não modifique código nem execute builds. Liste documentos alterados.
```

## 05 · Diagnóstico de performance

> **Modelo recomendado:** GPT-6.1 Sol · Médio. Para bugs complexos de Qt/asyncio ou travamentos difíceis de isolar, Astra · Médio.


```text
Investigue o desempenho de [COMPONENTE] no Ultron. Procure trabalho bloqueante no Qt, repaints/timers redundantes, alocações e importações custosas; respeite o pacing compartilhado e os caches existentes. Primeiro apresente hipóteses suportadas por código/medições. Faça apenas otimizações proporcionais e compare antes/depois quando for possível. Não afirme ganho de FPS global por teste offscreen isolado. Rode validações pertinentes.
```

## 06 · Interface PyQt6

> **Modelo recomendado:** GPT-6.1 Terra · Baixo/Médio para layout e ajustes pontuais; GPT-6.1 Sol · Médio para animações, cache e integrações complexas.


```text
Implemente este ajuste visual: [DESCRIÇÃO]. Área: [COMPONENTE].
Mantenha o design atual do Ultron (preto e vermelho, quando aplicável), responsividade, foco e interações existentes. Preserve thread Qt, animações/timers compartilhados e hierarquia de widgets. Inspecione o componente afetado; use preview/offscreen se houver ferramenta isolada e diga o que ainda precisa ser verificado visualmente no aplicativo real. Não altere módulos não relacionados.
```

## 07 · Revisão antes do commit

> **Modelo recomendado:** GPT-6.1 Terra · Médio para diff pequeno; GPT-6.1 Sol · Médio para mudanças amplas. Astra · Médio para revisão crítica de segurança.


```text
Revise o diff atual relacionado a [TAREFA], sem alterar nada. Verifique regressões, compatibilidade, dados sensíveis, arquivos gerados indevidos e testes ausentes. Priorize achados com evidência e arquivo/linha. Se não houver problemas relevantes, diga isso e aponte limitações da revisão. Sugira mensagem de commit em português; não faça commit/push.
```

## 08 · Complemento econômico

> **Modelo recomendado:** Funciona com qualquer modelo. Prefira esforço Baixo para tarefas simples, subindo quando a complexidade exigir.


```text
Modo econômico: use leituras e testes direcionados, evite comandos redundantes e relatórios longos durante a execução. Preserve todas as validações necessárias. Termine ao concluir o escopo; resumo final conciso com evidências. Não peça confirmação para cada edição pequena e reversível, mas respeite autorizações de segurança, publicação e ações destrutivas.
```

## 09 · Feature nova

> **Modelo recomendado:** GPT-6.1 Sol · Médio. Terra · Baixo para feature pequena e isolada; Astra · Médio para design complexo/risco alto.


```text
Implemente [FUNCIONALIDADE] em [ÁREA] com estes critérios de aceite: [CRITÉRIOS].
Antes de editar, identifique contratos e componentes reutilizáveis. Proponha plano breve apenas se cruzar múltiplos módulos ou envolver risco. Implemente por mudanças coesas, preserve compatibilidade e inclua testes proporcionais. Não adicione dependências nem integração externa sem necessidade. Ao final, indique o que foi feito, evidência de teste e pontos que exigem validação manual.
```

---

### Dicas rápidas

- Um pedido concreto costuma funcionar melhor que pedir “melhora tudo”.
- Não transforme cada execução em três conversas obrigatórias: uma tarefa bem delimitada pode ser investigada, editada e testada em um só turno.
- Mais prompts não garantem menos créditos; a economia real depende do modelo, contexto e ferramentas executadas.
- Para uma tarefa interrompida, comece pelo prompt 03 e confira o diff.

### Fontes para escolha dos modelos (consultadas em 30/10/2026)

- [OpenAI — Model selection](https://developers.openai.com/api/docs/guides/model-selection)
- [OpenAI — Como gerenciar o uso do GPT-6 Astra no Work e Codex](https://help.openai.com/pt-br/articles/20001516-managing-usage-with-gpt-6-astra-in-work-and-codex)

As recomendações são para orientar a seleção manual no Codex: este arquivo Markdown não troca o modelo automaticamente.
