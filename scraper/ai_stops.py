import json
import os

from google import genai
from google.genai import types

# Ordered newest/most capable first. A 429 (quota exceeded) response
# advances to the next entry instead of retrying the same model; any
# other error is treated as terminal for that call, not a signal to try
# the next model. gemini-3-flash-preview is deprecated in favor of
# gemini-3.5-flash but is kept as a fallback since it may still serve
# requests; gemini-2.5-flash is the last resort as the oldest model here
# still generally available.
MODEL_FALLBACK_LIST = [
    "gemini-3.5-flash",
    "gemini-3.1-pro-preview",
    "gemini-3-flash-preview",
    "gemini-2.5-flash",
]

RESPONSE_SCHEMA = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "index": {"type": "integer"},
            "stops": {
                "anyOf": [
                    {"type": "integer", "minimum": 0},
                    {"type": "null"},
                ]
            },
        },
        "required": ["index", "stops"],
    },
}

PROMPT_TEMPLATE = (
    "Each numbered block is the raw visible text of one flight search "
    "result card from a travel booking site. For each one, work out how "
    "many stops (layovers) that flight has, using anything in the text "
    "that implies it: an explicit stop count, the words nonstop or direct, "
    "a connecting-city name, multiple flight numbers or airline codes, "
    "wording in any language, etc.\n\n"
    "Respond with one entry per block. Use 0 for a nonstop or direct "
    "flight, the stop count for a connecting flight, or null if the text "
    "gives no way to tell.\n\n"
    "{cards}"
)

_client = None
_model_index = 0


def _get_client():
    global _client
    if _client is not None:
        return _client
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        return None
    _client = genai.Client(api_key=api_key)
    return _client


def _is_quota_exceeded_error(err):
    if getattr(err, "code", None) == 429:
        return True
    return "429" in str(err)


def _build_prompt(card_texts):
    cards = "\n\n".join(f"[{i}]\n{text}" for i, text in enumerate(card_texts))
    return PROMPT_TEMPLATE.format(cards=cards)


def _parse_response(response_text):
    return {item["index"]: item["stops"] for item in json.loads(response_text)}


_missing_key_warned = False


def infer_stops(card_texts):
    """Ask Gemini how many stops each flight has.

    card_texts is a plain list of raw card text. The returned dict is
    keyed by position in that list, not by any id the caller may have -
    callers passing a filtered subset are responsible for mapping the
    result back to their own indices.
    """
    global _model_index, _missing_key_warned

    if not card_texts:
        return {}

    client = _get_client()
    if client is None:
        if not _missing_key_warned:
            print("GEMINI_API_KEY is not set — flights the regex can't classify will stay as unknown stops")
            _missing_key_warned = True
        return {}

    prompt = _build_prompt(card_texts)

    while _model_index < len(MODEL_FALLBACK_LIST):
        model = MODEL_FALLBACK_LIST[_model_index]
        try:
            response = client.models.generate_content(
                model=model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_json_schema=RESPONSE_SCHEMA,
                ),
            )
            return _parse_response(response.text)
        except Exception as exc:
            if _is_quota_exceeded_error(exc):
                print(f"Gemini model {model} is over quota, trying the next fallback model")
                _model_index += 1
                continue
            print(f"Gemini stop inference failed on {model}: {exc}")
            return {}

    print("All Gemini fallback models are over quota, skipping AI stop inference")
    return {}
