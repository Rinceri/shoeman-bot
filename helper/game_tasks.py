import discord
from discord.ext import commands
from asyncpg import Pool

from helper.objects import Shoe, ViewHelper, Player, Event
from config import sd

# views (
#             id SERIAL PRIMARY KEY,
#             guild_id BIGINT NOT NULL,
#             message_id BIGINT NOT NULL,
#             created_on TIMESTAMP WITH TIME ZONE,
#             used_users BIGINT[]
# events (
#             guild_id BIGINT PRIMARY KEY,
#             pos_given INT NOT NULL,
#             channel_id BIGINT PRIMARY KEY
#         );

# IMPORTANT
# records to view tables can only be added/removed 
# ... when creating first giveaway in a guild
# ... when renewing the shoe giveaway

async def price_fluct(pool: Pool):
    """
    Fluctuates price once 24 hours are up
    """
    # check last change
    if await Shoe.check_last_change(pool):
        await Shoe.set_price(pool, upper_limit = sd)
    
async def pos_giveaway(bot: commands.Bot, pool: Pool):
    """
    Does the following things:
    - Removes views which are overdue from views table
    - Stops these views
    - Removes these views from botvar list my_views
    - For the same channels, send a message with new view
    - Adds it to the views table
    - Adds the view to botvar list my_views
    """

    # get all views that are overdue
    inv_views = await ViewHelper.get_overdue_views(pool)
    cids = set()

    for record in inv_views:
        # get view to stop
        for x in bot.my_views:
            if x.view.id == record['id']:
                # remove this view from my_views list, now that we are stopping it
                bot.my_views.remove(x)
    
                # stop the view
                x.stop()

                break
    
        # add to set of channel ids to remove from views table
        # ... and for sending new views
        # this is done later when all cids are collected
        # note that set is being used to avoid duplicates
        cids.add(record['channel_id'])

    # all ids to remove have been collected
    # ... now remove them from views table
    await ViewHelper.delete_views(pool, channel_ids = cids)

    for cid in cids:
        # send new view message to channel
        channel = bot.get_channel(cid)

        if channel:
            await send_view(pool, channel, bot.my_views)
            

async def send_view(pool: Pool, channel: discord.TextChannel, my_views):
    """
    Use when sending new view to channel
    - Send view to channel
    - Create view record
    - Append view object to my_views
    """
    view = GiveawayView(pool)
    em = discord.Embed(description = "Claim these shoes NOW!!")

    # send message in channel with view
    msg = await channel.send(embed = em, view = view)

    # create view record, now that we have message ID
    await ViewHelper.create_view(pool, channel.id, msg.id)

    # assign view.view to ViewHelper object
    view.view = await ViewHelper.from_message(pool, msg.id, channel.id)

    # add view to my_views
    my_views.append(view)

class GiveawayView(discord.ui.View):
    def __init__(self, pool: Pool, view: ViewHelper = None):
        self.pool = pool
        self.view = view
        super().__init__(timeout = None)

    async def interaction_check(self, itx: discord.Interaction) -> bool:
        if self.view.check_user(itx.user.id):
            await itx.response.send_message("You can only claim once.", ephemeral = True)
            return False
        return True

    @discord.ui.button(label = "Claim shoes", style = discord.ButtonStyle.green, custom_id = "giveeaway:claim_shoes")
    async def claim_shoes(self, itx: discord.Interaction, button: discord.ui.Button):        
        # add user to used_users, now that they haven't claimed it yet
        await self.view.add_user(itx.user.id)
        
        # add the claimed shoes to the player's record
        player = await Player.create_profile(itx.user.id, itx.guild_id, self.pool)
        await player.claim_pos()

        pos_given = await Event(itx.guild_id, self.pool).get_pos_given()

        # if limit reached, disable the button
        # note that we dont stop() the view or delete it from record
        # this is so that it is done in the giveaway task
        # OPTIONAL: send message about disabled button
        if await self.view.limit_reached(pos_given):
            button.disabled = True
            await itx.response.edit_message(view = self)
            await itx.followup.send("You got your pair of shoes!", ephemeral = True)
        else:
            await itx.response.send_message("You got your pair of shoes!", ephemeral = True)