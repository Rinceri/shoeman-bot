import discord
from discord.ext import commands
from asyncpg import Pool

from params import EMBED_COLOUR

from helper.objects import Shoe, ViewHelper, Player, Event

# IMPORTANT
# records to view tables can only be added/removed 
# ... when creating first giveaway in a guild
# ... when renewing the shoe giveaway

async def price_fluct(pool: Pool):
    """
    Fluctuates price once designated interval is up
    """
    # check last change
    if await Shoe.check_last_change(pool):
        await Shoe.set_price(pool)
    
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
            
async def send_shoe_ores(pool: Pool):
    """
    Calculates shoes per person based on ore reward, 
    for each guild that has surpassed a day in last_collect
    """
    
    # get sum of all guilds
    guild_ores = await pool.fetch("SELECT guild_id, sum(day_ores) AS day_ores FROM players GROUP BY guild_id;")

    # get all players that are in overdue guilds (overdue ie >24 hours)
    players = await pool.fetch(
        """
        SELECT players.* FROM players
        INNER JOIN events ON players.guild_id = events.guild_id
        WHERE (NOW() - events.last_collect) >= INTERVAL '24 hours';
        """
    )

    # if there are no overdue guilds, just finish the task
    if players == []:
        return

    # update guilds with overdue timer
    # I am doing this update here so there is no delay between fetching and updating
    await pool.execute(
        """
        UPDATE events
        SET last_collect = NOW()
        WHERE (NOW() - last_collect) >= INTERVAL '24 hours';
        """
    )

    player_frac = 0
    insert_players = []

    # iterate through all these players
    for player in players:
        # just move on if player has no ores
        if player['day_ores'] == 0:
            continue

        # get player's fraction of total ores
        for guild in guild_ores:
            if guild['guild_id'] == player['guild_id']:
                # note that we don't check if guild's total ores is not zero
                # (to prevent division by zero)
                # we skipped all players who have zero ores, and so any players who go through this section
                # ... will have >0 ores and hence >0 guild's total ores
                player_frac = player['day_ores'] / guild['day_ores']
                    
                # get total shoes given away
                shoes = await pool.fetchval("SELECT shoe_ores FROM events WHERE guild_id = $1", player['guild_id'])

                # get player shoes
                # note that I am not keeping track of total shoes
                # so it will give away more than total shoes in some situations
                player_shoes = round(player_frac * shoes)

                # insert to a list of tuples (player_id, guild_id, shoes)
                # note that players who have 0 ores will not be updated, because there's nothing to update
                insert_players.append((player_shoes, player['user_id'], player['guild_id']))

                # we found our record, break from guilds loop
                break

    # update shoes using list of tuples, and reset day_ores to 0
    await pool.executemany(
        """
        UPDATE players
        SET pos = pos + $1, day_ores = 0
        WHERE user_id = $2 AND guild_id = $3;
        """,
        insert_players
    )

async def make_giveaway_embed(pool: Pool, guild_id: int, pos_given: int = None, description: str = None) -> discord.Embed:

    if pos_given is None:
        pos_given = await Event(guild_id, pool).get_pos_given()

    embed = discord.Embed(
        colour = discord.Colour.from_str(EMBED_COLOUR),
        title = "Claim these shoes NOW!",
        description = "Nobody has claimed it yet!"
    )

    if description is not None:
        embed.description = description

    embed.set_footer(text = f"{pos_given} shoes available")

    return embed

async def send_view(pool: Pool, channel: discord.TextChannel, my_views):
    """
    Use when sending new view to channel
    - Send view to channel
    - Create view record
    - Append view object to my_views
    """
    view = GiveawayView(pool)
    em = await make_giveaway_embed(pool, channel.guild.id)

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

        # edit giveaway embed to show all claims
        description = "Claimed by: " + ", ".join([itx.guild.get_member(x).mention for x in self.view.used_users])
        embed = await make_giveaway_embed(self.pool, itx.guild_id, pos_given, description)

        # if limit reached, disable the button
        # note that we dont stop() the view or delete it from record
        # this is so that it is done in the giveaway task
        if await self.view.limit_reached(pos_given):
            button.disabled = True

        await itx.response.edit_message(embed = embed, view = self)
        await itx.followup.send("You got your pair of shoes!", ephemeral = True)