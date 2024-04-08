from asyncpg import Pool
from discord import Embed, TextChannel, Guild
from discord.utils import utcnow
from datetime import timedelta
from numpy.random import normal

"""
EVENT PLAN

this is a simple event that is an indicator of the activity in the server.

every 12 hours, a message will appear, that will have a button active for 12 hours

Clicking this button gives you a pair of shoes.

For this server:

Only 3 POS would drop per 12 hours (restricting one player to only one POS)

Sell this POS. The selling cost would fluctuate like the stock market (on some days good price, other days bad price).

That is it as of now.
"""

"""
Programmable features:

1. Number of POS given every time interval
2. Time interval XXXXX
3. End event
"""

"""
Classes:

Player class
    INIT
    MODIFY_BALANCE
    SHOW_PROFILE

Shoe Class
    MODIFY_POS
    GET_PRICE

Event Class
    START_EVENT
    MODIFY_EVENT
    END_EVENT
    SEND_MSG
"""

"""
players
    user_id,
    guild_id,
    balance,
    pos

shoes
    price_date,
    price

events
    guild_id
    pos_given
    channel_id

views
"""

#################


class Player:
    def __init__(self, user_id: int, guild_id: int, pool: Pool) -> None:
        self.user_id = user_id
        self.guild_id = guild_id
        self.pool = pool
    
    @classmethod
    async def create_profile(cls, user_id: int, guild_id: int, pool: Pool):
        """
        Constructor. Checks if user record on table, and creates it if not
        """
        exists = await pool.fetchval("SELECT EXISTS (SELECT 1 FROM players WHERE user_id = $1 AND guild_id = $2)",
            user_id, guild_id)
        
        if not exists:
            await pool.execute("INSERT INTO players VALUES ($1, $2, 0, 0)", user_id, guild_id)

        return cls(user_id, guild_id, pool)
    
    async def __get_details(self, field: str = None):
        """
        Private method: Get specific details about player from database
        """
        row = await self.pool.fetchrow(
            "SELECT * FROM players WHERE user_id = $1 AND guild_id = $2", 
            self.user_id, self.guild_id
        )

        if field is not None:
            return row[field]
        else:
            return row
    
    async def claim_pos(self):
        """
        When claim pos button is clicked.

        increases pos by 1
        """
        await self.pool.execute("UPDATE players SET pos = pos + 1 WHERE user_id = $1 AND guild_id = $2",
            self.user_id, self.guild_id)
        
    async def sell_pos(self, quantity = 1) -> dict:
        """
        Sell POS gets price for the day and then adds it to the balance, along with reducing pos owned

        Returns dictionary containing "price" for the day and "profit" for the profit from pos sold 
        """
        # make sure quantity not greater than maximum
        pos = await self.__get_details('pos')
        
        if quantity > pos:
            quantity = pos
        elif quantity < 0:
            quantity = 0

        # get profit
        prices = await Shoe.get_price_history(self.pool, count = 1)
        price = prices[0]['price']
        profit = price * quantity

        # update database
        await self.pool.execute(
            """
            UPDATE players 
                SET pos = pos - $1, 
                balance = balance + $2
            WHERE user_id = $3 AND guild_id = $4
            """, quantity, profit, self.user_id, self.guild_id 
        )

        return {'price': price, 'profit': profit}

    async def modify_fields(self, *, balance: float = None, pos: int = None):
        """
        Manually update fields of player. Useful for admin command in case of abuse
        Returns bool for status of change
        """
        if None not in [balance, pos]:
            await self.pool.execute(
                "UPDATE players SET balance = $1, pos = $2 WHERE guild_id = $3 AND user_id = $4", 
                balance, pos, self.guild_id, self.user_id
            )
    
        elif balance is not None:
            await self.pool.execute("UPDATE players SET balance = $1 WHERE guild_id = $2 AND user_id = $3", 
                balance, self.guild_id, self.user_id)

        elif pos is not None:
            await self.pool.execute("UPDATE players SET pos = $1 WHERE guild_id = $2 AND user_id = $3", 
                pos, self.guild_id, self.user_id)
            
        # no details provided, return False    
        else:
            return False
        
        return True

    async def show_profile(self) -> Embed:
        """
        Create discord Embed for profile
        """
        # get player details
        row = await self.__get_details()
        pos = row["pos"]
        bal = round(row["balance"], 2)

        # create embed
        embed = Embed(
            title = "Player profile",
            description = f"**Pairs of shoes owned:** {pos}\n**Credts:** {bal}"    
        )

        return embed

class Shoe:
    @staticmethod
    async def check_last_change(pool: Pool):
        """
        Checks whether last change was 24 hours ago

        Useful for task which sets price every 24 hours
        """
        last_change = await pool.fetchval("SELECT price_date FROM shoes ORDER BY price_date DESC LIMIT 1")
        
        # if difference between time now and last change is greater than 24 hours (ie last pos happened more than 24 hours ago)
        # ... return True
        return (utcnow() - last_change) >= timedelta(hours = 24)

    @staticmethod
    async def get_price_history(pool: Pool, count:int = 10, date = None):
        """
        Get shoe price for last `count` days before `before` date
        """
        if date is None:
            date = utcnow()

        price_history = await pool.fetch("SELECT * FROM shoes WHERE price_date <= $1 ORDER BY price_date DESC LIMIT $2", date, count)
        
        return price_history
    
    @staticmethod
    async def set_price(pool: Pool, *, upper_limit: float = None, new_price = None) -> float:
        """
        Set price for current time. Either set new_price or upper_limit

        new_price is for setting price manually, for owner command
        
        For setting price automatically (i.e. from bg task):
        It will use the price last set as the base price. upper limit is the 
        standard deviation for the normal distribution for change
        returns new price
        """
        # making sure method returns None if both args are None
        price = None

        if upper_limit is not None:
            # getting value of change
            mu, sigma = 0.0, upper_limit
            change = normal(mu, sigma)

            base = await pool.fetchval("SELECT price FROM shoes ORDER BY price_date DESC LIMIT 1")

            price = base + change
        
        elif new_price is not None:
            price = new_price

        if price is not None:
            await pool.execute("INSERT INTO shoes (price) VALUES ($1)", price)

        return price
    
class Event:
    def __init__(self, guild_id: int, pool: Pool) -> None:
        self.guild_id = guild_id
        self.pool = pool
    
    @staticmethod
    async def exists(guild_id: int, pool: Pool) -> bool:
        """
        Returns boolean if event exists (True) or not (False)
        """
        exists = await pool.fetchval("SELECT EXISTS (SELECT 1 FROM events WHERE guild_id = $1)",
            guild_id)
        
        return exists
    
    @classmethod
    async def create_event(cls, pool: Pool, guild_id: int, pos_given: int, channel: TextChannel):
        """
        Constructor. ONLY USE IT FOR CREATING NEW EVENT.

        `pos_given` is the quantity to be given at each message "event"
        `channel` is where the message is going to be sent

        Note that this does not create the view or send the first event message.
        """

        await pool.execute("INSERT INTO events (guild_id, pos_given, channel_id) VALUES ($1,$2,$3)",
            guild_id, pos_given, channel.id)
        
        return cls(guild_id, pool)
    
    async def get_pos_given(self):
        """
        Get giveaway shoes for this guild
        """
        query = "SELECT pos_given FROM events WHERE guild_id = $1"
        return await self.pool.fetchval(query, self.guild_id)
    
    async def get_channel_id(self):
        """
        Get channel id for this guild
        """
        query = "SELECT channel_id FROM events WHERE guild_id = $1"
        return await self.pool.fetchval(query, self.guild_id)
    

    async def modify_details(self, *, new_channel: TextChannel = None, pos_given: int = None) -> bool:
        """
        Change channel for sending message, or change amount of pos given
        Returns bool whether any details were changed (True) or not (False)
        """
        if None not in [new_channel, pos_given]:
            await self.pool.execute("UPDATE events SET channel_id = $1, pos_given = $2 WHERE guild_id = $3", 
                new_channel.id, pos_given, self.guild_id)
    
        elif new_channel is not None:
            await self.pool.execute("UPDATE events SET channel_id = $1 WHERE guild_id = $2", 
                new_channel.id, self.guild_id)

        elif pos_given is not None:
            await self.pool.execute("UPDATE events SET pos_given = $1 WHERE guild_id = $2", 
                pos_given, self.guild_id)
        # no details provided, return False    
        else:
            return False
        
        return True
    
    async def get_player_records(self):
        """
        Gets player records for this guild in descending order of field (must be "pos" or "balance")

        Useful for leaderboards
        """
        records = await self.pool.fetch("SELECT * FROM players WHERE guild_id = $1 ORDER BY balance DESC",
            self.guild_id)
        return records

    async def end_event(self):
        """
        Ends event: removes db entry in events and players table for this guild
        """
        await self.pool.execute(
            """
            DELETE FROM players
                WHERE guild_id = $1;
            """,
            self.guild_id
        )
        
        await self.pool.execute(
            """
            DELETE FROM events
                WHERE guild_id = $1;
            """,
            self.guild_id
        )

    async def get_info(self) -> Embed:
        """
        Return info for the server in an embed: last_pos, channel, and today's price 
        """
        grecord = await self.pool.fetchrow("SELECT * FROM events WHERE guild_id = $1", self.guild_id)
        sell_price_record = await Shoe.get_price_history(self.pool, count = 1)
        sell_price = sell_price_record[0]['price']
        channel_id = grecord['channel_id']
        channel = f'<#{channel_id}>'

        em = Embed(title = "Your server info")
        em.description = f"**Current shoe sell price:** {sell_price}\nChannel: {channel}"

        return em
    
    async def show_leaderboard(self, guild: Guild) -> Embed:
        """
        Returns embed of top 10 players
        """
        records = await self.get_player_records()
        embed = Embed(description = "Sorted by balance:\n")
        truncated = records[:10] if len(records) > 9 else records

        for record in truncated:
            embed.description += "{0} - {1}\n".format(
                guild.get_member(record['user_id']).mention, 
                record['balance']
            )

        return embed


#             id SERIAL PRIMARY KEY,
#             channel_id BIGINT NOT NULL,
#             message_id BIGINT NOT NULL,
#             created_on TIMESTAMP WITH TIME ZONE,
#             used_users BIGINT[]


class ViewHelper:
    def __init__(self, pool: Pool, message_id: int, channel_id: int, id: int, used_users) -> None:
        self.pool = pool
        self.mid = message_id
        self.cid = channel_id
        self.id = id
        self.used_users = used_users

    @staticmethod
    async def get_views(pool: Pool):
        """
        Get views. 
        Useful when persistent views must be added when bot restarts
        """
        return await pool.fetch("SELECT * FROM views")

    @staticmethod
    async def get_overdue_views(pool: Pool):
        """
        Returns list of view records where last giveaway was 12 hours ago

        Useful for task which creates POS messages every 12 hours
        """
        # checks where NOW - created_on is greater than/= 12 hours (ie happened 12 hours ago atleast)
        overdue_views = await pool.fetch("SELECT * FROM views WHERE (NOW() - created_on) >= INTERVAL '30 minutes'")
        
        return overdue_views
             
    @staticmethod
    async def delete_views(pool: Pool, *, view_ids = None, channel_ids = None):
        """
        Deletes all view records for specified IDs
        """
        if view_ids is not None:
            await pool.execute("DELETE FROM views WHERE id = ANY($1)", view_ids)
        elif channel_ids is not None:
            await pool.execute("DELETE FROM views WHERE channel_id = ANY($1)", channel_ids)

    @staticmethod
    async def create_view(pool: Pool, channel_id: int, message_id: int):
        """
        Use for creating a new view record 
        """
        await pool.execute(
            """
            INSERT INTO views (channel_id, message_id)
            VALUES ($1, $2)
            """,
            channel_id, message_id
        )

    @classmethod
    async def from_message(cls, pool: Pool, message_id: int, channel_id: int):
        """
        Classmethod: get view object from message_id and channel_id
        """
        record = await pool.fetchrow("SELECT * FROM views WHERE message_id = $1 AND channel_id = $2",
            message_id, channel_id)
        
        return cls(pool, message_id, channel_id, record['id'], record['used_users'])
    
    def check_user(self, user_id: int) -> bool:
        """
        Checks if user already clicked the button
        """
        return user_id in self.used_users
    
    async def add_user(self, user_id: int):
        """
        Adds user to list of used_users
        """        
        self.used_users.append(user_id)
        await self.pool.execute("UPDATE views SET used_users = $1 WHERE id = $2",
            self.used_users, self.id)
        
    async def limit_reached(self, pos_given: int):
        """
        Checks whether max pos reached.
        """
        return len(self.used_users) >= pos_given




##################