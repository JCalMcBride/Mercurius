import logging
import os
import warnings
from logging.config import dictConfig

import click

from lib.bot import Bot
from lib.common import get_config


@click.group()
@click.pass_context
def main(ctx, **kwargs):
    """Mercurius - A Warframe Discord bot."""

    ctx.ensure_object(dict)
    ctx.obj['basepath'] = os.path.dirname(os.path.realpath(__file__))

    # Set up logging
    logging.basicConfig()
    try:
        cfgdict = get_config(os.path.join(ctx.obj['basepath'], 'config.log.json'))
        logging.getLogger('apscheduler').setLevel(logging.DEBUG)
    except Exception as e:
        logging.error(e)
        quit()
    dictConfig(cfgdict)
    warnings.filterwarnings(
        "ignore",
        message="The localize method is no longer necessary, as this time zone supports the fold attribute",
    )

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


if __name__ == '__main__':
    main(obj={})
