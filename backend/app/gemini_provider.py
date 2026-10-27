"""Google Gemini multimodal extraction provider with canonical contract normalization."""

import base64
import json
import logging
import re
import time
import httpx
import fitz

from .db import SessionLocal
from .crypto import decrypt
from .storage import store, original_key, fitz_open_original
from .extraction_prompts import (
    DEFAULT_INSTRUCTION,
    system_instruction,
    reading_instructions,
    prompt_manifest,
)
from .extraction.connector_repository import SqlConnectorRepository
from .provider import ProcessingIssue
from .spider_provider import (
    field_catalog,
    field_guidance,
    field_types,
    _render_page_jpeg,
)

log = logging.getLogger("sqe.gemini")


def normalize_gemini_json(raw_text):
    """Sanitize and parse JSON from Gemini, handling markdown code fences."""
    text = raw_text.strip()
    # Strip markdown ```json ... ``` or ``` ... ```
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
        text = text.strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        # Fallback regex extraction of JSON object
        match = re.search(r"(\{.*\})", text, re.DOTALL)
        if match:
            data = json.loads(match.group(1))
        else:
            raise ProcessingIssue(f"Gemini returned non-JSON text: {text[:200]}") from exc

    if not isinstance(data, dict):
        raise ProcessingIssue("Gemini response did not contain a JSON object.")

    # Canonicalize output structure
    if "extract_result" in data:
        extract_result = data["extract_result"]
        classification = data.get("classification")
        locations = data.get("_field_locations", {})
    else:
        # Whole object is extract result
        extract_result = {k: v for k, v in data.items() if k not in {"classification", "_field_locations"}}
        classification = data.get("classification")
        locations = data.get("_field_locations", {})

    return extract_result, classification, locations


def run_gemini(doc, cfg, heartbeat):
    """Execute document classification and extraction with Google Gemini."""
    connection = SqlConnectorRepository(SessionLocal, decrypt).read(doc.org, "gemini")
    key, options = connection.api_key, connection.options
    if not key:
        raise ProcessingIssue(
            "Google Gemini API key is not configured. Register it under Configuration -> Connector."
        )

    base_url = options.get("base_url", "https://generativelanguage.googleapis.com/v1beta").rstrip("/")
    model_id = options.get("model_id", "gemini-2.5-pro")
    timeout = options.get("timeout_seconds", 120)
    max_pixels = options.get("image_max_pixels", 2400)
    jpeg_quality = options.get("image_jpeg_quality", 85)

    # 1. Render pages to JPEG
    page_images = []
    with fitz_open_original(store().read(original_key(doc))) as pdf:
        page_count = len(pdf)
        if page_count < 1 or page_count > 30:
            raise ProcessingIssue("Gemini extraction supports 1-30 pages per document.")
        for number, page in enumerate(pdf, 1):
            heartbeat()
            data = _render_page_jpeg(page, number, max_pixels, jpeg_quality, max_image_bytes=4 * 1024 * 1024)
            page_images.append(data)

    heartbeat()

    # 2. Build extraction prompt
    profile = cfg.get("profiles", {}).get(doc.doc_type, {})
    schema = profile.get("schema", {})
    system_text = (
        profile.get("system_prompt")
        or profile.get("system_instruction")
        or DEFAULT_INSTRUCTION
    )
    instruction_payload = {
        "target_document_type": doc.doc_type,
        "schema_catalog": field_catalog(schema),
        "field_instructions": field_guidance(schema),
        "field_types": field_types(schema),
        "reading_guidance": reading_instructions(doc.doc_type, cfg),
    }

    user_text = (
        f"{system_text}\n\n"
        "Analyze the provided document page images carefully. Extract all requested fields exactly according to the schema.\n"
        "Return ONLY a valid JSON object with the following top-level structure:\n"
        "{\n"
        '  "extract_result": { <extracted fields conforming to schema> },\n'
        '  "classification": { "doc_type": "' + doc.doc_type + '", "confidence": 1.0 },\n'
        '  "_field_locations": { "<field_path>": [ymin, xmin, ymax, xmax] }\n'
        "}\n\n"
        "SCHEMA & FIELD INSTRUCTIONS:\n" + json.dumps(instruction_payload, indent=2)
    )

    # 3. Call Gemini
    # Check if OpenAI-compatible proxy or native Google REST endpoint
    is_openai_mode = "openai" in base_url or base_url.endswith("/v1")

    headers = {"Content-Type": "application/json"}
    if is_openai_mode:
        headers["Authorization"] = f"Bearer {key}"
        url = f"{base_url}/chat/completions"
        content_parts = [{"type": "text", "text": user_text}]
        for img_bytes in page_images:
            b64 = base64.b64encode(img_bytes).decode("ascii")
            content_parts.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{b64}"}
            })
        payload = {
            "model": model_id,
            "messages": [{"role": "user", "content": content_parts}],
            "temperature": options.get("temperature", 0.1),
            "max_tokens": options.get("max_tokens", 16384),
        }
    else:
        # Native Google Generative Language REST API
        url = f"{base_url}/models/{model_id}:generateContent?key={key}"
        parts = [{"text": user_text}]
        for img_bytes in page_images:
            b64 = base64.b64encode(img_bytes).decode("ascii")
            parts.append({
                "inline_data": {
                    "mime_type": "image/jpeg",
                    "data": b64
                }
            })
        payload = {
            "contents": [{"role": "user", "parts": parts}],
            "generationConfig": {
                "temperature": options.get("temperature", 0.1),
                "topP": options.get("top_p", 0.95),
                "maxOutputTokens": options.get("max_tokens", 16384),
                "responseMimeType": "application/json",
            }
        }

    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.post(url, headers=headers, json=payload)
            if resp.status_code != 200:
                raise ProcessingIssue(f"Google Gemini request failed ({resp.status_code}): {resp.text[:300]}")
            resp_data = resp.json()
    except httpx.RequestError as exc:
        raise ProcessingIssue(f"Network error connecting to Google Gemini: {exc}") from exc

    # 4. Extract generated text
    if is_openai_mode:
        choices = resp_data.get("choices", [])
        if not choices:
            raise ProcessingIssue("Gemini returned no completions.")
        raw_output = choices[0].get("message", {}).get("content", "")
    else:
        candidates = resp_data.get("candidates", [])
        if not candidates:
            raise ProcessingIssue("Gemini returned no candidate outputs.")
        content = candidates[0].get("content", {})
        parts = content.get("parts", [])
        raw_output = parts[0].get("text", "") if parts else ""

    # 5. Normalize
    extract_result, classification, locations = normalize_gemini_json(raw_output)

    if not classification:
        classification = {"doc_type": doc.doc_type, "confidence": 1.0}

    response_payload = {
        "extract_result": extract_result,
        "_field_locations": locations,
        "page_count": page_count,
        "provider": "gemini",
        "model": model_id,
    }

    return response_payload, classification


def test_gemini_ping(api_key, base_url, model_id):
    """Verify Gemini connection and credentials with a 1-token probe request."""
    start = time.time()
    url = f"{base_url.rstrip('/')}/models/{model_id}:generateContent?key={api_key}"
    payload = {
        "contents": [{"role": "user", "parts": [{"text": "ping"}]}],
        "generationConfig": {"maxOutputTokens": 2}
    }
    try:
        with httpx.Client(timeout=15) as client:
            resp = client.post(url, json=payload)
            latency_ms = int((time.time() - start) * 1000)
            if resp.status_code == 200:
                return {"success": True, "latency_ms": latency_ms, "model": model_id}
            return {"success": False, "error": f"HTTP {resp.status_code}: {resp.text[:200]}"}
    except Exception as exc:
        return {"success": False, "error": str(exc)}
