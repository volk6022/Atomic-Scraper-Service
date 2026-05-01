import re


def clean_html_content(html: str) -> str:
    content = html
    content = re.sub(
        r"<script[^>]*>.*?</script>", "", content, flags=re.DOTALL | re.IGNORECASE
    )
    content = re.sub(
        r"<style[^>]*>.*?</style>", "", content, flags=re.DOTALL | re.IGNORECASE
    )
    content = re.sub(r"<!--.*?-->", "", content, flags=re.DOTALL)
    content = re.sub(
        r"<noscript[^>]*>.*?</noscript>", "", content, flags=re.DOTALL | re.IGNORECASE
    )
    content = re.sub(
        r"<iframe[^>]*>.*?</iframe>", "", content, flags=re.DOTALL | re.IGNORECASE
    )
    content = re.sub(r"<[^>]+>", "", content)
    content = re.sub(r"\s+", " ", content)
    return content.strip()


def html_to_text(html: str) -> str:
    content = clean_html_content(html)
    content = re.sub(r"<br\s*/?>", "\n", content, flags=re.IGNORECASE)
    content = re.sub(r"</p>", "\n\n", content, flags=re.IGNORECASE)
    content = re.sub(r"</div>", "\n", content, flags=re.IGNORECASE)
    content = re.sub(r"</li>", "\n", content, flags=re.IGNORECASE)
    content = re.sub(r"</h[1-6]>", "\n\n", content, flags=re.IGNORECASE)
    content = re.sub(r"<[^>]+>", "", content)
    content = re.sub(r"\n\s*\n", "\n\n", content)
    content = re.sub(r"[ \t]+", " ", content)
    content = content.strip()
    return content


def count_words(text: str) -> int:
    words = re.findall(r"\b\w+\b", text)
    return len(words)


def truncate_content(text: str, max_words: int = 500) -> str:
    words = text.split()
    if len(words) <= max_words:
        return text

    truncated_words = words[:max_words]
    while truncated_words and truncated_words[-1] in {".", "!", "?", ",", ";", ":"}:
        truncated_words.pop()

    result = " ".join(truncated_words)
    if truncated_words and result[-1] not in {".", "!", "?"}:
        result += "..."
    else:
        result += ".."

    return result
