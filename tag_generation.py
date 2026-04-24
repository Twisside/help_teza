import requests
def generate_tags_with_llm(text_content):
    """Asks the local SLM to extract 2-3 concise keywords."""
    url = "http://127.0.0.1:1234/v1/chat/completions"
    prompt = f"Extract 2-3 highly specific categories or tags for this text. Return ONLY the tags separated by commas. No intro.\nText: {text_content[:500]}"

    try:
        response = requests.post(url, json={
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1
        }, timeout=10)
        raw_tags = response.json()['choices'][0]['message']['content']
        return [t.strip().lower() for t in raw_tags.split(',') if t.strip()]
    except:
        return ["auto-categorized"]