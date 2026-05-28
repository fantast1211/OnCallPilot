"""Tests for database model shapes, constraints, and relationships."""

import pytest
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import AsyncEngine

from oncallpilot_api.db.models import (
    INCIDENT_STATUSES,
    INVESTIGATION_SESSION_STATUSES,
    CHAT_SESSION_STATUSES,
    CHAT_MESSAGE_ROLES,
    TOOL_CALL_STATUSES,
    REMEDIATION_ACTION_STATUSES,
    Incident,
    InvestigationSession,
    ChatSession,
    ChatMessage,
    ToolCall,
    RunbookDocument,
    IncidentMemory,
    RemediationAction,
    ServiceCatalogEntry,
)


class TestStatusConstants:
    """Test that status validation constants are properly defined."""

    def test_incident_statuses(self):
        assert INCIDENT_STATUSES == {"open", "investigating", "resolved", "error"}

    def test_investigation_session_statuses(self):
        assert INVESTIGATION_SESSION_STATUSES == {"pending", "running", "completed", "failed"}

    def test_chat_session_statuses(self):
        assert CHAT_SESSION_STATUSES == {"active", "completed"}

    def test_chat_message_roles(self):
        assert CHAT_MESSAGE_ROLES == {"user", "assistant", "system"}

    def test_tool_call_statuses(self):
        assert TOOL_CALL_STATUSES == {"pending", "running", "success", "failed"}

    def test_remediation_action_statuses(self):
        assert REMEDIATION_ACTION_STATUSES == {"pending", "approved", "executed", "failed"}


class TestIncidentModel:
    """Test Incident model columns and constraints."""

    def test_has_expected_columns(self):
        mapper = inspect(Incident)
        column_names = {col.key for col in mapper.columns}
        expected = {
            "id", "fingerprint", "status", "severity", "service",
            "namespace", "cluster", "description", "started_at",
            "resolved_at", "created_at", "updated_at",
        }
        assert expected.issubset(column_names)

    def test_fingerprint_is_not_nullable(self):
        mapper = inspect(Incident)
        assert mapper.columns["fingerprint"].nullable is False

    def test_status_is_not_nullable(self):
        mapper = inspect(Incident)
        assert mapper.columns["status"].nullable is False

    def test_severity_is_not_nullable(self):
        mapper = inspect(Incident)
        assert mapper.columns["severity"].nullable is False

    def test_id_is_primary_key(self):
        mapper = inspect(Incident)
        assert mapper.columns["id"].primary_key is True


class TestInvestigationSessionModel:
    """Test InvestigationSession model columns and relationships."""

    def test_has_expected_columns(self):
        mapper = inspect(InvestigationSession)
        column_names = {col.key for col in mapper.columns}
        expected = {
            "id", "incident_id", "status", "started_at", "ended_at",
            "metadata", "created_at", "updated_at",
        }
        assert expected.issubset(column_names)

    def test_has_incident_relationship(self):
        mapper = inspect(InvestigationSession)
        rel_names = {rel.key for rel in mapper.relationships}
        assert "incident" in rel_names

    def test_incident_id_is_foreign_key(self):
        mapper = inspect(InvestigationSession)
        fk = mapper.columns["incident_id"].foreign_keys
        assert len(fk) == 1


class TestChatSessionModel:
    """Test ChatSession model columns and relationships."""

    def test_has_expected_columns(self):
        mapper = inspect(ChatSession)
        column_names = {col.key for col in mapper.columns}
        expected = {
            "id", "investigation_session_id", "status",
            "created_at", "updated_at",
        }
        assert expected.issubset(column_names)

    def test_has_investigation_session_relationship(self):
        mapper = inspect(ChatSession)
        rel_names = {rel.key for rel in mapper.relationships}
        assert "investigation_session" in rel_names


class TestChatMessageModel:
    """Test ChatMessage model columns and relationships."""

    def test_has_expected_columns(self):
        mapper = inspect(ChatMessage)
        column_names = {col.key for col in mapper.columns}
        expected = {
            "id", "chat_session_id", "role", "content", "created_at",
        }
        assert expected.issubset(column_names)

    def test_has_chat_session_relationship(self):
        mapper = inspect(ChatMessage)
        rel_names = {rel.key for rel in mapper.relationships}
        assert "chat_session" in rel_names

    def test_role_is_not_nullable(self):
        mapper = inspect(ChatMessage)
        assert mapper.columns["role"].nullable is False


class TestToolCallModel:
    """Test ToolCall model columns, relationships, and cross-reference constraint."""

    def test_has_expected_columns(self):
        mapper = inspect(ToolCall)
        column_names = {col.key for col in mapper.columns}
        expected = {
            "id", "investigation_session_id", "chat_session_id",
            "tool_name", "input_data", "output_data", "status",
            "created_at",
        }
        assert expected.issubset(column_names)

    def test_has_investigation_session_relationship(self):
        mapper = inspect(ToolCall)
        rel_names = {rel.key for rel in mapper.relationships}
        assert "investigation_session" in rel_names

    def test_has_chat_session_relationship(self):
        mapper = inspect(ToolCall)
        rel_names = {rel.key for rel in mapper.relationships}
        assert "chat_session" in rel_names

    def test_tool_name_is_not_nullable(self):
        mapper = inspect(ToolCall)
        assert mapper.columns["tool_name"].nullable is False


class TestRunbookDocumentModel:
    """Test RunbookDocument model columns."""

    def test_has_expected_columns(self):
        mapper = inspect(RunbookDocument)
        column_names = {col.key for col in mapper.columns}
        expected = {
            "id", "title", "content", "service", "tags",
            "created_at", "updated_at",
        }
        assert expected.issubset(column_names)

    def test_title_is_not_nullable(self):
        mapper = inspect(RunbookDocument)
        assert mapper.columns["title"].nullable is False


class TestIncidentMemoryModel:
    """Test IncidentMemory model columns and relationships."""

    def test_has_expected_columns(self):
        mapper = inspect(IncidentMemory)
        column_names = {col.key for col in mapper.columns}
        expected = {
            "id", "incident_id", "content", "embedding",
            "metadata", "created_at",
        }
        assert expected.issubset(column_names)

    def test_has_incident_relationship(self):
        mapper = inspect(IncidentMemory)
        rel_names = {rel.key for rel in mapper.relationships}
        assert "incident" in rel_names

    def test_content_is_not_nullable(self):
        mapper = inspect(IncidentMemory)
        assert mapper.columns["content"].nullable is False


class TestRemediationActionModel:
    """Test RemediationAction model columns and relationships."""

    def test_has_expected_columns(self):
        mapper = inspect(RemediationAction)
        column_names = {col.key for col in mapper.columns}
        expected = {
            "id", "incident_id", "action_type", "status",
            "parameters", "result", "created_at",
        }
        assert expected.issubset(column_names)

    def test_has_incident_relationship(self):
        mapper = inspect(RemediationAction)
        rel_names = {rel.key for rel in mapper.relationships}
        assert "incident" in rel_names

    def test_action_type_is_not_nullable(self):
        mapper = inspect(RemediationAction)
        assert mapper.columns["action_type"].nullable is False


class TestServiceCatalogEntryModel:
    """Test ServiceCatalogEntry model columns."""

    def test_has_expected_columns(self):
        mapper = inspect(ServiceCatalogEntry)
        column_names = {col.key for col in mapper.columns}
        expected = {
            "id", "service_name", "description", "team",
            "contacts", "metadata", "created_at", "updated_at",
        }
        assert expected.issubset(column_names)

    def test_service_name_is_not_nullable(self):
        mapper = inspect(ServiceCatalogEntry)
        assert mapper.columns["service_name"].nullable is False


class TestModelExports:
    """Test that all models are exported from db package."""

    def test_models_importable_from_db(self):
        from oncallpilot_api.db import (
            Incident,
            InvestigationSession,
            ChatSession,
            ChatMessage,
            ToolCall,
            RunbookDocument,
            IncidentMemory,
            RemediationAction,
            ServiceCatalogEntry,
        )
        # If we get here, all imports succeeded
        assert True
