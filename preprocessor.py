import re
from datetime import datetime, timedelta
from typing import Optional


class TimeAwarePreprocessor:
    TIME_TRIGGER_WORDS = [
        'when', 'what day', 'what date', 'date', 'today', 'tomorrow',
        'yesterday', 'next week', 'last week', 'this week', 'tonight',
        'this morning', 'this afternoon', 'this evening', 'next month',
        'last month', 'day after tomorrow', 'day before yesterday'
    ]

    RELATIVE_DAYS = {
        'today': 0,
        'tomorrow': 1,
        'yesterday': -1,
        'day after tomorrow': 2,
        'day before yesterday': -2
    }

    WEEKDAY_MAP = {
        'monday': 0, 'tuesday': 1, 'wednesday': 2, 'thursday': 3,
        'friday': 4, 'saturday': 5, 'sunday': 6
    }

    TIME_UNITS = {
        'second': 1, 'minute': 1, 'hour': 1, 'day': 1,
        'week': 7, 'month': 30, 'year': 365
    }

    def should_preprocess(self, text: str) -> bool:
        text_lower = text.lower()
        return any(trigger in text_lower for trigger in self.TIME_TRIGGER_WORDS)

    def _parse_date(self, date_str: Optional[str]) -> datetime:
        if not date_str or date_str == 'Unknown Date':
            return datetime.now()
        try:
            return datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            try:
                return datetime.strptime(date_str, "%Y-%m-%d")
            except ValueError:
                return datetime.now()

    def _format_date(self, dt: datetime) -> str:
        return dt.strftime("%d-%m-%Y")

    def _calculate_weekday_offset(self, weekday_name: str, reference_date: datetime, is_next: bool, is_last: bool) -> datetime:
        target_weekday = self.WEEKDAY_MAP.get(weekday_name.lower())
        if target_weekday is None:
            return reference_date

        current_weekday = reference_date.weekday()
        days_ahead = target_weekday - current_weekday

        if is_last:
            days_ahead -= 7
        elif is_next or (days_ahead <= 0 and not is_last):
            days_ahead += 7

        return reference_date + timedelta(days=days_ahead)

    def _replace_relative_times(self, text: str, reference_date: datetime) -> str:
        result = text

        day_pattern = r'\b(day after tomorrow|day before yesterday)\b'
        result = re.sub(day_pattern, lambda m: self._format_date(reference_date + timedelta(days=self.RELATIVE_DAYS[m.group(1)])), result, flags=re.IGNORECASE)

        for term, offset in self.RELATIVE_DAYS.items():
            if term == 'day after tomorrow' or term == 'day before yesterday':
                continue
            pattern = r'\b' + re.escape(term) + r'\b'
            result = re.sub(pattern, self._format_date(reference_date + timedelta(days=offset)), result, flags=re.IGNORECASE)

        this_pattern = r'\b(this|last|next)\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b'
        result = re.sub(this_pattern, lambda m: self._format_date(self._calculate_weekday_offset(
            m.group(2), reference_date, m.group(1) == 'next', m.group(1) == 'last'
        )), result, flags=re.IGNORECASE)

        future_pattern = r'\b(in|after)\s+(\d+)\s+(second|minute|hour|day|week|month)s?\b'
        result = re.sub(future_pattern, lambda m: self._format_date(reference_date + timedelta(
            days=int(m.group(2)) * self.TIME_UNITS.get(m.group(3), 1)
        )), result, flags=re.IGNORECASE)

        past_pattern = r'\b(\d+)\s+(second|minute|hour|day|week|month)s?\s+ago\b'
        result = re.sub(past_pattern, lambda m: self._format_date(reference_date - timedelta(
            days=int(m.group(1)) * self.TIME_UNITS.get(m.group(2), 1)
        )), result, flags=re.IGNORECASE)

        week_pattern = r'\b(this|next|last)\s+week\b'
        result = re.sub(week_pattern, lambda m: self._week_range(reference_date, m.group(1)), result, flags=re.IGNORECASE)

        month_pattern = r'\b(this|next|last)\s+month\b'
        result = re.sub(month_pattern, lambda m: self._month_reference(reference_date, m.group(1)), result, flags=re.IGNORECASE)

        return result

    def _week_range(self, reference_date: datetime, modifier: str) -> str:
        if modifier == 'this':
            start = reference_date - timedelta(days=reference_date.weekday())
            return f"{self._format_date(start)} to {self._format_date(start + timedelta(days=6))}"
        elif modifier == 'next':
            start = reference_date + timedelta(days=7 - reference_date.weekday())
            return f"{self._format_date(start)} to {self._format_date(start + timedelta(days=6))}"
        elif modifier == 'last':
            start = reference_date - timedelta(days=reference_date.weekday() + 7)
            return f"{self._format_date(start)} to {self._format_date(start + timedelta(days=6))}"
        return reference_date.strftime("%Y-%m-%d")

    def _month_reference(self, reference_date: datetime, modifier: str) -> str:
        if modifier == 'this':
            return reference_date.strftime("%B %Y")
        elif modifier == 'next':
            next_month = reference_date.replace(day=1)
            if reference_date.month == 12:
                next_month = next_month.replace(year=reference_date.year + 1, month=1)
            else:
                next_month = next_month.replace(month=reference_date.month + 1)
            return next_month.strftime("%B %Y")
        elif modifier == 'last':
            last_month = reference_date.replace(day=1)
            if reference_date.month == 1:
                last_month = last_month.replace(year=reference_date.year - 1, month=12)
            else:
                last_month = last_month.replace(month=reference_date.month - 1)
            return last_month.strftime("%B %Y")
        return reference_date.strftime("%B %Y")

    def preprocess_query(self, query: str) -> str:
        return self._replace_relative_times(query, datetime.now())

    def preprocess_chunk(self, chunk: str, chunk_timestamp: Optional[str] = None) -> str:
        reference_date = self._parse_date(chunk_timestamp)
        return self._replace_relative_times(chunk, reference_date)

    def preprocess_batch(self, chunks: list[dict]) -> list[dict]:
        processed = []
        for chunk in chunks:
            content = chunk.get('content', '')
            timestamp = chunk.get('timestamp')
            processed_content = self.preprocess_chunk(content, timestamp)
            processed.append({
                **chunk,
                'content': processed_content
            })
        return processed