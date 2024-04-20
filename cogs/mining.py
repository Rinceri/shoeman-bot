import discord
from discord import app_commands
from discord.ext import commands, tasks
from asyncpg import Pool

import numpy as np

from helper.objects import Player, Event
from helper.game_tasks import send_shoe_ores

class MiningCommands(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.pool: Pool = self.bot.pool
        self.shoe_ores.start()

    def cog_unload(self):
        self.shoe_ores.cancel()

    @tasks.loop(minutes = 30)
    async def shoe_ores(self):
        await send_shoe_ores(self.pool)

    @shoe_ores.before_loop
    async def before_shoes(self):
        await self.bot.wait_until_ready()


    async def interaction_check(self, itx: discord.Interaction) -> bool:
        """
        Do not allow commands when event does not exist
        """
        if await Event.exists(itx.guild_id, self.pool):
            return True
        await itx.response.send_message("An event needs to be active here to use this command", ephemeral = True)
        return False

    @app_commands.command(
        name = "mine",
        description = "Mine some ore!"
    )
    @app_commands.checks.cooldown(1, 60, key = lambda i: (i.guild_id, i.user.id))
    async def mine_ore(self, itx: discord.Interaction):
        """
        Adds ore to the player's profile.

        Ore calculation is done by simply picking a random number between 0 and 10
        """
        rng = np.random.default_rng()
        rint = rng.integers(0, 11)

        player = await Player.create_profile(itx.user.id, itx.guild_id, self.pool)

        await player.add_ores(rint)

        await itx.response.send_message(f"You earned {rint} ores")
    
    @mine_ore.error
    async def on_test_error(self, itx: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.CommandOnCooldown):
            retry_after = int(error.retry_after)
            await itx.response.send_message(f"Wait for {retry_after} seconds before trying again", ephemeral=True)

    @app_commands.command(
        name = "ores",
        description = "Get ore leaderboard"
    )
    async def show_ore_leaderbord(self, itx: discord.Interaction):
        """
        Shows leaderboard based on ores, for top 10 only
        """
        event = Event(itx.guild_id, self.pool)
        embed = await event.show_ore_leaderboard(itx.guild)
        await itx.response.send_message(embed = embed)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(MiningCommands(bot))