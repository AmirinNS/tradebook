from flask import jsonify, render_template, request
from werkzeug.exceptions import HTTPException, default_exceptions


def _prefers_json():
    """Determine whether the incoming request expects a JSON error response."""
    if request.path.startswith("/api/"):
        return True
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return True
    accept = request.accept_mimetypes
    return accept["application/json"] > accept["text/html"]


def _extract_retry_after(err):
    """Extract Retry-After header value if present on the exception."""
    retry_after = getattr(err, "retry_after", None)
    if retry_after is not None:
        return str(retry_after)
    if hasattr(err, "get_headers"):
        for header, value in err.get_headers():
            if header.lower() == "retry-after":
                return str(value)
    return None


def handle_error(err):
    """Handle an HTTP error, returning JSON or HTML with appropriate headers."""
    if isinstance(err, HTTPException):
        code = err.code or 500
        heading = err.name or "Error"
        message = err.description or "An error occurred."
    else:
        code = 500
        heading = "Internal Server Error"
        message = "An unexpected server error occurred."

    headers = {}
    if code == 429:
        retry_val = _extract_retry_after(err)
        if retry_val:
            headers["Retry-After"] = retry_val

    if _prefers_json():
        payload = {"error": {"code": code, "message": message}}
        return jsonify(payload), code, headers

    try:
        body = render_template(
            "error.html",
            code=code,
            heading=heading,
            status_label=heading,
            message=message,
        )
        return body, code, headers
    except Exception:
        plain_headers = {**headers, "Content-Type": "text/plain; charset=utf-8"}
        return f"{code} {heading}\n{message}\n", code, plain_headers


def init_errors(app):
    """Register custom error handlers on the Flask app for every HTTP error code."""
    for code in default_exceptions:
        app.register_error_handler(code, handle_error)
    app.register_error_handler(HTTPException, handle_error)
