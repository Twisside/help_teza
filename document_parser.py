import os
import re
from bs4 import BeautifulSoup
import tika

base_dir = os.path.dirname(__file__)
local_jar = os.path.abspath(os.path.join(base_dir, 'bin', 'tika-server.jar'))
# Fix Windows pathing for the file:// URI
os.environ['TIKA_SERVER_JAR'] = f"file:///{local_jar.replace(os.sep, '/')}"

from tika import parser as tika_parser
from chunker import DocumentChunker
import os
import re
from bs4 import BeautifulSoup

class UniversalParser:
    def __init__(self, chunker):
        """
        Initializes the parser and warms up the tika-python server.
        """
        self.chunker = chunker
        self._warmup_tika()

    def _warmup_tika(self):
        """
        Lets tika-python automatically handle downloading the JAR (if missing)
        and starting the background Java server.
        """
        print("Warming up tika-python server...")
        try:
            # This triggers tika-python's internal server manager
            tika.initVM()
            # A dummy parse to ensure it's fully awake
            tika_parser.from_buffer("")
            print("Tika server is awake and ready!")
        except Exception as e:
            print(f"CRITICAL: tika-python failed to start. Ensure Java is installed on your system. Details: {e}")

    def process_file(self, filepath: str) -> list[str]:
        """Routes the file to the correct processing engine based on extension."""
        if not os.path.exists(filepath):
            print(f"Error: File not found - {filepath}")
            return []

        _, ext = os.path.splitext(filepath)
        ext = ext.lower()

        # Code files bypass Tika to preserve perfect syntax for Tree-sitter
        if ext in self.chunker.ts_parsers or ext in self.chunker.langchain_map:
            return self._process_code_file(filepath, ext)

        # Everything else (PDF, Word, Excel, etc.) goes to tika-python
        else:
            return self._process_rich_document(filepath)

    def _process_code_file(self, filepath: str, ext: str) -> list[str]:
        """Reads code natively to preserve AST structure."""
        try:
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                raw_code = f.read()

            if not raw_code.strip():
                return []

            return self.chunker.chunk_code(raw_code, ext)
        except Exception as e:
            print(f"Failed to read code file {filepath}: {e}")
            return []

    def _process_rich_document(self, filepath: str) -> list[str]:
        """
        Uses tika-python to extract content.
        Requests XML/HTML to preserve tables, formats them, and cleans the text.
        """
        try:
            # We ask tika-python for XML content so we don't lose table rows/columns
            parsed_file = tika_parser.from_file(filepath, xmlContent=True)

            status = parsed_file.get("status")
            if status != 200:
                print(f"Warning: tika-python returned status {status} for {filepath}")

            html_content = parsed_file.get("content", "")

            if not html_content or not html_content.strip():
                return []

            # 1. Extract tables into Markdown chunks
            table_chunks = self._extract_tables(html_content)

            # 2. Strip tables from the HTML so we don't index unformatted duplicates
            soup = BeautifulSoup(html_content, 'html.parser')
            for table in soup.find_all('table'):
                table.decompose()

            raw_text = soup.get_text(separator='\n')
            clean_text = self._clean_text(raw_text)

            # 3. Chunk the standard text
            text_chunks = self.chunker.chunk_document(clean_text)

            return text_chunks + table_chunks

        except Exception as e:
            print(f"tika-python parsing failed for {filepath}: {e}")
            return []

    def _extract_tables(self, html_content: str) -> list[str]:
        """Converts HTML tables found by tika-python into Markdown chunks."""
        soup = BeautifulSoup(html_content, 'html.parser')
        tables = soup.find_all('table')
        table_chunks = []

        for table in tables:
            rows = table.find_all('tr')
            if not rows:
                continue

            header_cells = rows[0].find_all(['th', 'td'])
            headers = [cell.get_text(strip=True).replace('\n', ' ') for cell in header_cells]

            if not headers:
                continue

            md_header = "| " + " | ".join(headers) + " |\n"
            md_separator = "|" + "|".join(["---"] * len(headers)) + "|\n"
            base_table_str = md_header + md_separator

            current_chunk_str = base_table_str

            for row in rows[1:]:
                cells = row.find_all(['th', 'td'])
                row_data = [cell.get_text(strip=True).replace('\n', ' ') for cell in cells]

                while len(row_data) < len(headers):
                    row_data.append("")

                md_row = "| " + " | ".join(row_data) + " |\n"

                if len(current_chunk_str + md_row) > self.chunker.max_chars:
                    table_chunks.append(current_chunk_str.strip())
                    current_chunk_str = base_table_str + md_row
                else:
                    current_chunk_str += md_row

            if current_chunk_str != base_table_str:
                table_chunks.append(current_chunk_str.strip())

        return table_chunks

    def _clean_text(self, raw_text: str) -> str:
        """Cleans up tika-python's text extraction."""
        if not raw_text:
            return ""

        lines = [line.strip() for line in raw_text.splitlines()]
        text = "\n".join(lines)
        cleaned_text = re.sub(r'\n{3,}', '\n\n', text)

        return cleaned_text.strip()