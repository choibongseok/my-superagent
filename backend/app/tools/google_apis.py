"""Google Workspace API tools for document creation and manipulation."""

from collections.abc import Mapping
import logging
from typing import Any

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

    def replace_template_variables(
        self,
        document_id: str,
        variables: Mapping[str, Any],
        *,
        placeholder_prefix: str = "{{",
        placeholder_suffix: str = "}}",
        match_case: bool = True,
    ) -> dict[str, Any]:
        """Replace template placeholders (e.g. ``{{name}}``) in a document.

        Args:
            document_id: Target document ID.
            variables: Mapping of placeholder names to replacement values.
                ``None`` values are replaced with an empty string.
            placeholder_prefix: Prefix used when constructing placeholders.
            placeholder_suffix: Suffix used when constructing placeholders.
            match_case: Whether placeholder matching should be case sensitive.

        Returns:
            API response dictionary from ``documents().batchUpdate``.

        Raises:
            ValueError: If variables/prefix/suffix/match_case are invalid.
            HttpError: If Google Docs replacement request fails.
        """
        if not isinstance(variables, Mapping):
            raise ValueError("variables must be a mapping of placeholder names")
        if not variables:
            raise ValueError("variables must include at least one placeholder")
        if not isinstance(match_case, bool):
            raise ValueError("match_case must be a boolean")

        normalized_prefix = self._normalize_placeholder_token(
            placeholder_prefix,
            field_name="placeholder_prefix",
        )
        normalized_suffix = self._normalize_placeholder_token(
            placeholder_suffix,
            field_name="placeholder_suffix",
        )

        requests: list[dict[str, Any]] = []
        for variable_name, replacement_value in variables.items():
            if not isinstance(variable_name, str):
                raise ValueError("variables keys must be non-empty strings")

            normalized_name = variable_name.strip()
            if not normalized_name:
                raise ValueError("variables keys must be non-empty strings")

            placeholder = f"{normalized_prefix}{normalized_name}{normalized_suffix}"
            requests.append(
                {
                    "replaceAllText": {
                        "containsText": {
                            "text": placeholder,
                            "matchCase": match_case,
                        },
                        "replaceText": ""
                        if replacement_value is None
                        else str(replacement_value),
                    }
                }
            )

        try:
            result = (
                self.service.documents()
                .batchUpdate(documentId=document_id, body={"requests": requests})
                .execute()
            )
            logger.debug(
                "Replaced %s template placeholders in document %s",
                len(requests),
                document_id,
            )
            return result

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
