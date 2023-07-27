# Hanabi-Suite

Disclaimer: This repository is still not in a good cleaned up code style, mainly due to me lacking time to clean stuff up properly.
Do not expect everything to work, do not expect everything to be well-documented.
However, I try to improve this from now on so that eventually, reasonable interfaces will exist so that this becomes actually more usable than now


## What is this?

This is my personal attempt to write hanabi-related code to analyse and play around with the game.
The main goals of the code are:

- Provide an easy-to-use interface that supports all the variants available at hanab.live (some variants not supported yet)
- Store data in a local database that mirrors (part of) the hanab.live database
    - This allows local analysis of a large sample of real-world hanab games played
    - It also allows us to store additional data for games / seeds etc, like: Is this seed theoretically winnable etc
- Develop fast, exact algorithms to test for feasibility of instances
- Develop bots that can play hanabi reasonably well, both for cheating and solitaire versions of the game
- Have analysis tools for actual games played (from which turn onwords did we lose? What was the correct winning line in the end?)

Clearly, there is still much work to do, any contributions, suggestions etc are welcome


## What is this good for?

Apart from the obvious use-cases for some features, I want to explore boundaries of the following questions:
- What percentage of games is theoretically winnable, assuming perfect information? (solitaire play)
    - To answer this, we need fast, exact algorithms and run them on larg samples of seeds
- What percentage of games is theoretically winnable by only looking at drawn cards, but not into the draw pile (cheating play)?
    - I guess we need to write a very good bot here, based on https://github.com/fpvandoorn/hanabi


## Alternative stuff that I would also like to try out eventually
- Have some sort of endgame database, both for solitaire and cheating play
- Develop certificates for infeasibility of hanab instances (I don't think the problem lies in coNP, but for real-world instances, most decks seems to have a short explanation on why they are not winnable)
- Have analysis tools that can compute optimal moves in cheating play for endgame situations (and display winning percentages)
- Analyse every seed on hanab.live for feasibility


## Installation

### Python
The hanabi folder is a working python package that you should be able to import if it's in your python path.
You will need to install the `requirements.txt` as usual, I recommend setting up a `venv`:
```
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### PostgreSQL
You need to install PostgreSQL on your system, for installation instructions refer to your distribution.
Create a new database and user, for example:
```
$ sudo -iu postgres
$ psql
# CREATE DATABASE "hanab-live";
# \c hanab-live
# CREATE USER hanabi WITH PASSWORD 'Insert password here';
# GRANT ALL PRIVILEGES ON DATABASE "hanab-live" TO hanabi;
# GRANT USAGE ON SCHEMA public TO hanabi;
# GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO hanabi;
# GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO hanabi;
```
Put the connection parameters in a config file (for the format, see `example_config.yaml`).
This should be located at your system default for the application `hanabi-suite`,
on POSIX systems this should be `~/.config/hanabi-suite/config.yaml`.


## Usage of stuff that already works:
Use the `hanabi_suite.py` CLI interface to download games and analyze them.
An initial setup might look like this:

```
hanabi_cli.py gen-config                    // Generates configuration file for DB connection parameters and prints its location
<Edit your configuration file>
hanabi_cli.py init                          // Initializes database tables
hanabi_cli.py download --var 0              // Donwloads information on all 'No Variant' games
hanabi_cli.py analyze --download <game id>  // Downloads and analyzes game from hanab.live
```
