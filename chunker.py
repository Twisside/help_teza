import math
import re
from langchain_text_splitters import Language, RecursiveCharacterTextSplitter
from tree_sitter import Language as TSLanguage, Parser
import tree_sitter_python as tspython
import tree_sitter_javascript as tsjavascript
import tree_sitter_c_sharp as tscsharp


class DocumentChunker:
    def __init__(self, max_tokens=1000, overlap_tokens=100):
        """
        Initializes the chunking engine using a fast, dependency-free character heuristic.
        (1 Token = 4 Characters)
        """
        self.max_tokens = max_tokens
        self.overlap_tokens = overlap_tokens

        # Pre-calculate character limits based on the 4-chars-per-token rule
        self.max_chars = self.max_tokens * 4
        self.overlap_chars = self.overlap_tokens * 4

        print(f"Chunker initialized: Max {self.max_chars} chars, Overlap {self.overlap_chars} chars.")

        # Map file extensions to LangChain's syntax-aware splitters
        self.langchain_map = {
            ".py": Language.PYTHON,
            ".js": Language.JS,
            ".cs": Language.CSHARP,
        }

        # Initialize Tree-sitter parsers for AST extraction
        self.ts_parsers = {}
        try:
            self.ts_parsers[".py"] = Parser(TSLanguage(tspython.language()))
            self.ts_parsers[".js"] = Parser(TSLanguage(tsjavascript.language()))
            self.ts_parsers[".cs"] = Parser(TSLanguage(tscsharp.language()))
        except Exception as e:
            print(f"Warning: Failed to load Tree-sitter parsers. {e}")

    def count_tokens(self, text: str) -> int:
        """
        Estimates the exact number of tokens using the standard 4-character rule.
        Uses math.ceil to err on the side of caution (rounding up).
        """
        return math.ceil(len(text) / 4)

    def _get_langchain_splitter(self, extension: str):
        """
        Creates a language-specific text splitter with overlapping capabilities.
        Uses the pre-calculated character limits.
        """
        lang = self.langchain_map.get(extension, Language.PYTHON)

        return RecursiveCharacterTextSplitter.from_language(
            language=lang,
            chunk_size=self.max_chars,
            chunk_overlap=self.overlap_chars
        )

    def chunk_code(self, text: str, extension: str) -> list[str]:
        """
        Executes hybrid code chunking using AST parsing and overlapping fallbacks.
        """
        parser = self.ts_parsers.get(extension)

        # Fallback to pure LangChain if language isn't supported by Tree-sitter
        if not parser:
            splitter = self._get_langchain_splitter(extension)
            return splitter.split_text(text)

        tree = parser.parse(bytes(text, "utf8"))
        root_node = tree.root_node

        target_node_types = [
            'function_definition', 'class_definition', 'method_declaration',
            'function_declaration', 'arrow_function', 'declaration'
        ]

        logical_blocks = []

        def traverse_tree(node):
            if node.type in target_node_types:
                block_text = text[node.start_byte:node.end_byte]
                logical_blocks.append(block_text)
                return

            for child in node.children:
                traverse_tree(child)

        traverse_tree(root_node)

        if not logical_blocks:
            logical_blocks = [text]

        final_chunks = []
        langchain_fallback = self._get_langchain_splitter(extension)

        for block in logical_blocks:
            # Check length using the fast character estimation
            if len(block) <= self.max_chars:
                final_chunks.append(block)
            else:
                sub_chunks = langchain_fallback.split_text(block)
                final_chunks.extend(sub_chunks)

        return final_chunks

    def chunk_document(self, text: str) -> list[str]:
        """Standard document chunking using the fast 4-character rule."""
        paragraphs = re.split(r'\n\s*\n', text.strip())
        final_chunks = []
        small_paragraph_buffer = []

        for p in paragraphs:
            p = p.strip()
            if not p:
                continue

            word_count = len(p.split())

            if word_count <= 3:
                small_paragraph_buffer.append(p)
            else:
                if small_paragraph_buffer:
                    combined_text = "\n".join(small_paragraph_buffer) + "\n" + p
                    small_paragraph_buffer = []
                else:
                    combined_text = p

                # Estimate size quickly using length instead of tokenizer
                if len(combined_text) <= self.max_chars:
                    final_chunks.append(combined_text)
                else:
                    final_chunks.extend(self._fallback_sentence_split(combined_text))

        if small_paragraph_buffer:
            final_chunks.append("\n".join(small_paragraph_buffer))

        return final_chunks

    def _fallback_sentence_split(self, text: str) -> list[str]:
        """Sentence splitter fallback using character limits."""
        sentences = re.split(r'(?<=[.!?]) +', text)
        chunks = []
        current_chunk = ""

        for sentence in sentences:
            if len(sentence) > self.max_chars:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                    current_chunk = ""
                chunks.extend(self._hard_math_split(sentence))
                continue

            if len(current_chunk + " " + sentence) > self.max_chars:
                chunks.append(current_chunk.strip())
                current_chunk = sentence
            else:
                current_chunk += " " + sentence if current_chunk else sentence

        if current_chunk:
            chunks.append(current_chunk.strip())

        return chunks

    def _hard_math_split(self, text: str) -> list[str]:
        """Final failsafe: hard cuts using character math."""
        chunks = []
        start = 0
        text_length = len(text)

        while start < text_length:
            end = start + self.max_chars
            if end < text_length:
                last_space = text.rfind(' ', start, end)
                if last_space != -1:
                    end = last_space

            chunks.append(text[start:end].strip())
            start = end - self.overlap_chars

        return chunks