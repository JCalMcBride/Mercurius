# -*- coding: utf-8 -*-
"""
Sigil Controller - server control interface
"""

import os
import logging
from logging.config import dictConfig
import click

from lib.common import get_config
from lib.bot import Bot


@click.group()
@click.pass_context
def main(ctx, **kwargs):
    """Sigil Controller - A Foxhole Discord bot."""

    ctx.ensure_object(dict)
    ctx.obj['basepath'] = os.path.dirname(os.path.realpath(__file__))

    # Set up logging
    logging.basicConfig()
    try:
        cfgdict = get_config(os.path.join(ctx.obj['basepath'], 'config.log.json'))
    except Exception as e:
        logging.error(e)
        quit()
    dictConfig(cfgdict)


@main.command()
@click.option(
    '--debug',
    is_flag=True,
    help="Launch bot in debug mode."
)
@click.pass_context
def start(ctx, **kwargs):
    """Launch the bot process."""

    bot_cfg = get_config(os.path.join(ctx.obj['basepath'], 'config.bot.json'))
    bot = Bot(bot_cfg)

    if kwargs['debug']:
        logging.getLogger('bot').warning('Running in debug mode.')
        bot.debug_mode = True

    bot.run()


@main.command()
@click.pass_context
def db_install(ctx, **kwargs):
    """Install the database schema."""
    pass


@main.command()
@click.pass_context
def db_backup(ctx, **kwargs):
    """Save a database backup to a file."""
    pass


if __name__ == '__main__':
    main(obj={})
