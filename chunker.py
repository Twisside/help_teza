import math
import re
from transformers import AutoTokenizer
import sentencepiece

# Use the base repo for the tokenizer metadata
tokenizer = AutoTokenizer.from_pretrained("mistralai/Ministral-3-14B-Instruct-2512")

class DocumentChunker:
    def __init__(self, max_tokens=1000, overlap_tokens=100):
        self.max_tokens = max_tokens
        self.overlap_tokens = overlap_tokens

    def count_tokens(self, paragraph: str) -> int:
        """
        Translates a string of text into AI tokens and returns the exact count.
        """
        token_ids = tokenizer.encode(paragraph)
        return len(token_ids)

    def chunk_document(self, text: str) -> list[str]:
        paragraphs = re.split(r'\n\s*\n', text.strip())
        final_chunks = []

        for p in paragraphs:
            p = p.strip()
            if not p:
                continue

            if self.count_tokens(p) <= self.max_tokens:
                final_chunks.append(p)
            else:
                final_chunks.extend(self._fallback_sentence_split(p))

        return final_chunks

    def _fallback_sentence_split(self, text: str) -> list[str]:
        sentences = re.split(r'(?<=[.!?]) +', text)
        chunks = []
        current_chunk = ""

        for sentence in sentences:

            if self.count_tokens(sentence) > self.max_tokens:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                    current_chunk = ""
                chunks.extend(self._hard_math_split(sentence))
                continue

            if self.count_tokens(current_chunk + " " + sentence) > self.max_tokens:
                chunks.append(current_chunk.strip())
                current_chunk = sentence
            else:
                current_chunk += " " + sentence if current_chunk else sentence

        if current_chunk:
            chunks.append(current_chunk.strip())

        return chunks

    def _hard_math_split(self, text: str) -> list[str]:

        total_tokens = self.count_tokens(text)
        num_chunks = math.ceil(total_tokens / self.max_tokens)
        target_tokens = math.ceil(total_tokens / num_chunks)
        target_chars = target_tokens * 4
        overlap_chars = self.overlap_tokens * 4

        chunks = []
        start = 0
        text_length = len(text)

        while start < text_length:
            end = start + target_chars
            if end < text_length:
                last_space = text.rfind(' ', start, end)
                if last_space != -1:
                    end = last_space

            chunks.append(text[start:end].strip())
            start = end - overlap_chars

        return chunks