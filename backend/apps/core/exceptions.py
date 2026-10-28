from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler


def custom_exception_handler(exc, context):
    response = exception_handler(exc, context)

    if response is not None:
        response.data = {
            "type": f"about:blank",
            "title": response.data.get("detail", str(exc)),
            "status": response.status_code,
            "detail": response.data.get("detail", str(exc)),
        }
        # Add trace id if available
        request = context.get("request")
        if request and hasattr(request, "id"):
            response.data["trace_id"] = request.id

    return response
