# Hanabi-Suite

This is my personal attempt to write hanabi-related code to analyse and play around with the game.
The main goals of the code are:

- Provide an easy-to-use interface that supports all the variants available at hanab.live (some variants not supported yet)
- Store data in a local database that mirrors (part of) the hanab.live database
    - This allows local analysis of a large sample of real-world hanab games played
    - It also allows us to store additional data for games / seeds etc, like: Is this seed theoretically winnable etc
- Develop fast, exact algorithms to test for feasibility of instances
- Develop bots that can play hanabi reasonably well, both for cheating and solitaire versions of the game
- Have analysis tools for actual games played (from which turn onwords did we lose? What was the correct winning line in the end?)

Apart from the obvious use-cases for some features, I want to explore boundaries of the following questions:
- What percentage of games is theoretically winnable, assuming perfect information? (solitaire play)
    - To answer this, we need fast, exact algorithms and run them on larg samples of seeds
- What percentage of games is theoretically winnable by only looking at drawn cards, but not into the draw pile (cheating play)?
    - I guess we need to write a very good bot here, based on https://github.com/fpvandoorn/hanabi


# Alternative stuff that I would also like to try out eventually
- Have some sort of endgame database, both for solitaire and cheating play
- Develop certificates for infeasibility of hanab instances (I don't think the problem lies in coNP, but for real-world instances, most decks seems to have a short explanation on why they are not winnable)
- Have analysis tools that can compute optimal moves in cheating play for endgame situations (and display winning percentages)
- Analyse every seed on hanab.live for feasibility



Clearly, there is still much work to do, any contributions, suggestions etc are welcome

