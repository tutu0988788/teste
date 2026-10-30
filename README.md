# ConferiXML

Aplicativo local para importar ZIPs/XMLs de NF-e (modelo 55) e NFC-e (modelo 65), identificar empresas, apurar documentos, pagamentos, cancelamentos, duplicidades e divergências.

## Requisitos
- Windows 10/11
- Python 3.10 ou superior (marque "Add Python to PATH" durante a instalação)

## Como executar
1. Extraia o ZIP em uma pasta.
2. Dê dois cliques em `run.bat`.
3. Na primeira execução, aguarde a instalação das dependências.
4. O navegador abrirá o painel local.

## Regras da primeira versão
- Faturamento documental: soma de `vNF` de NF-e/NFC-e autorizadas e não canceladas.
- Pagamentos informados: soma de `vPag` em `detPag` (NFC-e/NF-e quando disponível).
- Eventos de cancelamento são lidos para excluir a chave correspondente.
- Chaves de acesso são deduplicadas.
- XMLs em pastas EVENTO/INU não são tratados como documentos de venda. XMLs de evento são lidos para localizar cancelamentos.
- Devoluções e notas de ajuste são identificadas/indicadas para revisão; não são abatidas automaticamente do faturamento nesta versão.

## Observações
Este aplicativo é uma ferramenta de conferência gerencial, não substitui validação fiscal/contábil. O resultado depende dos XMLs fornecidos. Antes de usar em fechamento oficial, valide amostras com o contador/ERP.
