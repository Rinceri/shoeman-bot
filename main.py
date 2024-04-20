import discord
from discord.ext import commands, tasks
import asyncpg
import config
import helper.game_tasks as gt
from helper.objects import ViewHelper

import traceback

description = "A game bot by Rinceri"
extensions = [
    'cogs.owner',
    'cogs.user_commands',
    'cogs.admin',
    'cogs.mining'
]


def get_command_prefixes(bot: commands.Bot, msg: discord.Message):
    return [f'<@!{bot.user.id}> ', f'<@{bot.user.id}> ']
    

class Shoeman(commands.Bot):
    pool: asyncpg.Pool

    def __init__(self) -> None:
        intents = discord.Intents(
            guilds = True,
            members = True,
            messages = True,
            emojis = True,
        )

        super().__init__(
            command_prefix = get_command_prefixes,
            intents = intents,
            description = description
        )

        self.my_views = []

    async def setup_hook(self):
        # creating pool
        self.pool = await asyncpg.create_pool(config.connection_uri)

        # loading extensions
        for extension in extensions:
            try:
                await self.load_extension(extension)
            except Exception as e:
                print(e)

        # adding persistent views
        views = await ViewHelper.get_views(self.pool)

        for record in views:
            # create instance of VH for GiveawayView
            vh = ViewHelper(
                pool = self.pool, 
                message_id = record['message_id'], 
                channel_id = record['channel_id'],
                id = record['id'],
                used_users = record['used_users']
            )
            # create GiveawayView for add_view and my_views
            view = gt.GiveawayView(self.pool, vh)
            self.add_view(view, message_id = record['message_id'])
            self.my_views.append(view)

        # start bg task
        self.bg_task.start()

    @tasks.loop(minutes = 15)
    async def bg_task(self):
        await gt.price_fluct(self.pool)
        await gt.pos_giveaway(self, self.pool)

    @bg_task.before_loop
    async def before_bg_task(self):
        await self.wait_until_ready()

    async def on_ready(self):
        print(f"Logged in as {self.user}: (ID: {self.user.id})")
        print("---------")

    async def close(self):
        # closing the connection pool gracefully
        await self.pool.close()
        await super().close()

    async def on_command_error(
        self, 
        context: commands.Context, 
        exception: commands.CommandError
    ) -> None:
        # pass if check fails for text commands
        if isinstance(exception, commands.errors.CheckFailure):
            return
        else:
            traceback.print_exc()


client = Shoeman()

@client.tree.error
async def on_app_command_error(
    itx: discord.Interaction,
    error: discord.app_commands.errors.AppCommandError
):
    # cog check failed
    if isinstance(error, discord.app_commands.errors.CheckFailure):
        return
    else:
        traceback.print_exc()

if __name__ == "__main__":
    client.run(config.token)