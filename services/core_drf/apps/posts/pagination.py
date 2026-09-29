from rest_framework.pagination import CursorPagination

class CursorPaginationByCreatedAt(CursorPagination):
    """
    Keyset / Cursor-Based Pagination for Feed & Post endpoints.
    Eliminates O(N) OFFSET scan penalties and prevents duplicates upon new writes.
    Seeks directly on indexed (created_at, id) tuple.
    """
    page_size = 20
    page_size_query_param = 'limit'
    max_page_size = 50
    ordering = '-created_at'
    cursor_query_param = 'cursor'
