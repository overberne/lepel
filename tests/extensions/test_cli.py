from lepel.extensions.cli import cli_args_to_config


def test_cli_args_to_config_parses_equals_and_space_values():
    config = cli_args_to_config(['--foo=1', '--bar', '2'])
    assert config['foo'] == 1
    assert config['bar'] == 2


def test_cli_args_to_config_parses_flags_and_boolish():
    config = cli_args_to_config(['--flag', '--t=true', '--f=false'])
    assert config['flag'] is True
    assert config['t'] is True
    assert config['f'] is False


def test_cli_args_to_config_parses_float_and_string_fallback():
    config = cli_args_to_config(['--lr=0.01', '--name', 'exp1'])
    assert config['lr'] == 0.01
    assert config['name'] == 'exp1'


def test_cli_args_to_config_ignores_non_option_tokens():
    config = cli_args_to_config(['positional', '--x=1', 'still-positional'])
    assert config == {'x': 1}
