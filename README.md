# ABYSS

**Inteligência além da superfície.**

Ferramenta Python de OSINT comercial da Polypus IT Solutions. Organiza buscas sobre empresas e unidades, preserva fontes e exporta evidências para revisão humana. Não envia mensagens, propostas, candidaturas ou formulários.

## Versão 0.2.0

- Plano de pesquisa em nove dimensões: institucional, decisores, compras, tecnologia, projetos, pessoas, vagas, documentos e notícias.
- Localidade, aliases e múltiplos domínios oficiais informados pelo operador.
- Buscas corporativas adicionais sem filtro local para encontrar compradores centralizados.
- Adaptadores Brave Search API e SearXNG, com limite explícito de consultas e intervalo entre elas.
- Modo manual sem rede e importação de referências JSON.
- Deduplicação por URL mantendo diferentes trechos e consultas de origem.
- JSON, CSV, relatório TXT, links de pesquisa e hashes SHA-256 dos arquivos exportados.
- Falhas de provedores registradas; interrompe o lote quando ocorre erro, preservando resultados anteriores.
- Interface leve no terminal: nova pesquisa, abrir pesquisa salva, paginação, filtros, detalhes e auditoria de consultas.
- Exportação PDF paginada e Excel `.xlsx` com abas Resumo, Fontes, Consultas e Plano.

Esta versão coleta resultados e trechos dos buscadores; **não faz leitura integral automática das páginas ou PDFs de origem, nem confirma cargos atuais**. Não extrai contatos de áreas autenticadas, não infere e-mails e não verifica autoridade de contratação. Referências importadas continuam identificadas como importação. Não depende de IA e não promete cobertura exaustiva.

## Executar sem instalação

Requer Python 3.10 ou superior. Usa somente a biblioteca padrão.

```bash
python3 abyss.py --ui
```

Executar `python3 abyss.py` em um terminal interativo também abre o menu. Use `Nova pesquisa` para escolher alvo, unidade, domínios, aliases e provedor. Ao concluir, a interface mostra as fontes e permite filtrar, consultar detalhes e exportar. No modo manual sem importação, há apenas um plano, sem resultados coletados. `Abrir pesquisa salva` recebe a pasta ou o caminho de `research.json`.

Os parâmetros de linha de comando continuam disponíveis:

```bash
python3 abyss.py --company "Empresa Exemplo" --location "Anápolis GO" --domain example.com
```

O modo padrão é `manual`: cria o plano e links de pesquisa, sem consultas de rede. A saída vai para uma pasta nova em `output/`. Pastas existentes não são sobrescritas.

```bash
python3 abyss.py --company "Empresa Exemplo" --domain example.com \
  --import-json examples/reference.json --output output/demonstracao
```

O exemplo é fictício. Uma referência possui `title`, `url`, `snippet`, `category`, `query` e, opcionalmente, `published_date`. Consulte `examples/reference.json`.

## Exportar PDF e Excel

Pelo menu de resultados, escolha PDF, Excel ou ambos. Também é possível exportar sem abrir o menu:

```bash
python3 abyss.py --open output/demonstracao --export pdf xlsx
```

Para exportar ao final de uma pesquisa, acrescente `--export pdf xlsx` ao comando de busca. Cada exportação cria uma subpasta `export-*`, preservando arquivos anteriores, pesquisa JSON e seu manifesto. Um novo manifesto associa os relatórios ao hash do JSON original.

Excel usa o formato atual `.xlsx`, e não o binário legado `.xls`. Há cabeçalhos congelados, filtros e células de texto para impedir que trechos sejam interpretados como fórmulas. Células acima de 32.767 caracteres são truncadas apenas no Excel; o JSON preserva o conteúdo completo. O PDF A4 inclui evidências, URLs, origem, datas, erros e plano de pesquisa; sua fonte padrão suporta português/WinAnsi. Para outros alfabetos e símbolos, use Excel ou JSON, que preservam Unicode. Nenhum exportador exige instalação adicional.

## Busca automática

**Brave:** requer chave e plano contratado diretamente com o provedor. Não há chave incluída. As chamadas podem consumir sua cota ou gerar custos conforme o contrato. Defina `BRAVE_API_KEY` no ambiente, fora do repositório.

```bash
python3 abyss.py --company "Empresa Exemplo" --location "Anápolis GO" \
  --domain example.com --provider brave --max-queries 20 --count 10
```

**SearXNG:** requer uma instância existente com saída JSON habilitada. A aplicação não instala servidor nem escolhe instâncias públicas automaticamente.

```bash
python3 abyss.py --company "Empresa Exemplo" --provider searxng \
  --searxng-url http://localhost:8080 --max-queries 20
```

A busca usa requisições GET aos provedores configurados. O nome do alvo e os termos são enviados ao buscador, como em qualquer pesquisa; não são enviados ao alvo por mensagens ou formulários. Não há módulo de outreach, cadastro ou interação autenticada.

## Evidências e limites

`research.json` preserva consulta, provedor, horário de coleta, data de publicação informada pelo provedor, trecho e tipo de fonte. O horário de coleta não é a data do evento. Classificar um domínio como oficial depende da configuração do operador e não valida automaticamente sua propriedade.

Resultados de perfis podem estar desatualizados ou incluir publicações de terceiros. Não existe extração automática de organograma, aprovação de fatos, pontuação comercial ou conclusão de demanda. A validação da página original é uma etapa humana nesta versão.

`sources.csv` protege células que poderiam ser interpretadas como fórmulas por planilhas. Saídas, credenciais e dados de pesquisas não são versionados. Os hashes permitem verificar a integridade dos arquivos exportados, não autenticam o conteúdo do buscador.

## Verificação

```bash
python3 -m unittest discover -s tests -v
```

Testes de provedores usam respostas simuladas. Uma execução manual demonstra exportação e integridade; isso não comprova conectividade real de Brave/SearXNG.

## Desenvolvimento previsto

Leitura de páginas públicas e PDFs, rastreamento limitado a domínios selecionados, coleta de canais institucionais publicados, correlação de entidades, revisão de conflitos entre fontes e monitoramento incremental. Esses recursos ainda não estão implementados na versão 0.2.0.

## Uso e contribuições

Software proprietário, com licença de uso limitada descrita em [LICENSE](LICENSE). Não é software de código aberto. Contribuições externas não são aceitas; consulte [CONTRIBUTING.md](CONTRIBUTING.md).

Documentação dos provedores: [Brave Search](https://api-dashboard.search.brave.com/api-reference/web/search/get), [SearXNG](https://docs.searxng.org/dev/search_api.html).
