# Instalar e atualizar o ABYSS

Há duas formas de instalar: **instalador único recomendado**, com Python e certificados incluídos, ou instalação pelo código-fonte, com Python/Git separados. Brave e SearXNG são alternativas para realizar buscas automáticas, não requisitos para abrir o programa ou analisar pesquisas já salvas.

## Instalador único — sem Python ou Git separados

Baixe apenas o arquivo correspondente ao seu computador na [release mais recente](https://github.com/mister-m-1337/abyss/releases/latest):

| Sistema | Arquivo |
|---|---|
| Windows 10/11 x64 | [ABYSS-Setup-windows-x64.exe](https://github.com/mister-m-1337/abyss/releases/latest/download/ABYSS-Setup-windows-x64.exe) |
| macOS Apple Silicon (M1 ou superior) | [ABYSS-Setup-macos-arm64](https://github.com/mister-m-1337/abyss/releases/latest/download/ABYSS-Setup-macos-arm64) |
| macOS Intel | [ABYSS-Setup-macos-x64](https://github.com/mister-m-1337/abyss/releases/latest/download/ABYSS-Setup-macos-x64) |
| Linux x64 (Ubuntu 24.04 ou compatível) | [ABYSS-Setup-linux-x64](https://github.com/mister-m-1337/abyss/releases/latest/download/ABYSS-Setup-linux-x64) |

Os pacotes macOS são construídos e testados em macOS 15; Linux em Ubuntu 24.04 x64. Outras arquiteturas, incluindo Windows ARM e Linux ARM, ainda não têm pacote oficial.

**Windows:** abra o `.exe` e siga as instruções no terminal. Também é possível iniciar pelo PowerShell:

```powershell
.\ABYSS-Setup-windows-x64.exe
```

**macOS:** abra o Terminal na pasta de download. Para Apple Silicon:

```bash
chmod +x ABYSS-Setup-macos-arm64
./ABYSS-Setup-macos-arm64
```

Em Mac Intel, substitua `arm64` por `x64`. **Linux:**

```bash
chmod +x ABYSS-Setup-linux-x64
./ABYSS-Setup-linux-x64
```

O instalador oferece uma pasta por usuário e um lançador, com opção de cópia para a Área de Trabalho quando essa pasta existir. Não exige administrador e não altera o Python global. No Linux, o lançador é um script `.sh`; execute-o pelo terminal. No macOS é `.command`; no Windows, `.cmd`.

Pastas padrão:

- Windows: `%LOCALAPPDATA%\ABYSS`.
- macOS: `~/Library/Application Support/ABYSS`.
- Linux: `~/.local/share/abyss`, respeitando `XDG_DATA_HOME` quando informado.

A instalação mantém versões em `versions/`, pesquisas em `output/` e preferências sem credenciais em `config.json`. A chave Brave não é salva: se necessário, ela será solicitada sem eco na sessão. O menu **5 — Configurar buscador** permite escolher Brave, SearXNG existente ou modo manual.

O pacote contém o runtime Python, certificados TLS, código, menu e exportadores. **Não inclui assinatura/chave Brave nem instala um servidor SearXNG.** É preciso fornecer uma chave própria ou o endereço de uma instância existente para busca automática. O SearXNG deve aceitar JSON.

Os executáveis ainda não têm assinatura Authenticode/Apple Developer. Windows/macOS podem apresentar avisos de segurança. Verifique que o arquivo veio deste repositório e, se decidir abri-lo, use a autorização específica disponibilizada pelo sistema; o ABYSS não desativa proteções. Cada executável tem um arquivo `.sha256` na release para conferência de integridade.

No instalador, a opção **4 — Atualizações** baixa o executável oficial da nova release, verifica seu SHA-256 e instala em outra pasta de versão. O lançador passa a apontar para ela; as pesquisas e versões anteriores permanecem. Reabra pelo lançador após atualizar. Não é necessário Git para esse fluxo.

Instalação não interativa, útil para administradores/testes:

```bash
./ABYSS-Setup-linux-x64 --install --install-dir "$HOME/ABYSS"
```

Use o nome do executável correspondente ao seu sistema. A opção `--desktop-shortcut` também cria uma cópia do lançador na Área de Trabalho, se disponível.

## Instalação pelo código-fonte

Nesta alternativa são necessários **Python 3.10 ou superior e Git**. As instruções abaixo mantêm o programa sem dependências Python adicionais.

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
5. Configurar o buscador sem gravar chaves em arquivos.

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

Na instalação pelo código-fonte, o atualizador exige:

- Instalação via Git, na branch `main`, com `origin` apontando para `mister-m-1337/abyss`.
- Ausência de mudanças locais e arquivos não versionados fora das pastas ignoradas.
- Histórico compatível com avanço por `fast-forward`.

Ele não executa `reset --hard`, não limpa arquivos e não força a troca de branch. Arquivos em `output/` são preservados. Depois de atualizar, encerre e reabra o programa.

Na instalação por executável, o mesmo menu usa os pacotes publicados na release com conferência SHA-256, sem Git. Uma release sem pacote da sua plataforma não pode ser instalada por esse fluxo.

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
