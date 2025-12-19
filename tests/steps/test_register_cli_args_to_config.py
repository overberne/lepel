import sys

from lepel.steps import RegisterCliArgsToConfig
from lepel.config import get_config


def test_register_cli_args():
    sys.argv.extend(
        [
            *('--a', '1'),
            *('--b.c', '2.0'),
            '--d=3',
            '--e=False',
            '--f="foo"',
            'not',
            'parsed',
            '--flag',
            '--flag2',
        ]
    )
    RegisterCliArgsToConfig().run()
    config = get_config()
    assert config['a'] == 1
    assert config['b.c'] == 2.0
    assert config['d'] == 3
    assert config['e'] == False
    assert config['f'] == 'foo'
    assert config['flag'] == True
    assert config['flag2'] == True
    assert 'not' not in config
    assert 'parsed' not in config
