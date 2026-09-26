"""OpenRouter image-generation client using only the standard library.

Endpoint follows the OpenAI-compatible images API that OpenRouter exposes:
    POST https://openrouter.ai/api/v1/images/generations
    Authorization: Bearer <OPENROUTER_API_KEY>
"""

import base64
import json
import urllib.error
import urllib.request

IMAGES_URL = "https://openrouter.ai/api/v1/images/generations"
DEFAULT_IMAGE_MODEL = "black-forest-labs/flux-schnell"


class OpenRouterError(RuntimeError):
    pass


def generate_image(prompt: str, api_key: str, model: str = DEFAULT_IMAGE_MODEL,
                   size: str = "1024x1024", n: int = 1) -> bytes:
    """Generate one image and return its raw bytes (PNG/JPEG/WebP).

    Raises OpenRouterError with a human-readable message on failure.
    """
    if not api_key:
        raise OpenRouterError("OpenRouter API key is not set (Menu → Settings → AI).")

    payload = {"model": model, "prompt": prompt, "n": n, "size": size}
    req = urllib.request.Request(
        IMAGES_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        raise OpenRouterError(f"OpenRouter HTTP {e.code}: {body[:400]}") from e
    except urllib.error.URLError as e:
        raise OpenRouterError(f"OpenRouter request failed: {e.reason}") from e

    items = (data or {}).get("data") or []
    if not items:
        raise OpenRouterError(f"OpenRouter returned no image: {json.dumps(data)[:300]}")

    first = items[0]
    if first.get("b64_json"):
        return base64.b64decode(first["b64_json"])

    url = first.get("url")
    if not url:
        raise OpenRouterError(f"OpenRouter image has no url/b64_json: {json.dumps(first)[:300]}")

    try:
        with urllib.request.urlopen(url, timeout=180) as resp:
            return resp.read()
    except urllib.error.URLError as e:
        raise OpenRouterError(f"Failed to download generated image: {e.reason}") from e
