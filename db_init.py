import asyncio
import asyncpg
from config import connection_uri, first_price

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

    # set first shoe price
    await conn.execute(
        '''
        INSERT INTO shoes (price)
        VALUES ($1);
        ''',
        first_price
    )

    # Close the connection.
    await conn.close()

asyncio.get_event_loop().run_until_complete(main())