import discord
from discord import app_commands
from discord.ext import commands
from asyncpg import Pool

from typing import Optional

from helper.objects import Player, Event, ViewHelper
from helper.game_tasks import send_view

class AdminCommands(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.pool: Pool = self.bot.pool

    async def interaction_check(self, itx: discord.Interaction) -> bool:
        """
        Only allow users with admin permission
        """
        if itx.user.guild_permissions.administrator:
            return True
        await itx.response.send_message("You need admin permission", ephemeral = True)
        return False
    
    @app_commands.command(
        name = "set_player",
        description = "Set player's details, in case they abuse!"
    )
    async def set_player_details(
        self, itx: discord.Interaction,
        member: discord.Member,
        balance: Optional[float],
        shoes: Optional[int]
    ):
        """
        Set balance/pos for the player, if event exists
        """
        if not await Event.exists(itx.guild_id, self.pool):
            await itx.response.send_message("Event does not exist", ephemeral = True)
            return

        player = await Player.create_profile(member.id, itx.guild_id, self.pool)

        changed = await player.modify_fields(balance = balance, pos = shoes)

        if changed:
            await itx.response.send_message("Details have been changed.")
        else:
            await itx.response.send_message("Provide details for the change.", ephemeral = True)

class EventCog(commands.GroupCog, name = "event"):
    def __init__(self, bot) -> None:
        self.bot = bot
        self.pool: Pool = self.bot.pool
    
    async def interaction_check(self, itx: discord.Interaction) -> bool:
        """
        Only allow users with admin permission
        """
        if itx.user.guild_permissions.administrator:
            return True

        await itx.response.send_message("You need admin perms", ephemeral = True)
        return False

    @app_commands.command(
        name = "start",
        description = "Start the event"
    )
    async def start_event(
        self, itx: discord.Interaction,
        giveaway_shoes: int,
        shoes_ores: int,
        channel: discord.TextChannel
    ):
        """
        Checks if event exists, if not then...
        - Creates new event record
        - Creates new view record
        - Send message in channel
        - Adds view to my_views botvar
        """
        if await Event.exists(itx.guild_id, self.pool):
            await itx.response.send_message("Event already exists!", ephemeral = True)
            return

        # deferring in case it takes too long    
        await itx.response.defer(thinking = True)
        
        # create event record
        await Event.create_event(self.pool, itx.guild_id, giveaway_shoes, channel, shoes_ores)

        # send view message, store to view table, append to my_views
        await send_view(self.pool, channel, self.bot.my_views)

        await itx.followup.send("Event has begun in this server!")

    @app_commands.command(
        name = "end",
        description = "End the event. Do not do this unless you are absolutely sure!"
    )
    async def end_event(self, itx: discord.Interaction):
        """
        Checks if event exists, if it does then...
        - Sends a final leaderboard message in channel
        - Deletes all player records of this guild
        - Deletes event record in events table
        - Deletes all view records of this guild in views table
        - Stops any active views
        - Removes view from my_views
        """
        if not await Event.exists(itx.guild_id, self.pool):
            await itx.response.send_message("Event does not exist", ephemeral = True)
            return
        
        # deferring in case it takes longer than 3 seconds
        await itx.response.defer(thinking = True)

        event = Event(itx.guild_id, self.pool)
        cid = await event.get_channel_id()
        channel = itx.guild.get_channel(cid)
        
        if channel is not None:
            # send leaderboard message
            embed = await event.show_leaderboard(itx.guild)
            await channel.send(embed = embed)

        # delete views of this channel_id (ie this guild)
        await ViewHelper.delete_views(self.pool, channel_ids = [cid])

        # get active view instance
        for x in self.bot.my_views:
            if x.view.cid == cid:
                # remove this view from my_views list, now that we are stopping it
                self.bot.my_views.remove(x)
                # stop the view
                x.stop()
                break

        # delete event and players record
        await event.end_event()

        await itx.followup.send("Adios my friend. Hope we meet again.")

    @app_commands.command(
        name = "config",
        description = "Change the channel given, shoes to giveaway from events or ores"
    )
    async def config_event(
        self, itx: discord.Interaction, 
        channel: Optional[discord.TextChannel],
        giveaway_shoes: Optional[int],
        ore_shoes: Optional[int]
    ):
        """
        If event exists...
        - Change event details
        """

        if not await Event.exists(itx.guild_id, self.pool):
            await itx.response.send_message("Event does not exist", ephemeral = True)
            return
        
        event = Event(itx.guild_id, self.pool)
        changed = await event.modify_details(new_channel = channel, pos_given = giveaway_shoes, shoe_ores = ore_shoes)
    
        if changed:
            embed = await event.get_info()
            await itx.response.send_message("Changes are in effect", embed = embed)
        else:
            await itx.response.send_message("Please provide something to change!", ephemeral = True)
      

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AdminCommands(bot))
    await bot.add_cog(EventCog(bot))