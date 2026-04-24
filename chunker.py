import math
import re
from transformers import AutoTokenizer
import sentencepiece


# TODO:
#  find a dynamic way to switch model by model used

model_id = "google/gemma-3-4b-it"

class DocumentChunker:
    def __init__(self, model_name="mistralai/Ministral-3-14B-Instruct-2512", max_tokens=1000, overlap_tokens=100):
        self.max_tokens = max_tokens
        self.overlap_tokens = overlap_tokens

        # This is the "Automation"
        print(f"Loading tokenizer for: {model_name}")
        self.tokenizer = AutoTokenizer.from_pretrained(model_name)

    def count_tokens(self, text: str) -> int:
        return len(self.tokenizer.encode(text))

    def chunk_document(self, text: str) -> list[str]:
        # Split by double newlines to find paragraphs
        paragraphs = re.split(r'\n\s*\n', text.strip())
        final_chunks = []

        # This buffer will hold small paragraphs until we hit a big one
        small_paragraph_buffer = []

        for p in paragraphs:
            p = p.strip()
            if not p:
                continue

            # Define "small" as 3 words or fewer
            word_count = len(p.split())

            if word_count <= 3:
                # Accumulate small paragraphs (like headers or titles)
                small_paragraph_buffer.append(p)
            else:
                # We found a "big" paragraph!
                # Combine it with whatever was in the buffer
                if small_paragraph_buffer:
                    combined_text = "\n".join(small_paragraph_buffer) + "\n" + p
                    small_paragraph_buffer = [] # Clear the buffer
                else:
                    combined_text = p

                # Now process the combined text normally
                if self.count_tokens(combined_text) <= self.max_tokens:
                    final_chunks.append(combined_text)
                else:
                    # If the combined block is too big, use the fallback sentence splitter
                    final_chunks.extend(self._fallback_sentence_split(combined_text))

        # If the document ends with small paragraphs (and no big one follows)
        # we don't want to lose them, so we add them as a final chunk.
        if small_paragraph_buffer:
            final_chunks.append("\n".join(small_paragraph_buffer))

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