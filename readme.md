# Polysynth volume bot

The script helps to run USDC through a lot of wallets (open-close position in a few iterations and send tokens to the next wallet). It is created to work with Polysynth (Polygon), however it could be updated and used for other protocols (DEXes).

First steps:

1. Clone repo
2. Run "python3 -m venv" (if virtual environment not created)
3. Run "pip3 install -r requirements.txt"
4. Rename and update config.jsonexample (must be config.json)
5. Run main.py

Folder keys should contain a separate txt file named as ID of profile in AdsPower. Each file should contain a seed phrase for that profile (1 row).

TODO:
- clean up the code
- save functions in a separate module
- add comments
- docker
