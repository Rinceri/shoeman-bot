from typing import Literal, Optional
import helper.objects as o
import discord
from discord.ext import commands
from asyncpg import Pool

class Owner(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.pool: Pool = self.bot.pool

    async def cog_check(self, ctx: commands.Context) -> bool:
        return await self.bot.is_owner(ctx.author)

    @commands.guild_only()
    @commands.command(hidden = True)
    async def sync(self, ctx: commands.Context, guilds: commands.Greedy[discord.Object], spec: Optional[Literal["~", "*", "^"]] = None) -> None:
        """
        Sync commands (Owner only)
        """
        # FOR TESTING: SYNC * -> SYNC ^ -> SYNC
        # IE: sync to testing guild, remove all commands from testing guild, sync to all guilds

        if not guilds:
            # This will sync all GUILD commands for the current context’s guild
            # it will not sync GLOBAL commands that haven't been synced yet
            # USE FOR: syncing guild commands of this guild to discord
            if spec == "~":
                synced = await ctx.bot.tree.sync(guild=ctx.guild)
            
            # copies all global commands (and guild commands of that guild) to current guild, and syncs
            # USE FOR: testing global commands before releasing
            # CAUTION: clear commands for guild after, as it creates two copies of commands that...
            # have been synced before 
            elif spec == "*":
                ctx.bot.tree.copy_global_to(guild=ctx.guild)
                synced = await ctx.bot.tree.sync(guild=ctx.guild)
            
            # removes guild commands from this guild
            # USE FOR: clearing testing commands from test guild
            # CAUTION: removes guild commands too. make sure to add them back if there are any
            elif spec == "^":
                ctx.bot.tree.clear_commands(guild=ctx.guild)
                await ctx.bot.tree.sync(guild=ctx.guild)
                synced = []
            
            # sync global tree to discord
            # USE FOR: releasing global commands to all servers
            else:
                synced = await ctx.bot.tree.sync()

            await ctx.send(
                f"Synced {len(synced)} commands {'globally' if spec is None else 'to the current guild.'}"
            )
            return

        ret = 0
        for guild in guilds:
            try:
                await ctx.bot.tree.sync(guild=guild)
            except discord.HTTPException:
                pass
            else:
                ret += 1

        await ctx.send(f"Synced the tree to {ret}/{len(guilds)}.")

    @commands.command(hidden = True)
    async def set_pos(self, ctx: commands.Context, amount: float):
        """
        Set price of shoes manually. Note that the price is recorded and doesn't change until 24 hours are up (owner only)
        """
        now = discord.utils.utcnow()

        await o.Shoe.set_price(self.pool, new_price = amount)

        await ctx.send(f"Price set to: {amount} on {discord.utils.format_dt(now, 'F')}")
    
    @commands.command(hidden = True)
    async def test(self, ctx: commands.Context):
        """
        Test command (owner only)
        """
        
        await ctx.send("Test successful!")

    @commands.command(hidden = True)
    async def load(self, ctx: commands.Context, extension: str):
        """
        Loads an extension
        """
        await self.bot.load_extension(f'cogs.{extension}')
        await ctx.send("Loaded your extension.")

    @commands.command(hidden = True)
    async def reload(self, ctx: commands.Context, extension: str):
        """
        Reload an extension
        """
        await self.bot.reload_extension(f'cogs.{extension}')
        await ctx.send("Reloaded your extension.")

    @commands.command(hidden = True)
    async def unload(self, ctx: commands.Context, extension: str):
        """
        Unloads an extension
        """
        await self.bot.unload_extension(f'cogs.{extension}')
        await ctx.send("Unloaded your extension.")

async def setup(bot: commands.Bot):
    await bot.add_cog(Owner(bot))