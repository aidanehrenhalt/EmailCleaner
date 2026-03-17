"""Gmail API wrapper: listing, header fetching, and bulk operations."""

import time
from collections.abc import Iterator

from googleapiclient.errors import HttpError
from googleapiclient.http import BatchHttpRequest


def _retry_on_rate_limit(func, max_retries=5):
    """Call func(), retrying with exponential backoff on 429/500/503."""
    delay = 1
    for attempt in range(max_retries + 1):
        try:
            return func()
        except HttpError as e:
            if e.resp.status in (429, 500, 503) and attempt < max_retries:
                time.sleep(delay)
                delay = min(delay * 2, 32)
            else:
                raise


def list_message_ids(
    service,
    query: str = "",
    label_ids: list[str] | None = None,
    limit: int = 0,
) -> Iterator[str]:
    """Yield message IDs matching the query, handling pagination.

    Args:
        service: Authenticated Gmail API service.
        query: Gmail search query string (e.g. 'category:promotions').
        label_ids: Filter to specific label IDs.
        limit: Maximum number of IDs to yield (0 = unlimited).
    """
    count = 0
    page_token = None

    while True:
        kwargs = {"userId": "me", "maxResults": 500}
        if query:
            kwargs["q"] = query
        if label_ids:
            kwargs["labelIds"] = label_ids
        if page_token:
            kwargs["pageToken"] = page_token

        result = _retry_on_rate_limit(
            lambda: service.users().messages().list(**kwargs).execute()
        )

        messages = result.get("messages", [])
        for msg in messages:
            yield msg["id"]
            count += 1
            if limit and count >= limit:
                return

        page_token = result.get("nextPageToken")
        if not page_token:
            return


def get_message_headers(
    service,
    message_ids: list[str],
    batch_size: int = 50,
    on_batch_done=None,
) -> list[dict]:
    """Fetch From/Subject/Date headers for message IDs using batch requests.

    Args:
        service: Authenticated Gmail API service.
        message_ids: List of message IDs to fetch.
        batch_size: Number of messages per batch request.
        on_batch_done: Optional callback(fetched_so_far, total) for progress.

    Returns:
        List of dicts with keys: id, from_header, subject, date.
    """
    results = []
    total = len(message_ids)

    for i in range(0, total, batch_size):
        chunk = message_ids[i : i + batch_size]
        batch_results = []

        def _make_callback(batch_list):
            def callback(request_id, response, exception):
                if exception:
                    return  # Skip failed messages
                headers = {}
                for h in response.get("payload", {}).get("headers", []):
                    name = h["name"].lower()
                    if name in ("from", "subject", "date"):
                        headers[name] = h["value"]
                batch_list.append(
                    {
                        "id": response["id"],
                        "from_header": headers.get("from", ""),
                        "subject": headers.get("subject", "(no subject)"),
                        "date": headers.get("date", ""),
                    }
                )

            return callback

        def _execute_batch():
            batch = service.new_batch_http_request(
                callback=_make_callback(batch_results)
            )
            for msg_id in chunk:
                batch.add(
                    service.users()
                    .messages()
                    .get(
                        userId="me",
                        id=msg_id,
                        format="metadata",
                        metadataHeaders=["From", "Subject", "Date"],
                    )
                )
            batch.execute()

        _retry_on_rate_limit(_execute_batch)
        results.extend(batch_results)

        if on_batch_done:
            on_batch_done(len(results), total)

        # Small delay between batches to stay within rate limits
        if i + batch_size < total:
            time.sleep(0.1)

    return results


def batch_trash(service, message_ids: list[str]) -> int:
    """Move messages to trash using batchModify (up to 1000 per call).

    Returns the number of messages trashed.
    """
    trashed = 0
    for i in range(0, len(message_ids), 1000):
        chunk = message_ids[i : i + 1000]
        _retry_on_rate_limit(
            lambda: service.users()
            .messages()
            .batchModify(
                userId="me",
                body={"ids": chunk, "addLabelIds": ["TRASH"]},
            )
            .execute()
        )
        trashed += len(chunk)
    return trashed


def batch_delete(service, message_ids: list[str]) -> int:
    """Permanently delete messages using batchDelete (up to 1000 per call).

    Requires full mail scope. Returns the number of messages deleted.
    """
    deleted = 0
    for i in range(0, len(message_ids), 1000):
        chunk = message_ids[i : i + 1000]
        _retry_on_rate_limit(
            lambda: service.users()
            .messages()
            .batchDelete(userId="me", body={"ids": chunk})
            .execute()
        )
        deleted += len(chunk)
    return deleted
