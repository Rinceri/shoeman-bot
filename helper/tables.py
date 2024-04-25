from orm import MyORM
from orm import Condition

class PlayerTable(MyORM):
    guild_id = "guild_id"
    player_id = "user_id"
    balance = "balance"
    shoes = "pos"
    ores = "day_ores"

    def __init__(self, guild_id: int = None, user_id: int = None) -> None:
        super().__init__("players")
        self.keys = (
            Condition(self.guild_id, value = guild_id), 
            Condition(self.player_id, value = user_id)
        )

class EventTable(MyORM):
    guild_id = "guild_id"
    shoes_given = "pos_given"
    channel_id = "channel_id"
    last_ore_collect = "last_collect"
    shoe_ores = "shoe_ores"

    def __init__(self, guild_id: int = None) -> None:
        super().__init__("events")
        self.keys = (Condition(self.guild_id, value = guild_id))

class ShoeTable(MyORM):
    price = "price"
    set_on = "price_dat"

    def __init__(self) -> None:
        super().__init__("shoes")


class ViewTable(MyORM):
    id = "id"
    channel_id = "channel_id"
    message_id = "message_id"
    used_users = "used_users"
    created_on = "created_on"

    def __init__(self, channel_id: int = None, message_id: int = None) -> None:
        super().__init__("views")
        self.keys = (
            Condition(self.channel_id, value = channel_id), 
            Condition(self.message_id, value = message_id)
        )