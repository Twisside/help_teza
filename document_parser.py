import os
import re
import pypdf
from chunker import DocumentChunker


class UniversalParser:
    def __init__(self, chunker):
        """
        Initializes the parser.
        (Tika warmup removed, making initialization instant).
        """
        self.chunker = chunker

    def process_file(self, filepath: str) -> list[str]:
        """Routes the file to the correct processing engine based on extension."""
        if not os.path.exists(filepath):
            print(f"Error: File not found - {filepath}")
            return []

        _, ext = os.path.splitext(filepath)
        ext = ext.lower()

        # Code files bypass to preserve perfect syntax for Tree-sitter
        if ext in self.chunker.ts_parsers or ext in self.chunker.langchain_map:
            return self._process_code_file(filepath, ext)

        # Route PDFs to pypdf
        elif ext == '.pdf':
            return self._process_pdf(filepath)

        # Route CSV/TSV to plain text conversion
        elif ext in ('.csv', '.tsv'):
            return self._process_csv(filepath)

        # Fallback for plain text files (.txt, .md, .csv, etc.)
        else:
            return self._process_plain_text(filepath)

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

    def _process_pdf(self, filepath: str) -> list[str]:
        """
        Uses pypdf to extract text from PDF files.
        """
        try:
            text_content = []
            with open(filepath, 'rb') as f:
                reader = pypdf.PdfReader(f)
                for page in reader.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text_content.append(page_text)

            raw_text = "\n".join(text_content)
            clean_text = self._clean_text(raw_text)

            if not clean_text:
                return []

            # Chunk the extracted PDF text
            return self.chunker.chunk_document(clean_text)

        except Exception as e:
            print(f"pypdf parsing failed for {filepath}: {e}")
            return []

    def _process_csv(self, filepath: str) -> list[str]:
        """Converts CSV/TSV files to plain text for chunking."""
        try:
            delimiter = '\t' if filepath.lower().endswith('.tsv') else ','
            rows = []
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    parts = line.split(delimiter)
                    text_line = ' | '.join(part.strip() for part in parts if part.strip())
                    if text_line:
                        rows.append(text_line)

            raw_text = '\n'.join(rows)
            clean_text = self._clean_text(raw_text)

            if not clean_text:
                return []

            return self.chunker.chunk_document(clean_text)

        except Exception as e:
            print(f"CSV/TSV parsing failed for {filepath}: {e}")
            return []

    def _process_plain_text(self, filepath: str) -> list[str]:
        """Reads standard text files safely."""
        try:
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                raw_text = f.read()

            clean_text = self._clean_text(raw_text)

            if not clean_text:
                return []

            return self.chunker.chunk_document(clean_text)
        except Exception as e:
            print(f"Text parsing failed for {filepath}: {e}")
            return []

    def _clean_text(self, raw_text: str) -> str:
        """Cleans up extracted text formatting."""
        if not raw_text:
            return ""

        # Strip trailing whitespaces per line
        lines = [line.strip() for line in raw_text.splitlines()]
        text = "\n".join(lines)

        # Remove excessive empty lines
        cleaned_text = re.sub(r'\n{3,}', '\n\n', text)

        return cleaned_text.strip()