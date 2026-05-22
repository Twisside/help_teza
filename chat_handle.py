import json
import os
from datetime import datetime


class ChatSession:
    def __init__(self, db, max_window=10, state_path="./conversation_state.json", preprocessor=None):
        self.db = db
        self.max_window = max_window
        self.state_path = state_path
        self.messages = []
        self.preprocessor = preprocessor

    def add_message(self, role: str, content: str) -> None:
        self.messages.append({
            "role": role,
            "content": content,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })

        if len(self.messages) > self.max_window:
            excess = self.messages[:-self.max_window]
            self._archive_to_qdrant(excess)
            self.messages = self.messages[-self.max_window:]

    def search_context(self, query: str, user_limit: int = 5, archive_limit: int = 3) -> dict:
        user_results = self.db.search("user_entries", query, limit=user_limit)
        archive_results = self.db.search_conversation_archive(query, limit=archive_limit)

        return {
            "user_entries": user_results,
            "conversation_archive": archive_results
        }

    def build_system_prompt(self, query: str, context_results: dict) -> str:
        now = datetime.now()
        query_had_time_trigger = self.preprocessor and self.preprocessor.should_preprocess(query)

        system_parts = [
            f"You are a helpful assistant. The current date and time is {now}.",
            "Answer the user's question based ONLY on the provided context.",
            "Pay attention to the dates provided in the context; if there is conflicting information,",
            "prioritize the most recent entry unless asked otherwise.",
            "Use the current date as an anchor to resolve relative time references",
            "like 'yesterday', 'last week', or 'today' when looking at context timestamps."
        ]

        context_lines = []

        for res in context_results.get("user_entries", []):
            payload = res["payload"]
            content = payload.get("content", "")
            timestamp = payload.get("timestamp", "Unknown Date")
            filename = payload.get("filename", "Manual Entry")
            score = res["score"]

            if query_had_time_trigger:
                content = self.preprocessor.preprocess_chunk(content, timestamp)

            context_lines.append(f"[Doc Score: {score:.2f}] [Recorded: {timestamp}] [Source: {filename}]\n{content}")

        for res in context_results.get("conversation_archive", []):
            payload = res["payload"]
            content = payload.get("content", "")
            score = res["score"]
            role = payload.get("role", "unknown")
            context_lines.append(f"[Chat Archive Score: {score:.2f}] [Role: {role}]\n{content}")

        if context_lines:
            system_parts.append("\n--- RELEVANT CONTEXT ---\n" + "\n\n---\n\n".join(context_lines))

        return "\n".join(system_parts)

    def build_conversation_history(self) -> list:
        history = []
        for msg in self.messages:
            history.append({
                "role": msg["role"],
                "content": msg["content"]
            })
        return history

    def get_history(self) -> list:
        return self.messages.copy()

    def clear(self) -> None:
        self.messages = []
        self.db.clear_conversation_archive()
        if os.path.exists(self.state_path):
            os.remove(self.state_path)

    def save(self) -> None:
        state = {
            "messages": self.messages,
            "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        with open(self.state_path, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)

    def load(self) -> bool:
        if not os.path.exists(self.state_path):
            return False

        try:
            with open(self.state_path, "r", encoding="utf-8") as f:
                state = json.load(f)
            self.messages = state.get("messages", [])
            return True
        except (json.JSONDecodeError, IOError):
            return False

    def _archive_to_qdrant(self, messages: list) -> None:
        for i, msg in enumerate(messages):
            content = f"{msg['role']}: {msg['content']}"
            role = msg["role"]
            turn_index = -1 - i

            combined_tags = ["conversation", f"role:{role}"]
            self.db.insert_to_conversation_archive(content, role, turn_index, combined_tags)