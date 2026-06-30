import sys
import pytest
from unittest.mock import patch, MagicMock
from ui.cli import main

@patch("ui.cli.sys.argv", ["ltut", "invalid-subcommand"])
@patch("ui.cli.print")
def test_cli_invalid_command(mock_print):
    # Running an invalid command should print usage and return without starting the TUI
    main()
    mock_print.assert_any_call("Usage: ltut <command>\n")

@patch("ui.cli.sys.argv", ["ltut"])
@patch("ui.cli.load_config")
@patch("ui.cli.sys.exit")
@patch("ui.cli.print")
def test_cli_initialization_failure(mock_print, mock_exit, mock_load_config):
    # If loading configuration raises an error, it should exit with code 1
    mock_load_config.side_effect = ValueError("Missing configuration key")
    mock_exit.side_effect = SystemExit(1)
    
    with pytest.raises(SystemExit):
        main()
    mock_print.assert_any_call("[!] Error loading initialization layers: Missing configuration key")
    mock_exit.assert_called_once_with(1)

@patch("ui.cli.sys.argv", ["ltut"])
@patch("ui.cli.load_config")
@patch("ui.cli.build_storage")
@patch("ui.cli.build_llm")
@patch("ui.cli.sys.exit")
@patch("ui.cli.print")
def test_cli_health_check_failure(mock_print, mock_exit, mock_build_llm, mock_build_storage, mock_load_config):
    # If the LLM health check fails, the CLI should print connection instructions and exit with code 1
    mock_config = MagicMock()
    mock_load_config.return_value = mock_config
    
    mock_llm = MagicMock()
    mock_llm.check_health.return_value = False
    mock_build_llm.return_value = mock_llm
    mock_exit.side_effect = SystemExit(1)

    with pytest.raises(SystemExit):
        main()
    mock_print.assert_any_call("    Please ensure LM Studio (or your local LLM provider) is running and the Local Server is enabled.")
    mock_exit.assert_called_once_with(1)

@patch("ui.cli.sys.argv", ["ltut"])
@patch("ui.cli.load_config")
@patch("ui.cli.build_storage")
@patch("ui.cli.build_llm")
@patch("ui.cli.Orchestrator")
@patch("ui.cli.input")
@patch("ui.cli.print")
def test_cli_main_flow(mock_print, mock_input, mock_orchestrator_cls, mock_build_llm, mock_build_storage, mock_load_config):
    # Simulates a successful main session:
    # 1. Enter student ID -> 'john'
    # 2. Start another learning session -> 'n' (exits loop)
    mock_input.side_effect = ["john", "n"]
    
    mock_config = MagicMock()
    mock_load_config.return_value = mock_config
    
    mock_llm = MagicMock()
    mock_llm.check_health.return_value = True
    mock_build_llm.return_value = mock_llm
    
    mock_orch = MagicMock()
    mock_orchestrator_cls.return_value = mock_orch

    main()
    
    # Assert orchestrator instantiation and session execution
    call_args = mock_orchestrator_cls.call_args
    assert call_args[0] == (mock_build_storage.return_value, mock_llm, mock_config)
    assert "io" in call_args[1]
    call_kwargs = mock_orch.run_session.call_args
    assert call_kwargs[0][0] == "john"
    assert call_kwargs[1]["language"] is None
    assert callable(call_kwargs[1]["on_language_warning"])
    mock_print.assert_any_call("Goodbye!")
