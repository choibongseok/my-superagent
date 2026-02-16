"""Google Workspace API tools for document creation and manipulation."""

from collections.abc import Mapping, Sequence
import logging
from typing import Any, Callable

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

logger = logging.getLogger(__name__)


class GoogleDocsAPI:
    """
    Google Docs API wrapper for document creation and editing.

    Features:
        - Create new documents
        - Insert text content
        - Replace template placeholders in existing documents
        - Get document content

    Usage:
        api = GoogleDocsAPI(credentials)
        doc_id = api.create_document("My Report")
        api.insert_text(doc_id, "Content here")
        api.replace_template_variables(doc_id, {"name": "AgentHQ"})
    """

    def __init__(self, credentials: Credentials):
        """
        Initialize Google Docs API client.

        Args:
            credentials: OAuth2 credentials
        """
        self.credentials = credentials
        self.service = build("docs", "v1", credentials=credentials)
        logger.debug("Google Docs API client initialized")

    def create_document(self, title: str) -> str:
        """
        Create a new Google Doc.

        Args:
            title: Document title

        Returns:
            Document ID

        Raises:
            HttpError: If document creation fails
        """
        try:
            document = {"title": title}

            doc = self.service.documents().create(body=document).execute()
            doc_id = doc.get("documentId")

            logger.info("Created document '%s' with ID: %s", title, doc_id)
            return doc_id

        except HttpError as error:
            logger.error("Failed to create document: %s", error)
            raise

    def insert_text(
        self,
        document_id: str,
        text: str,
        index: int = 1,
    ) -> dict[str, Any]:
        """
        Insert text into document.

        Args:
            document_id: Target document ID
            text: Text content to insert
            index: Insert position (default: 1, start of document)

        Returns:
            API response dictionary

        Raises:
            HttpError: If insertion fails
        """
        try:
            requests = [
                {
                    "insertText": {
                        "location": {
                            "index": index,
                        },
                        "text": text,
                    }
                }
            ]

            result = (
                self.service.documents()
                .batchUpdate(documentId=document_id, body={"requests": requests})
                .execute()
            )

            logger.debug(
                "Inserted %s characters into document %s", len(text), document_id
            )
            return result

        except HttpError as error:
            logger.error("Failed to insert text: %s", error)
            raise

    @staticmethod
    def _normalize_placeholder_token(token: Any, *, field_name: str) -> str:
        """Normalize placeholder prefix/suffix values."""
        if not isinstance(token, str):
            raise ValueError(f"{field_name} must be a non-empty string")

        normalized_token = token.strip()
        if not normalized_token:
            raise ValueError(f"{field_name} must be a non-empty string")

        return normalized_token

    @staticmethod
    def _normalize_max_requests_per_batch(value: Any) -> int | None:
        """Normalize optional batch sizes for template replacement updates."""
        if value is None:
            return None

        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ValueError(
                "max_requests_per_batch must be a positive integer or None"
            )

        return value

    @staticmethod
    def _normalize_dry_run(value: Any) -> bool:
        """Normalize dry-run flags used by template replacement."""
        if not isinstance(value, bool):
            raise ValueError("dry_run must be a boolean")

        return value

    @staticmethod
    def _normalize_skip_none_values(value: Any) -> bool:
        """Normalize None-skipping flags used by template replacement."""
        if not isinstance(value, bool):
            raise ValueError("skip_none_values must be a boolean")

        return value

    @staticmethod
    def _normalize_skip_blank_values(value: Any) -> bool:
        """Normalize blank-string skipping flags for template replacement."""
        if not isinstance(value, bool):
            raise ValueError("skip_blank_values must be a boolean")

        return value

    @staticmethod
    def _normalize_flatten_nested_variables(value: Any) -> bool:
        """Normalize nested-variable flattening flags."""
        if not isinstance(value, bool):
            raise ValueError("flatten_nested_variables must be a boolean")

        return value

    @staticmethod
    def _normalize_flatten_nested_sequences(value: Any) -> bool:
        """Normalize nested-sequence flattening flags."""
        if not isinstance(value, bool):
            raise ValueError("flatten_nested_sequences must be a boolean")

        return value

    @staticmethod
    def _normalize_variable_order(value: Any) -> str:
        """Normalize variable ordering strategies for replacement requests."""
        if not isinstance(value, str):
            raise ValueError("variable_order must be one of: input, asc, desc")

        normalized_order = value.strip().lower()
        if normalized_order not in {"input", "asc", "desc"}:
            raise ValueError("variable_order must be one of: input, asc, desc")

        return normalized_order

    @staticmethod
    def _normalize_nested_key_separator(value: Any) -> str:
        """Normalize nested-variable key separators used during flattening."""
        if not isinstance(value, str):
            raise ValueError("nested_key_separator must be a non-empty string")

        normalized_separator = value.strip()
        if not normalized_separator:
            raise ValueError("nested_key_separator must be a non-empty string")

        return normalized_separator

    @staticmethod
    def _normalize_value_serializer(
        value: Any,
    ) -> Callable[[Any], Any] | None:
        """Normalize optional replacement-value serializer callbacks."""
        if value is None:
            return None

        if not callable(value):
            raise ValueError("value_serializer must be callable when provided")

        return value

    @classmethod
    def _flatten_template_variables(
        cls,
        variables: Mapping[str, Any],
        *,
        nested_key_separator: str,
        flatten_nested_sequences: bool = False,
        path: tuple[str, ...] = (),
    ) -> list[tuple[str, Any]]:
        """Flatten nested template variables into placeholder key paths."""
        flattened_variables: list[tuple[str, Any]] = []

        def _flatten_value(
            value: Any,
            *,
            value_path: tuple[str, ...],
        ) -> None:
            if isinstance(value, Mapping):
                flattened_variables.extend(
                    cls._flatten_template_variables(
                        value,
                        nested_key_separator=nested_key_separator,
                        flatten_nested_sequences=flatten_nested_sequences,
                        path=value_path,
                    )
                )
                return

            if (
                flatten_nested_sequences
                and isinstance(value, Sequence)
                and not isinstance(value, (str, bytes, bytearray))
            ):
                for index, sequence_item in enumerate(value):
                    _flatten_value(
                        sequence_item,
                        value_path=(*value_path, str(index)),
                    )
                return

            normalized_key = nested_key_separator.join(value_path)
            flattened_variables.append((normalized_key, value))

        for variable_name, replacement_value in variables.items():
            if not isinstance(variable_name, str):
                raise ValueError("variables keys must be non-empty strings")

            normalized_name = variable_name.strip()
            if not normalized_name:
                raise ValueError("variables keys must be non-empty strings")

            variable_path = (*path, normalized_name)
            _flatten_value(replacement_value, value_path=variable_path)

        return flattened_variables

    def replace_template_variables(
        self,
        document_id: str,
        variables: Mapping[str, Any],
        *,
        placeholder_prefix: str = "{{",
        placeholder_suffix: str = "}}",
        match_case: bool = True,
        max_requests_per_batch: int | None = 100,
        dry_run: bool = False,
        skip_none_values: bool = False,
        skip_blank_values: bool = False,
        flatten_nested_variables: bool = False,
        flatten_nested_sequences: bool = False,
        nested_key_separator: str = ".",
        value_serializer: Callable[[Any], Any] | None = None,
        variable_order: str = "input",
    ) -> dict[str, Any]:
        """Replace template placeholders (e.g. ``{{name}}``) in a document.

        Args:
            document_id: Target document ID.
            variables: Mapping of placeholder names to replacement values.
                ``None`` values are replaced with an empty string unless
                ``skip_none_values`` is enabled.
            placeholder_prefix: Prefix used when constructing placeholders.
            placeholder_suffix: Suffix used when constructing placeholders.
            match_case: Whether placeholder matching should be case sensitive.
            max_requests_per_batch: Optional maximum number of
                ``replaceAllText`` requests sent in each ``batchUpdate`` call.
                Use ``None`` to send all requests in a single call.
            dry_run: When ``True``, skip API calls and return a payload that
                describes the generated request batches.
            skip_none_values: When ``True``, variables with ``None`` values are
                ignored instead of being replaced with an empty string.
            skip_blank_values: When ``True``, variables with string values that
                become blank after ``strip()`` are ignored.
            flatten_nested_variables: When ``True``, nested mapping values are
                flattened into placeholder names joined by
                ``nested_key_separator`` (for example,
                ``{"user": {"name": "Ada"}}`` -> ``{{user.name}}``).
            flatten_nested_sequences: When ``True`` (and
                ``flatten_nested_variables`` is also enabled), nested list/
                tuple values are flattened using zero-based indexes (for
                example, ``{"items": ["A", "B"]}`` ->
                ``{{items.0}}`` and ``{{items.1}}``).
            nested_key_separator: Separator used when flattening nested
                variable keys.
            value_serializer: Optional callable used to transform non-``None``
                replacement values before string coercion.
                Serializer return values of ``None`` are treated as empty
                replacement strings.
            variable_order: Placeholder request ordering strategy.
                ``"input"`` preserves incoming mapping order,
                ``"asc"`` sorts normalized placeholder names ascending, and
                ``"desc"`` sorts them descending.

        Returns:
            API response dictionary from ``documents().batchUpdate``.
            When multiple batches are required, returns an aggregate payload
            containing ``batchCount``, ``requestCount``, and
            ``batchResponses`` (plus merged ``replies`` when available).
            When ``dry_run`` is enabled, returns a deterministic preview
            payload containing ``documentId``, ``requestCount``,
            ``batchCount``, and ``requestBatches``.
            When ``skip_none_values``/``skip_blank_values`` filter out all
            replacements, returns an empty deterministic payload without
            issuing API calls.

        Raises:
            ValueError: If variables/prefix/suffix/match_case/batch size,
                flattening options, duplicate flattened keys, or
                ``dry_run``/``skip_none_values``/``skip_blank_values``/
                ``value_serializer``/``variable_order`` are invalid.
            HttpError: If Google Docs replacement request fails.
        """
        if not isinstance(variables, Mapping):
            raise ValueError("variables must be a mapping of placeholder names")
        if not variables:
            raise ValueError("variables must include at least one placeholder")
        if not isinstance(match_case, bool):
            raise ValueError("match_case must be a boolean")

        normalized_dry_run = self._normalize_dry_run(dry_run)
        normalized_skip_none_values = self._normalize_skip_none_values(skip_none_values)
        normalized_skip_blank_values = self._normalize_skip_blank_values(
            skip_blank_values
        )
        normalized_flatten_nested_variables = self._normalize_flatten_nested_variables(
            flatten_nested_variables
        )
        normalized_flatten_nested_sequences = self._normalize_flatten_nested_sequences(
            flatten_nested_sequences
        )
        normalized_nested_key_separator = self._normalize_nested_key_separator(
            nested_key_separator
        )
        normalized_value_serializer = self._normalize_value_serializer(value_serializer)
        normalized_variable_order = self._normalize_variable_order(variable_order)
        normalized_max_requests_per_batch = self._normalize_max_requests_per_batch(
            max_requests_per_batch
        )

        if (
            normalized_flatten_nested_sequences
            and not normalized_flatten_nested_variables
        ):
            raise ValueError(
                "flatten_nested_sequences requires " "flatten_nested_variables=True"
            )

        normalized_prefix = self._normalize_placeholder_token(
            placeholder_prefix,
            field_name="placeholder_prefix",
        )
        normalized_suffix = self._normalize_placeholder_token(
            placeholder_suffix,
            field_name="placeholder_suffix",
        )

        variable_items: list[tuple[str, Any]]
        if normalized_flatten_nested_variables:
            variable_items = self._flatten_template_variables(
                variables,
                nested_key_separator=normalized_nested_key_separator,
                flatten_nested_sequences=normalized_flatten_nested_sequences,
            )
        else:
            variable_items = []
            for variable_name, replacement_value in variables.items():
                if not isinstance(variable_name, str):
                    raise ValueError("variables keys must be non-empty strings")

                normalized_name = variable_name.strip()
                if not normalized_name:
                    raise ValueError("variables keys must be non-empty strings")

                variable_items.append((normalized_name, replacement_value))

        if normalized_flatten_nested_variables:
            normalized_names = [variable_name for variable_name, _ in variable_items]
            if len(normalized_names) != len(set(normalized_names)):
                raise ValueError(
                    "flattened variables contain duplicate placeholder keys; "
                    "adjust nested keys or disable flatten_nested_variables"
                )

        if normalized_variable_order != "input":
            variable_items = sorted(
                variable_items,
                key=lambda item: item[0],
                reverse=normalized_variable_order == "desc",
            )

        requests: list[dict[str, Any]] = []
        for normalized_name, replacement_value in variable_items:
            if replacement_value is None and normalized_skip_none_values:
                continue

            if (
                normalized_skip_blank_values
                and isinstance(replacement_value, str)
                and not replacement_value.strip()
            ):
                continue

            placeholder = f"{normalized_prefix}{normalized_name}{normalized_suffix}"

            replacement_text: str
            if replacement_value is None:
                replacement_text = ""
            else:
                serialized_value = replacement_value
                if normalized_value_serializer is not None:
                    serialized_value = normalized_value_serializer(replacement_value)

                replacement_text = (
                    "" if serialized_value is None else str(serialized_value)
                )

            requests.append(
                {
                    "replaceAllText": {
                        "containsText": {
                            "text": placeholder,
                            "matchCase": match_case,
                        },
                        "replaceText": replacement_text,
                    }
                }
            )

        if not requests:
            if normalized_dry_run:
                return {
                    "dryRun": True,
                    "documentId": document_id,
                    "requestCount": 0,
                    "batchCount": 0,
                    "requestBatches": [],
                }

            return {
                "documentId": document_id,
                "requestCount": 0,
                "batchCount": 0,
                "batchResponses": [],
                "replies": [],
            }

        request_batches = [requests]
        if normalized_max_requests_per_batch is not None:
            request_batches = [
                requests[index : index + normalized_max_requests_per_batch]
                for index in range(0, len(requests), normalized_max_requests_per_batch)
            ]

        if normalized_dry_run:
            return {
                "dryRun": True,
                "documentId": document_id,
                "requestCount": len(requests),
                "batchCount": len(request_batches),
                "requestBatches": [
                    {"requests": request_batch} for request_batch in request_batches
                ],
            }

        try:
            batch_responses: list[dict[str, Any]] = []
            for request_batch in request_batches:
                result = (
                    self.service.documents()
                    .batchUpdate(
                        documentId=document_id, body={"requests": request_batch}
                    )
                    .execute()
                )
                batch_responses.append(result)

            logger.debug(
                "Replaced %s template placeholders in document %s using %s batch(es)",
                len(requests),
                document_id,
                len(batch_responses),
            )

            if len(batch_responses) == 1:
                return batch_responses[0]

            merged_replies = [
                reply
                for response in batch_responses
                for reply in response.get("replies", [])
            ]

            aggregate_response: dict[str, Any] = {
                "batchCount": len(batch_responses),
                "requestCount": len(requests),
                "batchResponses": batch_responses,
            }

            if merged_replies:
                aggregate_response["replies"] = merged_replies

            return aggregate_response

        except HttpError as error:
            logger.error("Failed to replace template variables: %s", error)
            raise

    def get_document(self, document_id: str) -> dict[str, Any]:
        """
        Get document content and metadata.

        Args:
            document_id: Document ID

        Returns:
            Document data dictionary

        Raises:
            HttpError: If retrieval fails
        """
        try:
            document = self.service.documents().get(documentId=document_id).execute()

            logger.debug("Retrieved document %s", document_id)
            return document

        except HttpError as error:
            logger.error("Failed to get document: %s", error)
            raise

    def get_document_url(self, document_id: str) -> str:
        """
        Get shareable URL for document.

        Args:
            document_id: Document ID

        Returns:
            Document URL
        """
        return f"https://docs.google.com/document/d/{document_id}/edit"


__all__ = ["GoogleDocsAPI"]
