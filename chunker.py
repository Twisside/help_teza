import math
import re


class DocumentChunker:
    def __init__(self, max_tokens=500, overlap_tokens=50):
        self.max_tokens = max_tokens
        self.overlap_tokens = overlap_tokens

    def count_tokens(self, text: str) -> int:
        """Approximation: 1 token is roughly 4 characters in English."""
        return len(text) // 4

    def chunk_document(self, text: str) -> list[str]:
        """Main entry point: Splits by paragraph first."""
        # Normalize line endings and split by double line breaks
        paragraphs = re.split(r'\n\s*\n', text.strip())
        final_chunks = []

        for p in paragraphs:
            p = p.strip()
            if not p:
                continue

            if self.count_tokens(p) <= self.max_tokens:
                # Perfect size, add it directly
                final_chunks.append(p)
            else:
                # Paragraph is too big, apply fallback logic
                final_chunks.extend(self._fallback_sentence_split(p))

        return final_chunks

    def _fallback_sentence_split(self, text: str) -> list[str]:
        """Attempts to split a massive paragraph by sentences."""
        # Simple regex to split by period, question mark, or exclamation point
        sentences = re.split(r'(?<=[.!?]) +', text)
        chunks = []
        current_chunk = ""

        for sentence in sentences:
            # Check if this single sentence is an absolute monster
            if self.count_tokens(sentence) > self.max_tokens:
                # If we have a pending chunk, save it first
                if current_chunk:
                    chunks.append(current_chunk.strip())
                    current_chunk = ""
                # Apply your exact mathematical splitting logic here
                chunks.extend(self._hard_math_split(sentence))
                continue

            # Will adding this sentence push us over the limit?
            if self.count_tokens(current_chunk + " " + sentence) > self.max_tokens:
                chunks.append(current_chunk.strip())
                current_chunk = sentence  # Start a new chunk
            else:
                current_chunk += " " + sentence if current_chunk else sentence

        if current_chunk:
            chunks.append(current_chunk.strip())

        return chunks

    def _hard_math_split(self, text: str) -> list[str]:
        """Your mathematical splitting logic for unbreakable text walls."""
        total_tokens = self.count_tokens(text)

        # Calculate exactly how many chunks we need (your logic)
        num_chunks = math.ceil(total_tokens / self.max_tokens)

        # Find the mathematical target size per chunk
        target_tokens = math.ceil(total_tokens / num_chunks)
        target_chars = target_tokens * 4  # Convert back to character approximation
        overlap_chars = self.overlap_tokens * 4

        chunks = []
        start = 0
        text_length = len(text)

        while start < text_length:
            end = start + target_chars

            # Try to snap the cut to the nearest space so we don't slice a word in half
            if end < text_length:
                last_space = text.rfind(' ', start, end)
                if last_space != -1:
                    end = last_space

            chunks.append(text[start:end].strip())
            # Move forward, but step back slightly for the overlap
            start = end - overlap_chars

        return chunks