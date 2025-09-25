import os
import json
import time
import logging
import google.generativeai as genai
from dotenv import load_dotenv

# Configuração de logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Carrega variáveis de ambiente
load_dotenv()

# Configura a API do Gemini
api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    logger.error("GEMINI_API_KEY não encontrada nas variáveis de ambiente")
    raise ValueError("GEMINI_API_KEY não configurada")

genai.configure(api_key=api_key)

class PDFExtractorAgent:
    def __init__(self, model_name='gemini-1.5-flash-002'):
        """
        Inicializa o agente extrator de PDFs.
        
        Args:
            model_name (str): Nome do modelo Gemini a ser utilizado
        """
        self.model = genai.GenerativeModel(model_name)
        self.prompt_template = """
        Você é um especialista em análise de documentos fiscais. Analise cuidadosamente esta nota fiscal 
        e extraia APENAS as informações solicitadas, retornando um JSON válido.
        
        Extraia os seguintes dados da nota fiscal:
        
        1. FORNECEDOR (empresa emitente):
           - Razão Social: nome completo da empresa
           - Fantasia: nome fantasia (se disponível)
           - CNPJ: número do CNPJ
        
        2. FATURADO (cliente/destinatário):
           - Nome Completo: nome da pessoa ou empresa
           - CPF/CNPJ: número do CPF ou CNPJ se for empresa
        
        3. NÚMERO DA NOTA FISCAL: número do documento fiscal
        
        4. DATA DE EMISSÃO: data em que a nota foi emitida (formato: DD/MM/AAAA)
        
        5. DESCRIÇÃO DOS PRODUTOS: lista com descrição de cada item/produto/serviço

        6. CLASIFICAÇÃO DE DESPESA: lista com categorias de despesa
        
        7. QUANTIDADE DE PARCELAS: número de parcelas (se à vista, considere 1)
        
        8. DATA DE VENCIMENTO: data de vencimento da nota ou primeira parcela (formato: DD/MM/AAAA)
        
        9. VALOR TOTAL: valor total da nota fiscal
        
        IMPORTANTE:
        - Retorne APENAS o JSON, sem explicações adicionais
        - Use null para campos não encontrados
        - Para valores monetários, use números decimais (ex: 1500.50)
        - Para datas, use o formato DD/MM/AAAA
        - Para descrição_produtos, retorne um array de strings
        - Para o campo do faturado ou destinatário, procure pelo campo de CPF ou CNPJ na nota fiscal
        
        Estrutura JSON esperada:
        {
            "fornecedor": {
                "razao_social": "string",
                "fantasia": "string ou null",
                "cnpj": "string"
            },
            "faturado": {
                "nome_completo": "string",
                "cpf_cnpj": "string"
            },
            "numero_nota_fiscal": "string",
            "data_emissao": "string",
            "descricao_produtos": ["string"],
            "classificacao_despesa": ["string"],
            "quantidade_parcelas": número,
            "data_vencimento": "string",
            "valor_total": número
        }

        Sobre o Item 6 CLASSIFICAÇÃO DE DESPESA deve ser considerado o seguinte critério:
            Analise CADA ITEM na "descricao_produtos" associe cada um à sua categoria de despesa correspondente.

            CATEGORIAS VÁLIDAS:
            - INSUMOS AGRÍCOLAS (Ex: Sementes, Fertilizantes, Defensivos Agrícolas, Corretivos)
            - MANUTENÇÃO E OPERAÇÃO (Ex: Combustíveis, Lubrificantes, Peças, Parafusos, Pneus, Filtros, Ferramentas, Manutenção de Máquinas)
            - RECURSOS HUMANOS (Ex: Mão de Obra Temporária, Salários)
            - SERVIÇOS OPERACIONAIS (Ex: Frete, Transporte, Colheita Terceirizada, Secagem, Armazenagem, Pulverização)
            - INFRAESTRUTURA E UTILIDADES (Ex: Energia Elétrica, Arrendamento de Terras, Materiais de Construção, Reformas)
            - ADMINISTRATIVAS (Ex: Honorários Contábeis, Advocatícios, Agronômicos, Despesas Bancárias)
            - SEGUROS E PROTEÇÃO (Ex: Seguro Agrícola, Seguro de Máquinas/Veículos)
            - IMPOSTOS E TAXAS (Ex: ITR, IPTU, IPVA, INCRA-CCIR)
            - INVESTIMENTOS (Ex: Aquisição de Máquinas, Veículos, Imóveis, Infraestrutura Rural)
            - OUTRAS DESPESAS (Use esta categoria se nenhum item se encaixar claramente nas outras)
        IMPORTANTE:
            - A sua resposta deve ser APENAS um objeto JSON válido.
            - O JSON de resposta deve ter a seguinte estrutura: {{"classificacoes": ["CATEGORIA_1", "CATEGORIA_2", ...]}}
            - Não inclua explicações ou texto fora do JSON.
            - A lista de classificações não deve conter valores duplicados.
        """

    def _clean_json_response(self, response_text):
        """
        Limpa a resposta da API para extrair apenas o JSON válido.
        
        Args:
            response_text (str): Texto da resposta da API
            
        Returns:
            str: JSON limpo
        """
        json_str = response_text.strip()
        if json_str.startswith("```json"):
            json_str = json_str[7:]
        elif json_str.startswith("```"):
            json_str = json_str[3:]
        if json_str.endswith("```"):
            json_str = json_str[:-3]
        
        return json_str.strip()

    def extract_pdf_to_json(self, pdf_path, max_retries=3, retry_delay=2):
        """
        Extrai informações de um PDF e retorna em formato JSON usando upload direto do arquivo
        
        Args:
            pdf_path (str): Caminho para o arquivo PDF
            max_retries (int): Número máximo de tentativas em caso de falha
            retry_delay (int): Tempo de espera entre tentativas em segundos
            
        Returns:
            dict: Dados extraídos em formato JSON ou mensagem de erro
        """
        pdf_file = None
        
        try:
            if not os.path.exists(pdf_path):
                return {"error": f"Arquivo não encontrado: {pdf_path}"}
                
            logger.info(f"Fazendo upload do arquivo: {pdf_path}")
            pdf_file = genai.upload_file(pdf_path, mime_type="application/pdf")
            
            logger.info("Arquivo enviado. Aguardando processamento...")
            timeout = 30
            start_time = time.time()
            
            while pdf_file.state.name == "PROCESSING":
                if time.time() - start_time > timeout:
                    return {"error": "Timeout no processamento do arquivo"}
                    
                time.sleep(retry_delay)
                pdf_file = genai.get_file(pdf_file.name)
                
            if pdf_file.state.name == "FAILED":
                return {"error": "Falha no processamento do arquivo"}
            
            logger.info("Arquivo processado. Enviando para extração de dados...")
            
            # Preparar conteúdo para a API
            contents = [self.prompt_template, pdf_file]
            
            # Fazer a requisição à API do Gemini com retentativas
            for attempt in range(max_retries):
                try:
                    response = self.model.generate_content(contents)
                    
                    if response.text:
                        json_str = self._clean_json_response(response.text)
                        return json.loads(json_str)
                    
                    logger.warning(f"Tentativa {attempt+1}: Resposta vazia da API")
                    
                except Exception as e:
                    logger.warning(f"Tentativa {attempt+1} falhou: {str(e)}")
                    
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
            
            return {"error": "Falha após múltiplas tentativas de extração"}
            
        except json.JSONDecodeError as e:
            return {"error": f"Erro ao decodificar JSON: {str(e)}"}
        except Exception as e:
            return {"error": str(e)}
        finally:
            if pdf_file:
                try:
                    genai.delete_file(pdf_file.name)
                    logger.info("Arquivo temporário removido com sucesso.")
                except Exception as e:
                    logger.warning(f"Não foi possível remover o arquivo temporário: {str(e)}")