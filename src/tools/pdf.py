import requests
from io import BytesIO

from agno.tools import Toolkit
from agno.utils.log import log_debug, log_warning

try:
    import PyPDF2
except ImportError:
    raise ImportError("`PyPDF2` not installed. Please install it with `pip install PyPDF2`.")

class PDFTools(Toolkit):
    """ Toolkit for handling PDF files. """

    def __init__(self, **kwargs):
        super().__init__(name="pdf_tools", tools=[self.extract_text_from_url], **kwargs)

    def extract_text_from_url(self, pdf_url: str) -> str:
        """ Extract text from a PDF file located at a given URL. """
        
        log_debug(f"Extracting text from PDF at URL: {pdf_url}")

        try:
            response = requests.get(pdf_url)
            response.raise_for_status()

            # Process with PyPDF2
            pdf_file = BytesIO(response.content)
            pdf_reader = PyPDF2.PdfReader(pdf_file)

            text = "### PDF Content ###\n"
            for page in pdf_reader.pages:
                text += page.extract_text() + "\n"

            return text.strip()
        except requests.RequestException as e:
            log_warning(f"Failed to fetch PDF from URL: {pdf_url}. Error: {e}")
            return f"Failed to fetch PDF from URL: {pdf_url}."
        except Exception as e:
            log_warning(f"Error processing PDF: {e}")
            return "Error processing PDF."