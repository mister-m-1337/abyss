# Publicar instaladores oficiais

O usuário final não precisa deste procedimento. O workflow constrói um executável por plataforma com Python 3.13, PyInstaller e certificados certifi fixados nas versões do workflow. Licenças de Python, certificados, ferramenta de empacotamento e ABYSS são incluídas. A licença proprietária do ABYSS não elimina direitos sobre componentes de terceiros.

Na primeira distribuição v0.4.1, a fila de runners Apple Silicon foi substituída por build local isolado em macOS 27.0.1/Python 3.12.15, com os mesmos pins de PyInstaller/certifi e verificação nativa de instalação, exportações e HTTPS. Os demais pacotes foram gerados no workflow. Nenhum Python global foi alterado. A seleção de plataforma do workflow permite refazer apenas o pacote necessário enquanto a release ainda é draft.

Para publicar uma versão:

1. Atualize `VERSION` e a documentação, execute os testes, faça commit e push.
2. Crie e envie a tag estável correspondente: `git tag vMAJOR.MINOR.PATCH` e `git push origin vMAJOR.MINOR.PATCH`.
3. Crie uma release **draft** para a tag com as notas.
4. Execute **Actions → Build installers → Run workflow**, informando a tag.
5. Aguarde os quatro jobs aprovarem os testes e anexarem executáveis e arquivos SHA-256 ao draft. Cada job instala o pacote numa pasta temporária, exporta PDF/XLSX e consulta releases por HTTPS com os certificados incluídos.
6. Confira os arquivos e publique o draft como release mais recente.

O draft evita avisar usuários antes de os pacotes estarem prontos. Em caso de correção, use uma nova versão/tag: não substitua silenciosamente o executável de uma versão já publicada. Não há assinatura Authenticode/Apple Developer nesta configuração.
