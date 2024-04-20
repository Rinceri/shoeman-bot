from asyncpg import Pool
from discord import Embed, TextChannel, Guild, Colour
from discord.utils import utcnow, format_dt
from datetime import timedelta
import numpy as np
from params import VIEW_INTERVAL_HRS, PRICE_CHANGE_HRS, EMBED_COLOUR, mu, sd 

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
        ores = row['day_ores']

        # create embed
        embed = Embed(
            colour = Colour.from_str(EMBED_COLOUR),
            title = "Player profile",
            description = f"**Pairs of shoes owned:** {pos}\n**Credts:** {bal}\n**Ores:** {ores}"    
        )

        return embed

    async def add_ores(self, ores: int):
        """
        Adds ores to player database
        """
        await self.pool.execute("""
            UPDATE players 
            SET day_ores = day_ores + $1 
            WHERE user_id = $2 AND guild_id = $3""",
            ores, self.user_id, self.guild_id
        )

class Shoe:
    @staticmethod
    async def check_last_change(pool: Pool):
        """
        Checks whether last change was 24 hours ago

        Useful for task which sets price every 24 hours
        """
        last_change = await pool.fetchval("SELECT price_date FROM shoes ORDER BY price_date DESC LIMIT 1")
        
        # if difference between time now and last change is greater than 12 hours (ie last pos happened more than 12 hours ago)
        # ... return True
        return (utcnow() - last_change) >= timedelta(hours = PRICE_CHANGE_HRS)

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
    async def set_price(pool: Pool, new_price = None) -> float:
        """
        Set price for current time.

        new_price is for setting price manually, for owner command
        
        For setting price automatically (i.e. from bg task):
        It will use the price last set as the base price. 
        Using normal distribution for change, and adding to base, returns new price
        """
        if new_price is None:
            change = np.random.default_rng().normal(mu, sd)
            base = await pool.fetchval("SELECT price FROM shoes ORDER BY price_date DESC LIMIT 1")
            price = base + change
            
        else:
            price = new_price

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
    async def create_event(cls, pool: Pool, guild_id: int, pos_given: int, channel: TextChannel, shoe_ores: int):
        """
        Constructor. ONLY USE IT FOR CREATING NEW EVENT.

        `pos_given` is the quantity to be given at each message "event"
        `channel` is where the message is going to be sent
        `shoe_ores` is how many total shoes given per day to players' ore balance

        Note that this does not create the view or send the first event message.
        """

        await pool.execute("INSERT INTO events (guild_id, pos_given, channel_id, shoe_ores) VALUES ($1,$2,$3,$4)",
            guild_id, pos_given, channel.id, shoe_ores)
        
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
    

    async def modify_details(self, *, new_channel: TextChannel = None, pos_given: int = None, shoe_ores: int = None) -> bool:
        """
        Change channel for sending message, amount of pos given or shoe ores
        Returns bool whether any details were changed (True) or not (False)
        """
        status = False
        
        if None not in [new_channel, pos_given, shoe_ores]:
            await self.pool.execute(
                """
                UPDATE events 
                SET channel_id = $1, 
                pos_given = $2,
                shoe_ores = $3
                WHERE guild_id = $4
                """, 
                new_channel.id, pos_given, shoe_ores, self.guild_id
            )
            return True

        if new_channel is not None:
            await self.pool.execute("UPDATE events SET channel_id = $1 WHERE guild_id = $2", 
                new_channel.id, self.guild_id)
            status = True

        if pos_given is not None:
            await self.pool.execute("UPDATE events SET pos_given = $1 WHERE guild_id = $2", 
                pos_given, self.guild_id)
            status = True

        if shoe_ores is not None:
            await self.pool.execute("UPDATE events SET shoe_ores = $1 WHERE guild_id = $2", 
                shoe_ores, self.guild_id)
            status = True

        return status

    async def get_player_records(self, field = None):
        """
        Gets player records for this guild in descending order of "balance" (default) or "ores"

        Useful for leaderboards
        """
        if field == 'ores':
            db_field = 'day_ores'
        else:
            db_field = 'balance'

        records = await self.pool.fetch(f"SELECT * FROM players WHERE guild_id = $1 ORDER BY {db_field} DESC",
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
        Return info for the server in an embed: last_pos, channel, and shoe_ores
        """
        grecord = await self.pool.fetchrow("SELECT * FROM events WHERE guild_id = $1", self.guild_id)
        channel_id = grecord['channel_id']
        channel = f'<#{channel_id}>'
        shoe_ores = grecord['shoe_ores']
        next_collect = timedelta(hours = 24) + grecord['last_collect']


        em = Embed(title = "Your server info")
        em.description = f"Channel: {channel}"

        em.add_field(name = "Shoes given per day based on ores", value = shoe_ores)
        em.add_field(name = "Next shoe reward (ores)", value = format_dt(next_collect, 'R'))

        return em
    
    async def show_leaderboard(self, guild: Guild) -> Embed:
        """
        Returns embed of top 10 players
        """
        records = await self.get_player_records()
        embed = Embed(
            title = "Leaderboard (top 10)", 
            timestamp = utcnow(),
            colour = Colour.from_str(EMBED_COLOUR)
        )

        # no players registered for this guild 
        if records == []:
            embed.description = "There are no players playing here..."
            return embed

        embed.description = ""
        embed.set_footer(text = "Sorted by balance")

        for position, record in enumerate(records, start = 1):
            embed.description += "{0}. {1} - **{2} coins and {3} shoes**\n".format(
                position,
                guild.get_member(record['user_id']).mention, 
                int(record['balance']),
                record['pos']
            )

            # 10 players reached
            if position >= 10:
                break

        return embed
    
    async def show_ore_leaderboard(self, guild: Guild) -> Embed:
        """
        Returns embed of top 10 players by ore
        """
        records = await self.get_player_records("ores")
        embed = Embed(
            title = "Ores Leaderboard (top 10)", 
            timestamp = utcnow(),
            colour = Colour.from_str(EMBED_COLOUR)
        )

        # no players registered for this guild 
        if records == []:
            embed.description = "There are no players playing here..."
            return embed

        embed.description = ""
        embed.set_footer(text = "Sorted by ores")

        for position, record in enumerate(records, start = 1):
            embed.description += "{0}. {1} - **{2} ores**\n".format(
                position,
                guild.get_member(record['user_id']).mention, 
                record['day_ores'],
            )

            # 10 players reached
            if position >= 10:
                break

        return embed


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
        if isinstance(VIEW_INTERVAL_HRS, int):
            # NOTE: this is very dangerous.
            query = "SELECT * FROM views WHERE (NOW() - created_on) >= INTERVAL '{0} hours'".format(VIEW_INTERVAL_HRS)

        # checks where NOW - created_on is greater than/= 12 hours (ie happened 12 hours ago atleast)
        overdue_views = await pool.fetch(query)
        
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