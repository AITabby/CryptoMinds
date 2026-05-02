"""Tests for AgentService — lifecycle, status, callbacks (mocked deps)."""
from unittest.mock import patch, MagicMock
from decimal import Decimal
import pytest


# Must import AFTER sys.modules mock, so we patch before agent_service imports deps
_mock_daemon_mod = MagicMock()
_mock_listener_mod = MagicMock()
_mock_closer_mod = MagicMock()
_mock_env_loader = MagicMock()
_mock_env_loader.load_env.return_value = {}


@pytest.fixture(autouse=True)
def _mock_deps():
    """Mock all heavy dependencies that have import-time side effects."""
    with patch.dict("sys.modules", {
        "logging_config": MagicMock(),
        "scripts": MagicMock(),
        "scripts.env_loader": _mock_env_loader,
        "agent_daemon": _mock_daemon_mod,
        "market_listener": _mock_listener_mod,
        "task_closer": _mock_closer_mod,
    }):
        # Force reload so mock modules take effect
        import importlib
        if "agent_service" in __import__("sys").modules:
            del __import__("sys").modules["agent_service"]
        yield


class TestAgentServiceConfig:

    def test_default_values(self):
        from agent_service import AgentServiceConfig
        config = AgentServiceConfig(agent_id="test", wallet="0xW")
        assert config.agent_id == "test"
        assert config.wallet == "0xW"
        assert config.private_key == ""
        assert config.task_types is None
        assert config.auto_accept is True
        assert config.max_concurrent_tasks == 3
        assert config.min_amount == Decimal("0.001")

    def test_custom_values(self):
        from agent_service import AgentServiceConfig
        config = AgentServiceConfig(
            agent_id="my-agent",
            wallet="0xABC",
            private_key="key123",
            task_types=["token_delivery", "data_delivery"],
            supported_chains=["bsc", "mock"],
            auto_accept=False,
            max_concurrent_tasks=5,
            market_url="http://custom:9999",
        )
        assert config.task_types == ["token_delivery", "data_delivery"]
        assert config.auto_accept is False


class TestAgentServiceInit:

    def test_init_creates_internal_components(self):
        from agent_service import AgentService, AgentServiceConfig
        config = AgentServiceConfig(agent_id="test", wallet="0xW")
        svc = AgentService(config)
        # daemon/listener/matcher/closer are created from mocked modules
        assert svc._running is False


class TestAgentServiceLifecycle:

    def test_start_sets_running(self):
        from agent_service import AgentService, AgentServiceConfig
        config = AgentServiceConfig(agent_id="test", wallet="0xW")
        svc = AgentService(config)
        svc.start()
        assert svc._running is True

    def test_start_already_running_no_error(self):
        from agent_service import AgentService, AgentServiceConfig
        config = AgentServiceConfig(agent_id="test", wallet="0xW")
        svc = AgentService(config)
        svc.start()
        svc.start()  # second call should just log warning
        assert svc._running is True

    def test_stop_sets_not_running(self):
        from agent_service import AgentService, AgentServiceConfig
        config = AgentServiceConfig(agent_id="test", wallet="0xW")
        svc = AgentService(config)
        svc.start()
        svc.stop()
        assert svc._running is False

    def test_pause_calls_daemon_pause(self):
        from agent_service import AgentService, AgentServiceConfig
        config = AgentServiceConfig(agent_id="test", wallet="0xW")
        svc = AgentService(config)
        svc.pause()
        svc.daemon.pause.assert_called_once()

    def test_resume_calls_daemon_resume(self):
        from agent_service import AgentService, AgentServiceConfig
        config = AgentServiceConfig(agent_id="test", wallet="0xW")
        svc = AgentService(config)
        svc.resume()
        svc.daemon.resume.assert_called_once()


class TestAgentServiceRegisterExecutor:

    def test_register_executor_calls_daemon(self):
        from agent_service import AgentService, AgentServiceConfig
        config = AgentServiceConfig(agent_id="test", wallet="0xW")
        svc = AgentService(config)
        mock_fn = MagicMock()
        svc.register_executor("token_delivery", mock_fn)
        svc.daemon.register_executor.assert_called_once_with("token_delivery", mock_fn)


class TestAgentServiceGetStatus:

    def test_get_status_aggregates_from_daemon(self):
        from agent_service import AgentService, AgentServiceConfig
        config = AgentServiceConfig(agent_id="test", wallet="0xW")
        svc = AgentService(config)
        svc.daemon.get_status.return_value = {
            "state": "idle",
            "active_tasks": 0,
            "pending_tasks": 0,
            "completed_tasks": 0,
            "stats": {},
        }
        status = svc.get_status()
        assert status["agent_id"] == "test"
        assert status["wallet"] == "0xW"
        assert status["running"] is False
        assert status["daemon_state"] == "idle"


class TestAgentServiceSubmitTask:

    def test_submit_task_delegates_to_daemon(self):
        from agent_service import AgentService, AgentServiceConfig
        config = AgentServiceConfig(agent_id="test", wallet="0xW")
        svc = AgentService(config)
        svc.daemon.submit_task.return_value = True
        mock_task = MagicMock()
        result = svc.submit_task(mock_task)
        assert result is True
        svc.daemon.submit_task.assert_called_once_with(mock_task)


class TestCreateService:

    def test_create_service_returns_service(self):
        from agent_service import create_service, AgentService
        svc = create_service("test-agent", "0xW")
        assert isinstance(svc, AgentService)