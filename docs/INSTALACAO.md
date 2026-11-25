# Instalar e atualizar o ABYSS

O ABYSS funciona no Windows, macOS e Linux com **Python 3.10 ou superior e Git**. Não precisa de `pip install`, banco de dados, Docker ou bibliotecas externas. Brave e SearXNG são alternativas para realizar buscas automáticas, não requisitos para abrir o programa ou analisar arquivos já salvos.

## 1. Instalar os requisitos

### Windows

Instale [Python](https://www.python.org/downloads/windows/) e [Git](https://git-scm.com/downloads/win). No instalador do Python, habilite o launcher e a opção de adicionar Python ao PATH. Feche e abra novamente o PowerShell.

```powershell
py -3 --version
git --version
```

Se `py` não estiver disponível, tente `python --version`. Use `python` no lugar de `py -3` nos comandos abaixo, desde que a versão seja 3.10 ou superior.

### macOS

Instale [Python para macOS](https://www.python.org/downloads/macos/) e [Git](https://git-scm.com/downloads/mac), caso ainda não estejam disponíveis.

```bash
python3 --version
git --version
```

### Ubuntu / Debian

```bash
sudo apt update
sudo apt install python3 git
python3 --version
git --version
```

O Python deve ser 3.10 ou superior. Em outras distribuições, instale Python e Git pelo gerenciador de pacotes correspondente.

## 2. Baixar o projeto com Git

No terminal, escolha a pasta onde deseja instalar e execute:

```bash
git clone https://github.com/mister-m-1337/abyss.git
cd abyss
```

O repositório é público, portanto não é necessário cadastrar token de GitHub para cloná-lo por HTTPS ou consultar releases públicas.

**Use o clone Git para receber atualizações pelo programa.** Download ZIP permite executar a ferramenta, mas não cria o histórico e a origem necessários ao atualizador. Para migrar de ZIP, faça um clone em outra pasta e copie suas pesquisas para `output/`, preservando a cópia anterior.

## 3. Abrir a interface

Windows:

```powershell
py -3 abyss.py --ui
```

macOS / Linux:

```bash
python3 abyss.py --ui
```

O menu permite:

1. Criar pesquisa com empresa, unidade, domínios e aliases.
2. Abrir resultados salvos, filtrar, ver detalhes e exportar PDF/Excel.
3. Retomar uma pesquisa anterior ou interrompida.
4. Consultar e instalar novas releases.

Sem provedor configurado, escolha **Plano manual/importação**. Esse modo gera consultas para pesquisa e aceita referências JSON; não executa buscas na internet sozinho.

## 4. Ativar buscas automáticas

### Brave Search API

Obtenha sua chave diretamente no [painel do Brave Search API](https://api-dashboard.search.brave.com/). A disponibilidade, cota e cobrança dependem do plano do provedor. A ferramenta não inclui chave nem contrata serviços.

No PowerShell, configure a chave apenas para a sessão:

```powershell
$env:BRAVE_API_KEY = "SUA_CHAVE"
py -3 abyss.py --ui
```

No macOS/Linux:

```bash
export BRAVE_API_KEY="SUA_CHAVE"
python3 abyss.py --ui
```

`SUA_CHAVE` é um marcador, não uma credencial incluída. Não coloque sua chave no código, nas pesquisas exportadas ou em commits. O programa lê variáveis de ambiente; **não carrega arquivos `.env` automaticamente**.

### SearXNG

Informe uma instância existente com a saída JSON habilitada. Muitas instâncias públicas desativam essa saída; nesse caso a consulta pode receber HTTP 403. O ABYSS não instala SearXNG automaticamente.

```bash
python3 abyss.py --company "Empresa Exemplo" --provider searxng \
  --searxng-url http://localhost:8080 --max-queries 9
```

No PowerShell, use a mesma linha sem a barra de continuação `\`, trocando `python3` por `py -3`. Servidores remotos devem usar HTTPS. Para repetir o endereço sem digitá-lo, defina `SEARXNG_URL` no ambiente.

O modo **Ambos** consulta Brave e SearXNG, exigindo as duas configurações. Um provedor indisponível é suspenso naquela execução; resultados do outro são preservados. O relatório mostra a cobertura incompleta.

## 5. Usar buscas mais profundas

```bash
python3 abyss.py --company "Empresa Exemplo" --location "Anápolis GO" \
  --domain example.com --alias "Nome comercial" --depth deep \
  --person "Nome do profissional" --keyword "automação industrial" \
  --provider brave --pages 3 --max-queries 20 --max-requests 30 \
  --freshness year --export pdf xlsx
```

- `--depth deep`: mais variações, incluindo termos internacionais. Não aumenta sozinho o orçamento de chamadas.
- `--person`: nomes conhecidos fornecidos por você; também pesquisa sinais de mudança de vínculo.
- `--keyword`: tema específico. A opção pode ser repetida.
- `--exclude-domain`: exclui domínios nas consultas por `-site:`. O respeito ao operador depende do buscador.
- `--query-file caminho.txt`: adiciona consultas personalizadas, uma por linha; linhas vazias e comentários iniciados por `#` são ignorados.
- `--pages`: de 1 a 10 páginas por consulta/provedor.
- `--max-queries`: quantidade de consultas do plano a cobrir.
- `--max-requests`: limite total de chamadas novas naquela execução, somando páginas e provedores. O padrão é 30.
- `--freshness all|day|month|year`: filtro temporal do buscador. Não comprova que um cargo ou evento é atual.

Nomes, temas e consultas informados explicitamente têm prioridade no plano. Os demais temas são intercalados para distribuir a cobertura entre as dimensões.

O programa preserva resultados parciais em `checkpoint.json` após cada requisição concluída. `Ctrl+C` interrompe o lote e mantém os resultados já processados. Uma requisição interrompida antes de concluir não é marcada como sucesso.

Para retomar, use a opção 3 do menu ou:

```bash
python3 abyss.py --resume output/SUA-PESQUISA/checkpoint.json \
  --max-queries 50 --max-requests 30
```

Também pode informar `research.json`. Configure novamente a chave/URL do provedor no ambiente. A retomada usa o plano e os dados originais, preserva os arquivos anteriores e grava uma pasta nova. Páginas com sucesso não se repetem para o mesmo provedor e período; erros e cobertura parcial podem ser tentados novamente. Se mudar `--freshness`, as consultas desse novo período precisam ser executadas. Para acrescentar novos nomes, temas ou consultas ao plano, inicie outra pesquisa.

## 6. Onde ficam os resultados

As pesquisas são gravadas em `output/`, relativas à pasta onde você executou o comando. Use `--output caminho` para escolher outra pasta nova.

- `research.json`: dados consolidados e evidências.
- `checkpoint.json`: estado recuperável da coleta.
- `sources.csv`: fontes e consultas associadas.
- `report.txt` e `queries.txt`: relatório e plano de pesquisa.
- `export-*/`: relatórios PDF e Excel `.xlsx`, quando solicitados.
- `sha256.json`: integridade dos arquivos exportados.

`output/`, `data/` e credenciais `.env` são ignorados pelo Git. Os dados de pesquisa não são enviados ao repositório pelo programa.

## 7. Avisos e atualizações por release

Ao abrir o menu em terminal interativo, o ABYSS consulta a release estável oficial, com cache de 24 horas e timeout de 3 segundos. Se houver versão superior, exibe um aviso. Falta de rede não impede usar o programa.

Escolha **4 — Atualizações** para consultar novamente e atualizar. Pelo comando:

```bash
python3 abyss.py --check-update
python3 abyss.py --update
```

No Windows, use `py -3`. A atualização busca a **tag da release estável**, e não simplesmente o último commit de desenvolvimento. Não exige chave de GitHub no clone HTTPS público.

Se você ainda usa a versão 0.1 ou 0.2, faça `git pull --ff-only` uma vez para obter a versão que inclui o atualizador. O Git recusará o avanço se o histórico estiver divergente; preserve mudanças locais antes de prosseguir.

O atualizador exige:

- Instalação via Git, na branch `main`, com `origin` apontando para `mister-m-1337/abyss`.
- Ausência de mudanças locais e arquivos não versionados fora das pastas ignoradas.
- Histórico compatível com avanço por `fast-forward`.

Ele não executa `reset --hard`, não limpa arquivos e não força a troca de branch. Arquivos em `output/` são preservados. Depois de atualizar, encerre e reabra o programa.

Para desativar apenas a verificação automática, defina `ABYSS_NO_UPDATE_CHECK=1` no ambiente. A opção 4 e `--check-update` continuam disponíveis. A verificação consulta apenas o GitHub; nenhuma informação do alvo é enviada nesse processo.

## Solução de problemas

| Mensagem/situação | Como resolver |
|---|---|
| Python não encontrado | Reabra o terminal, verifique a instalação e use `py -3` no Windows. |
| `BRAVE_API_KEY` ausente | Configure a variável na mesma sessão ou escolha outro modo. |
| HTTP 401/403/429 | Confira permissão, cota e configuração do provedor; o ABYSS não contorna bloqueios. |
| Nenhum resultado no modo manual | Esse modo gera o plano; configure um provedor ou importe referências. |
| Limite de chamadas atingido | Retome a pesquisa; aumentar o plano sozinho não aumenta o orçamento de chamadas. |
| Atualização bloqueada por alterações locais | Preserve suas mudanças e reveja `git status`. O programa não descarta seu trabalho. |
| Download ZIP não atualiza | Faça a instalação via Git e copie suas pesquisas. |
| Falha ao consultar releases | Tente novamente com rede disponível; continue usando a versão instalada. |

Para verificar a instalação: `python3 -m unittest discover -s tests -v` (ou `py -3 -m unittest discover -s tests -v`).

As evidências exigem revisão na fonte original. Um nome encontrado em trecho público não confirma vínculo atual, autoridade de compra ou demanda comercial. O ABYSS não envia mensagens nem preenche cadastros.
