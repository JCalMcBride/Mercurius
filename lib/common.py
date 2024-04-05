# -*- coding: utf-8 -*-
"""Common utility functions."""

from typing import Dict
import os
import json


def get_config(path:str) -> Dict[str, str]:
    """Load and parse a config file.

    Args:
        path (str, optional): Path to json config file.

    Returns:
        dict: Parsed config file data.
    """
    if not os.path.exists(path):
        raise Exception(
            '{0} : File does not exist.'.format(path)
        )
    if not os.access(path, os.R_OK):
        raise Exception(
            '{0} : File is not readable.'.format(path)
        )
    with open(path, 'r') as f:
        ret = json.load(f)
    return ret

with open('lib/data/misc_bot_data.json') as f:
    misc_bot_data = json.load(f)


def get_emoji(emoji):
    return f"<:{emoji}:{misc_bot_data['emojis'][emoji]}>"
