import discord
from discord import app_commands
from discord.ext import commands
from discord.utils import utcnow, format_dt
from datetime import timedelta
from asyncpg import Pool

from typing import Optional

from params import EMBED_COLOUR, PRICE_CHANGE_HRS
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

    @app_commands.command(
        name = "offer",
        description = "Make an offer to sell shoes at a price. Lasts for 1 hour"
    )
    async def make_offer(self, itx: discord.Interaction, price: float, shoes: int = 1):
        """
        Make offer for by default 1 shoe
        """
        player = await Player.create_profile(itx.user.id, itx.guild_id, self.pool)
        player_shoes = await player.get_pos()

        if (shoes > player_shoes) or (shoes < 1):
            await itx.response.send_message("Invalid number of shoes offered", ephemeral = True)
            return

        embed = discord.Embed(
            colour = discord.Colour.from_str(EMBED_COLOUR), 
            title = f"Offer: buy {shoes} shoes for {price} coins"
        )
        expires = utcnow() + timedelta(hours = 1)
        
        embed.description = f"Offer made by {itx.user.mention} which expires {format_dt(expires, 'R')}"

        view = OfferView(player, price, shoes, self.pool)

        await itx.response.send_message(embed = embed, view = view)

        # we do this so we can get a Message object to edit the view later on
        # as interaction webhooks expires after 15 minutes
        message = await itx.original_response()
        view.msg = await message.fetch()


class OfferView(discord.ui.View):
    def __init__(self, 
        owner: Player,
        price: float, shoes: int, 
        pool: Pool
    ):
        super().__init__(timeout = 3600)
        
        self.owner = owner
        self.price = price
        self.shoes = shoes
        self.pool = pool
        self.msg = None

    async def interaction_check(self, itx: discord.Interaction) -> bool:
        if self.owner.user_id == itx.user.id:
            await itx.response.send_message("You can't accept your own offer!", ephemeral = True)
            return False
        return True
    
    async def on_timeout(self) -> None:
        self.msg: discord.Message
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True
        
        await self.msg.edit(view = self)
        self.stop()

    @discord.ui.button(label='Accept offer', style=discord.ButtonStyle.green)
    async def accept_offer(self, itx: discord.Interaction, button: discord.ui.Button):
        player = await Player.create_profile(itx.user.id, itx.guild_id, self.pool)

        # check if player has enough money
        player_bal = await player.get_balance()
        if player_bal < self.price:
            await itx.response.send_message("You do not have enough money!", ephemeral = True)
            return
            
        # we need to check whether owner has the shoes needed for this offer 
        owner_shoes = await self.owner.get_pos()
        if owner_shoes < self.shoes:
            await itx.response.send_message("Owner does not have enough shoes anymore", ephemeral = True)
            
            # disable button
            button.disabled = True
            await itx.response.edit_message(view = self)
            self.stop()            
            return
        
        # increase owner's balance and decrease shoes owned, and vice versa for itx user
        await self.owner.exchange_details(itx.user.id, self.shoes, self.price)

        # disable button and edit to show changes
        button.disabled = True
        await itx.response.edit_message(view = self)
        await itx.followup.send(f"The offer has been accepted by {itx.user.mention}, and transactions have been processed!")
        self.stop()



async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(UserCommands(bot))
