"""
Módulo para construir contexto a partir do banco de dados para consultas RAG.

Realiza análise léxica básica da pergunta do usuário para identificar:
- Fornecedores/clientes (por nome ou CNPJ/CPF)
- Números de notas fiscais
- Classificações de despesa
- Períodos de tempo
- Valores monetários
"""

import re
from datetime import datetime, timedelta
from django.db.models import Q, Sum, Count
from .models import AccountTransaction, Person, Classification, Installment

class RAGContextBuilder:
    """
    Constrói contexto para consultas RAG analisando a pergunta e buscando dados relevantes.
    """

    # Palavras-chave para identificar tipos de consulta
    KEYWORDS_TOTAL = ['total', 'soma', 'somar', 'quanto', 'valor']
    KEYWORDS_COUNT = ['quantas', 'quantos', 'número de', 'quantidade']
    KEYWORDS_LIST = ['listar', 'liste', 'mostrar', 'mostre', 'quais']
    KEYWORDS_PERSON = ['fornecedor', 'cliente', 'faturado', 'empresa']
    KEYWORDS_CLASSIFICATION = ['classificação', 'categoria', 'despesa', 'receita', 'tipo']
    KEYWORDS_TRANSACTION = ['transação', 'transações', 'nota', 'notas', 'nota fiscal', 'nf']
    KEYWORDS_INSTALLMENT = ['parcela', 'parcelas', 'vencimento']
    KEYWORDS_PERIOD = ['mês', 'ano', 'período', 'data', 'quando']

    # Mapeamento de meses
    MONTHS = {
        'janeiro': 1, 'fevereiro': 2, 'março': 3, 'abril': 4,
        'maio': 5, 'junho': 6, 'julho': 7, 'agosto': 8,
        'setembro': 9, 'outubro': 10, 'novembro': 11, 'dezembro': 12
    }

    def __init__(self, question):
        """
        Inicializa o construtor de contexto.

        Args:
            question (str): Pergunta do usuário
        """
        self.question = question.lower().strip()
        self.context_parts = []

    def _extract_document_number(self):
        """
        Extrai números de documentos (CNPJ/CPF) da pergunta.

        Returns:
            list: Lista de documentos encontrados
        """
        # Padrão para CNPJ: XX.XXX.XXX/XXXX-XX ou XXXXXXXXXXXXXX
        cnpj_pattern = r'\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}'
        # Padrão para CPF: XXX.XXX.XXX-XX ou XXXXXXXXXXX
        cpf_pattern = r'\d{3}\.?\d{3}\.?\d{3}-?\d{2}'

        documents = []
        documents.extend(re.findall(cnpj_pattern, self.question))
        documents.extend(re.findall(cpf_pattern, self.question))

        return [doc.replace('.', '').replace('/', '').replace('-', '') for doc in documents]

    def _extract_invoice_number(self):
        """
        Extrai números de nota fiscal da pergunta.

        Returns:
            list: Lista de números de nota encontrados
        """
        # Procura por padrões como "nota 123", "nf 456", "nota fiscal 789"
        patterns = [
            r'nota\s+fiscal\s+(\d+)',
            r'nf\s+(\d+)',
            r'nota\s+(\d+)',
            r'número\s+(\d+)'
        ]

        invoice_numbers = []
        for pattern in patterns:
            matches = re.findall(pattern, self.question)
            invoice_numbers.extend(matches)

        return invoice_numbers

    def _extract_period(self):
        """
        Extrai período de tempo da pergunta.

        Returns:
            tuple: (data_inicio, data_fim) ou (None, None)
        """
        # Procura por mês específico
        for month_name, month_num in self.MONTHS.items():
            if month_name in self.question:
                # Procura por ano
                year_match = re.search(r'20\d{2}', self.question)
                year = int(year_match.group()) if year_match else datetime.now().year

                # Primeiro e último dia do mês
                start_date = datetime(year, month_num, 1).date()
                if month_num == 12:
                    end_date = datetime(year + 1, 1, 1).date() - timedelta(days=1)
                else:
                    end_date = datetime(year, month_num + 1, 1).date() - timedelta(days=1)

                return start_date, end_date

        # Procura por ano específico
        year_match = re.search(r'20\d{2}', self.question)
        if year_match:
            year = int(year_match.group())
            return datetime(year, 1, 1).date(), datetime(year, 12, 31).date()

        return None, None

    def _contains_keywords(self, keywords):
        """
        Verifica se a pergunta contém alguma das palavras-chave.

        Args:
            keywords (list): Lista de palavras-chave

        Returns:
            bool: True se encontrou alguma palavra-chave
        """
        return any(keyword in self.question for keyword in keywords)

    def _query_persons(self, documents=None):
        """
        Consulta pessoas no banco de dados.

        Args:
            documents (list): Lista de documentos para filtrar

        Returns:
            QuerySet: Pessoas encontradas
        """
        query = Q(status='ativo')

        if documents:
            query &= Q(documento__in=documents)

        persons = Person.objects.filter(query)
        return persons

    def _query_transactions(self, persons=None, invoice_numbers=None, start_date=None, end_date=None):
        """
        Consulta transações no banco de dados.

        Args:
            persons (QuerySet): Pessoas para filtrar
            invoice_numbers (list): Números de nota fiscal
            start_date (date): Data inicial
            end_date (date): Data final

        Returns:
            QuerySet: Transações encontradas
        """
        query = Q(status='ativo')

        if persons and persons.exists():
            query &= (Q(fornecedor_cliente__in=persons) | Q(faturado__in=persons))

        if invoice_numbers:
            query &= Q(numero_nota_fiscal__in=invoice_numbers)

        if start_date and end_date:
            query &= Q(data_emissao__range=[start_date, end_date])

        transactions = AccountTransaction.objects.filter(query).select_related(
            'fornecedor_cliente', 'faturado'
        ).prefetch_related('classificacoes')

        return transactions

    def _format_person_context(self, persons):
        """
        Formata informações de pessoas para o contexto.

        Args:
            persons (QuerySet): Pessoas a formatar

        Returns:
            str: Contexto formatado
        """
        if not persons.exists():
            return ""

        lines = ["### Pessoas/Empresas Cadastradas:\n"]
        for person in persons[:10]:  # Limita a 10 para não consumir muitos tokens
            fantasia_info = f" ({person.fantasia})" if person.fantasia else ""
            lines.append(
                f"- {person.razao_social}{fantasia_info}\n"
                f"  Documento: {person.documento}\n"
                f"  Tipo: {person.tipo}\n"
            )

        return "\n".join(lines)

    def _format_transaction_context(self, transactions):
        """
        Formata informações de transações para o contexto.

        Args:
            transactions (QuerySet): Transações a formatar

        Returns:
            str: Contexto formatado
        """
        if not transactions.exists():
            return ""

        lines = ["### Notas Fiscais Encontradas:\n"]
        for tx in transactions[:20]:  # Limita a 20 para não consumir muitos tokens
            classificacoes = ", ".join([c.descricao for c in tx.classificacoes.all()])
            lines.append(
                f"- Nota Fiscal: {tx.numero_nota_fiscal}\n"
                f"  Fornecedor: {tx.fornecedor_cliente.razao_social}\n"
                f"  Faturado: {tx.faturado.razao_social if tx.faturado else 'N/A'}\n"
                f"  Data Emissão: {tx.data_emissao.strftime('%d/%m/%Y')}\n"
                f"  Valor Total: R$ {tx.valor_total:,.2f}\n"
                f"  Tipo: {tx.tipo}\n"
                f"  Classificações: {classificacoes}\n"
                f"  Descrição: {tx.descricao}\n"
            )

        return "\n".join(lines)

    def _format_summary_context(self, transactions):
        """
        Formata informações de resumo (totais, contagens) para o contexto.

        Args:
            transactions (QuerySet): Transações para sumarizar

        Returns:
            str: Contexto formatado
        """
        if not transactions.exists():
            return ""

        # Calcula totais
        total_value = transactions.aggregate(total=Sum('valor_total'))['total'] or 0
        count = transactions.count()

        # Agrupa por tipo
        by_type = transactions.values('tipo').annotate(
            total=Sum('valor_total'),
            count=Count('id')
        )

        # Agrupa por classificação
        by_classification = transactions.values(
            'classificacoes__descricao'
        ).annotate(
            total=Sum('valor_total'),
            count=Count('id')
        ).order_by('-total')[:10]

        lines = ["### Resumo das Notas Fiscais:\n"]
        lines.append(f"Total de notas fiscais: {count}")
        lines.append(f"Valor total: R$ {total_value:,.2f}\n")

        if by_type:
            lines.append("\n**Por Tipo:**")
            for item in by_type:
                lines.append(
                    f"- {item['tipo']}: {item['count']} transações, "
                    f"R$ {item['total']:,.2f}"
                )

        if by_classification:
            lines.append("\n**Por Classificação:**")
            for item in by_classification:
                if item['classificacoes__descricao']:
                    lines.append(
                        f"- {item['classificacoes__descricao']}: {item['count']} transações, "
                        f"R$ {item['total']:,.2f}"
                    )

        return "\n".join(lines)

    def _extract_classification_names(self):
        """
        Extrai nomes de classificações mencionadas na pergunta.

        Returns:
            list: Lista de nomes de classificação encontrados
        """
        # Lista de classificações conhecidas
        known_classifications = [
            'INSUMOS AGRÍCOLAS', 'MANUTENÇÃO E OPERAÇÃO', 'RECURSOS HUMANOS',
            'SERVIÇOS OPERACIONAIS', 'INFRAESTRUTURA E UTILIDADES',
            'ADMINISTRATIVAS', 'SEGUROS E PROTEÇÃO', 'IMPOSTOS E TAXAS',
            'INVESTIMENTOS', 'OUTRAS DESPESAS'
        ]

        found = []
        question_upper = self.question.upper()

        for classification in known_classifications:
            # Verifica se o nome completo ou palavras-chave estão na pergunta
            if classification in question_upper:
                found.append(classification)
            else:
                # Verifica palavras-chave específicas
                keywords = classification.split()
                if any(keyword in question_upper for keyword in keywords if len(keyword) > 3):
                    found.append(classification)

        return found

    def _query_classifications(self, classification_names=None):
        """
        Consulta classificações no banco de dados.

        Args:
            classification_names (list): Nomes de classificações para filtrar

        Returns:
            QuerySet: Classificações encontradas
        """
        query = Q(status='ativo')

        if classification_names:
            query &= Q(descricao__in=classification_names)

        classifications = Classification.objects.filter(query)
        return classifications

    def _query_installments(self, transactions=None, start_date=None, end_date=None):
        """
        Consulta parcelas no banco de dados.

        Args:
            transactions (QuerySet): Transações relacionadas às parcelas
            start_date (date): Data inicial de vencimento
            end_date (date): Data final de vencimento

        Returns:
            QuerySet: Parcelas encontradas
        """
        query = Q()

        if transactions and transactions.exists():
            query &= Q(account_transaction__in=transactions)

        if start_date and end_date:
            query &= Q(data_vencimento__range=[start_date, end_date])

        installments = Installment.objects.filter(query).select_related('account_transaction')
        return installments

    def _format_classification_context(self, classifications):
        """
        Formata informações de classificações para o contexto.

        Args:
            classifications (QuerySet): Classificações a formatar

        Returns:
            str: Contexto formatado
        """
        if not classifications.exists():
            return ""

        lines = ["### Classificações Cadastradas:\n"]
        for classification in classifications[:15]:  # Limita a 15
            lines.append(
                f"- {classification.descricao}\n"
                f"  Tipo: {classification.tipo}\n"
            )

        return "\n".join(lines)

    def _format_installment_context(self, installments):
        """
        Formata informações de parcelas para o contexto.

        Args:
            installments (QuerySet): Parcelas a formatar

        Returns:
            str: Contexto formatado
        """
        if not installments.exists():
            return ""

        lines = ["### Parcelas Encontradas:\n"]
        for inst in installments[:30]:  # Limita a 30 para não consumir muitos tokens
            lines.append(
                f"- Parcela: {inst.identificacao}\n"
                f"  Transação: Nota Fiscal {inst.account_transaction.numero_nota_fiscal}\n"
                f"  Valor Parcela: R$ {inst.valor_parcela:,.2f}\n"
                f"  Valor Pago: R$ {inst.valor_pago:,.2f}\n"
                f"  Saldo: R$ {inst.valor_saldo:,.2f}\n"
                f"  Status: {inst.status_parcela}\n"
                f"  Vencimento: {inst.data_vencimento.strftime('%d/%m/%Y')}\n"
            )

        return "\n".join(lines)

    def _format_installment_summary_context(self, installments):
        """
        Formata resumo de parcelas (totais, contagens) para o contexto.

        Args:
            installments (QuerySet): Parcelas para sumarizar

        Returns:
            str: Contexto formatado
        """
        if not installments.exists():
            return "" 

        # Calcula totais
        total_value = installments.aggregate(total=Sum('valor_parcela'))['total'] or 0
        total_paid = installments.aggregate(total=Sum('valor_pago'))['total'] or 0
        total_balance = installments.aggregate(total=Sum('valor_saldo'))['total'] or 0
        count = installments.count()

        # Agrupa por status
        by_status = installments.values('status_parcela').annotate(
            total=Sum('valor_parcela'),
            saldo=Sum('valor_saldo'),
            count=Count('id')
        ).order_by('-count')

        lines = ["### Resumo das Parcelas:\n"]
        lines.append(f"Total de parcelas: {count}")
        lines.append(f"Valor total: R$ {total_value:,.2f}")
        lines.append(f"Valor pago: R$ {total_paid:,.2f}")
        lines.append(f"Saldo restante: R$ {total_balance:,.2f}\n")

        if by_status:
            lines.append("\n**Por Status:**")
            for item in by_status:
                lines.append(
                    f"- {item['status_parcela']}: {item['count']} parcelas, "
                    f"R$ {item['total']:,.2f} (saldo: R$ {item['saldo']:,.2f})"
                )

        return "\n".join(lines)

    def build_context(self):
        """
        Constrói o contexto completo analisando a pergunta e consultando o banco.

        Returns:
            str: Contexto formatado para o RAG
        """
        # Extrai informações da pergunta
        documents = self._extract_document_number()
        invoice_numbers = self._extract_invoice_number()
        start_date, end_date = self._extract_period()
        classification_names = self._extract_classification_names()

        # Consulta pessoas se relevante
        persons = None
        if documents or self._contains_keywords(self.KEYWORDS_PERSON):
            persons = self._query_persons(documents)
            if persons.exists():
                self.context_parts.append(self._format_person_context(persons))

        # Consulta classificações se relevante
        if classification_names or self._contains_keywords(self.KEYWORDS_CLASSIFICATION):
            classifications = self._query_classifications(classification_names)
            if classifications.exists():
                self.context_parts.append(self._format_classification_context(classifications))

        # Consulta transações
        transactions = None
        if (self._contains_keywords(self.KEYWORDS_TRANSACTION) or
            self._contains_keywords(self.KEYWORDS_TOTAL) or
            self._contains_keywords(self.KEYWORDS_COUNT) or
            self._contains_keywords(self.KEYWORDS_LIST) or
            invoice_numbers or start_date or documents or
            self._contains_keywords(self.KEYWORDS_CLASSIFICATION)):

            transactions = self._query_transactions(
                persons=persons,
                invoice_numbers=invoice_numbers,
                start_date=start_date,
                end_date=end_date
            )

            # Filtra por classificação se especificada
            if classification_names and transactions.exists():
                transactions = transactions.filter(classificacoes__descricao__in=classification_names).distinct()

            if transactions.exists():
                # Se a pergunta pede resumo/total, fornece informações agregadas
                if (self._contains_keywords(self.KEYWORDS_TOTAL) or
                    self._contains_keywords(self.KEYWORDS_COUNT)):
                    self.context_parts.append(self._format_summary_context(transactions))
                else:
                    # Caso contrário, fornece lista detalhada
                    self.context_parts.append(self._format_transaction_context(transactions))

        # Consulta parcelas se relevante
        if self._contains_keywords(self.KEYWORDS_INSTALLMENT) or transactions:
            installments = self._query_installments(
                transactions=transactions,
                start_date=start_date,
                end_date=end_date
            )

            if installments.exists():
                # Se a pergunta pede resumo/total, fornece informações agregadas
                if (self._contains_keywords(self.KEYWORDS_TOTAL) or
                    self._contains_keywords(self.KEYWORDS_COUNT)):
                    self.context_parts.append(self._format_installment_summary_context(installments))
                else:
                    # Caso contrário, fornece lista detalhada
                    self.context_parts.append(self._format_installment_context(installments))

        # Junta todas as partes do contexto
        if self.context_parts:
            full_context = "\n\n".join(self.context_parts)
            return full_context
        else:
            return ""

def build_rag_context(question):
    """
    Função auxiliar para construir contexto a partir de uma pergunta.

    Args:
        question (str): Pergunta do usuário

    Returns:
        str: Contexto formatado
    """
    builder = RAGContextBuilder(question)
    return builder.build_context()
