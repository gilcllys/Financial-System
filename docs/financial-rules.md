# Regras financeiras usadas pela interface

Este documento registra decisões de produto adotadas durante a correção do relatório Melhorias_Controle_Financeiro.pdf (fornecido pelo usuário em 2026-11-02). O PDF continua sendo a fonte dos relatos originais; decisões sobre valores e períodos foram confirmadas pelo usuário no chat.

- **Faturas:** a compra pertence ao ciclo delimitado pelo fechamento efetivo do cartão. Fechamento em sábado ou domingo é antecipado para sexta-feira. Na Home, o mês selecionado é o mês de fechamento: em novembro, mostra-se o ciclo que fecha em novembro e vence em dezembro; a Home avança ao ciclo seguinte quando o mês selecionado muda. Home, Parcelamentos, Faturas, dívidas por pessoa e o gráfico por cartão devem derivar o mesmo período. Endpoints antigos sem mês de fechamento explícito mantêm sua regra anterior.
- **Parcelamento:** o valor total deve ser dividido em centavos sem perda; a última parcela recebe qualquer resíduo. A parcela é considerada vencida/fechada conforme o ciclo do cartão, não só pela data da compra.
- **Valores compartilhados:** “devido ao banco” mostra o valor bruto cobrado pelo cartão. O custo pessoal desconta de compras compartilhadas a parte reembolsável. O resumo não deve somar novamente uma compra individual como se fosse compartilhada.
- **Receitas e despesas:** receitas ficam positivas no histórico e nos resumos. Categorias têm tipo despesa ou receita. Transferências entre contas não são receitas.
- **Sem categoria:** usa o código estável `uncategorized`, sem depender de ID numérico da base.
- **Análises por cartão:** o ciclo da fatura é o padrão. “Mês da compra” é uma alternativa explícita.
- **Métricas diárias:** média por dia com gastos e mediana são apresentadas junto ao total diário; dias sem despesa não entram na média.
- **Dados e implantação:** migrações são aditivas. Os endpoints existentes seguem disponíveis durante a transição. Testes e dados de QA não devem atingir produção.
