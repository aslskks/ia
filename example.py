import requests

TAVILY_API_KEY = "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"

def perform_search(query: str, max_results: int = 5) -> str:
    try:
        resp = requests.post(
            "https://api.tavily.com/search",
            json={
                "api_key": TAVILY_API_KEY,
                "query": query,
                "max_results": max_results
            },
            timeout=5
        )
        resp.raise_for_status()
        data = resp.json()

        results = []

        for r in data.get("results", []):
            title = r.get("title", "No title")
            url = r.get("url", "")
            content = r.get("content", "")
            results.append(f"- {title}\n  {content}\n  ({url})")

        if not results:
            return f"[No results found for: {query}]"

        return f"[Tavily search: '{query}']\n" + "\n\n".join(results)

    except requests.exceptions.Timeout:
        return f"[Search timed out for: {query}]"
    except requests.exceptions.ConnectionError:
        return f"[Search connection failed for: {query}]"
    except Exception as e:
        return f"[Search failed: {e}]"


print(perform_search("what year is it"))