import asyncio
import asyncpg
from config import connection_uri
from params import first_price

async def main():
    # Establish a connection to an existing database
    conn = await asyncpg.connect(connection_uri)
    
    # Execute statement to create tables
    await conn.execute(
        '''
        CREATE TABLE IF NOT EXISTS players (
            user_id BIGINT NOT NULL,
            guild_id BIGINT NOT NULL,
            balance FLOAT DEFAULT 0.00,
            pos INT DEFAULT 0,

            PRIMARY KEY (user_id, guild_id)
        );
                       
        CREATE TABLE IF NOT EXISTS shoes (
            id SERIAL PRIMARY KEY,
            price_date TIMESTAMPTZ DEFAULT NOW(),
            price FLOAT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS events (
            guild_id BIGINT PRIMARY KEY,
            pos_given INT NOT NULL,
            channel_id BIGINT
        );

        CREATE TABLE IF NOT EXISTS views (
            id SERIAL PRIMARY KEY,
            channel_id BIGINT NOT NULL,
            message_id BIGINT,
            used_users BIGINT[] DEFAULT '{}',
            created_on TIMESTAMPTZ DEFAULT NOW()
        );
        '''
    )

    # set first shoe price, if no records exist
    exists = await conn.fetchval(
        '''
        SELECT EXISTS (SELECT 1 FROM shoes);
        '''
    )

    if not exists:
        await conn.execute(
            """
            INSERT INTO shoes (price)
            VALUES ($1);
            """,
            first_price
        )
    
    await do_updates(conn)

    # Close the connection.
    await conn.close()

async def do_updates(conn: asyncpg.connection.Connection):
    """
    This function runs all statements that are updates to the game
    """

    await conn.execute(
        """
        ALTER TABLE players
            ADD COLUMN IF NOT EXISTS day_ores INTEGER DEFAULT 0;
        
        ALTER TABLE events
            ADD COLUMN IF NOT EXISTS last_collect TIMESTAMPTZ DEFAULT NOW(),
            ADD COLUMN IF NOT EXISTS shoe_ores INTEGER DEFAULT 0; 
        """
    )

if __name__ == '__main__':
    asyncio.get_event_loop().run_until_complete(main())