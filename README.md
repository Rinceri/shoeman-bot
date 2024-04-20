# shoeman-bot (Discord bot)

A discord game bot written in Python. 

[Invite the bot](https://discord.com/oauth2/authorize?client_id=1226544956903260220)

## How the bot works
The end goal is to get as much money as possible. This is mainly done by selling shoes based on a price that fluctuates globally every few hours (by default 12 hours). The change in price is modelled by a normal distribution with a default mean of 0 and standard deviation of 100.

You can get shoes by a "button event" that runs, by default, every 12 hours. Basically a message would appear with a button that would increment the number of shoes owned. Only a limited number of shoes would be available to be given away per server, which can be set by the event admin.

You can also "mine" ores, which every 24 hours would be exchanged for shoes based on the contribution of a player's ores to total ores in the entire server. The total number of shoes available for giving away in a server can be set by the event admin. So, shoes here would be distributed based on the ores mined for the day.

When running `event start` or `event config`...
- `channel` is where the button event message would be sent,
- `giveaway_shoes` denotes number of shoes to giveaway every button event,
- `shoes_ores` denotes number of shoes distributed in total, based on ore reward.

## Running the bot
In case you decide to run the bot on your own, follow the below steps:
1. Make sure you have Python 3 and PostgreSQL installed.
2. Create `config.py` file in the root directory (i.e. same level as `main.py`), with the following lines:
```py
connection_uri = # your postgresql connection uri
token = # your bot token
```
3. (Optional) Run `python3 -m venv .venv` to create a virtual environment, and run `source .venv/bin/activate` to activate it.
4. Run `pip install -r requirements.txt` to install all necessary libraries
5. If you want, edit the `params.py` according to your own likings:
```py
first_price = # first shoe price
mu = # mean, for normal distribution 
sd = # standard deviation for normal distribution

PRICE_CHANGE_HRS = # how often the shoe price changes, in hours
VIEW_INTERVAL_HRS = # how often a button event is sent, in hours
EMBED_COLOUR = # embed colour for all embeds, in hex
```
6. Run the `db_init.py` file to initialise the tables and values in the database.
7. Run the `main.py` file for starting the bot.

### Contributing
Any suggestions are always welcome, and feel free to report any bugs you encounter.