from rest_framework.pagination import CursorPagination as DRFCursorPagination


class CursorPagination(DRFCursorPagination):
    page_size = 50
    ordering = "-created_at"
    page_size_query_param = "page_size"
    max_page_size = 100
