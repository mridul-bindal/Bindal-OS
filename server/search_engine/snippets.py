# Creates short text excerpts around matching query terms for search results.
def create_snippet(
    content: str,
    query_tokens: set[str],
    max_snippets: int = 3,
    snippet_window: int = 100,
) -> list[str]:
    lower_content = content.lower()
    snippets = []
    start_position = 0

    for token in query_tokens:
        position = lower_content.find(token, start_position)
        if position == -1:
            continue

        start_position = max(0, position - snippet_window // 2)
        end_position = min(len(content), position + snippet_window // 2)
        snippet = content[start_position:end_position].replace("\n", " ")
        snippets.append(snippet)
        start_position = position + len(token)

    return snippets[:max_snippets]
