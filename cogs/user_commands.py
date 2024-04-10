import discord
from discord import app_commands
from discord.ext import commands
from asyncpg import Pool

from typing import Optional

from config import EMBED_COLOUR, PRICE_CHANGE_HRS
from helper.objects import Player, Event, Shoe

class UserCommands(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.pool: Pool = self.bot.pool

    async def interaction_check(self, itx: discord.Interaction) -> bool:
        """
        Do not allow commands when event does not exist
        """
        if await Event.exists(itx.guild_id, self.pool):
            return True
        await itx.response.send_message("An event needs to be active here to use this command", ephemeral = True)
        return False

    @app_commands.command(
        name = "profile",
        description = "Get player details"
    )
    async def show_profile(self, itx: discord.Interaction, member: Optional[discord.Member]):
        """
        Shows player profile
        """
        member = itx.user if member is None else member
        
        player = await Player.create_profile(member.id, itx.guild_id, self.pool)
        embed = await player.show_profile()

        await itx.response.send_message(embed = embed)

    @app_commands.command(
        name = "leaderboard",
        description = "Shows top 10 players in the game"
    )
    async def show_leaderboard(self, itx: discord.Interaction):
        """
        Shows leaderboard (highest 10)
        """
        event = Event(itx.guild_id, self.pool)
        embed = await event.show_leaderboard(itx.guild)
        await itx.response.send_message(embed = embed)

    @app_commands.command(
        name = "price",
        description = "Get the price history for last 5 changes"
    )
    async def show_price_history(self, itx: discord.Interaction):
        """
        Show the price history: last 6 records
        """
        prices = await Shoe.get_price_history(self.pool, 6)
        embed = discord.Embed(
            colour = discord.Colour.from_str(EMBED_COLOUR),
            description = ""
        )

        for record in prices:
            price = round(record['price'], 2)
            date = discord.utils.format_dt(record['price_date'], 'f')

            embed.description += f"- `{price}` coins on {date}\n"
        
        embed.set_footer(text = "Price changes every ~{} hours".format(PRICE_CHANGE_HRS))

        await itx.response.send_message(embed = embed)

    @app_commands.command(
        name = "sell",
        description = "Sell your shoes"
    )
    async def sell_shoes(self, itx: discord.Interaction, quantity: int = 1):
        """
        Sell your shoes, by default 1
        """
        player = await Player.create_profile(itx.user.id, itx.guild_id, self.pool)
        
        outcome = await player.sell_pos(quantity)

        await itx.response.send_message("You earned {0} at the rate {1} per pair of shoes".format(
            round(outcome['profit'], 2), round(outcome['price'], 2))
        )



async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(UserCommands(bot))