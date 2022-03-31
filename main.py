from web3 import Web3
from polysynth import Polysynth

import json
import csv
import requests
import pandas as pd
import time

from constants import *


# ----------------------------------------------------------------
# SET UP
# ----------------------------------------------------------------

# Read the configuration file
with open('config.json') as config:
    CONFIG = json.load(config)

# Get ERC20 ABI contract specification (for transfers of USDC)
abi = json.loads(ERC20_ABI)

# Create a connection to RPC (infura mkolki33@gmail.com, Polygon Mainnet)
w3 = Web3(Web3.HTTPProvider(CONFIG['HTTP_PROVIDER']))
print('Connection to HTTP provider established') if w3.isConnected()\
    else print('Connection to HTTP provider not established')
quit() if not w3.isConnected() else None
w3.eth.account.enable_unaudited_hdwallet_features()

# USDC contract
usdc_contract_address = Web3.toChecksumAddress(USDC_ADDRESS)
usdc_contract_instance = w3.eth.contract(address=usdc_contract_address, abi=abi)

# Variables
previous_address = ''
previous_privatekey = ''
tx_timeout = 300  # seconds
tr_counter = 0
tr_mxcounter = 10
tr_side = 'Buy'
tr_size = 50
tr_leverage = 1
tr_slippage = 0.01
send_funds = False  # Update the flag after the first iteration completed

# Get IDs of profiles which already processed (create the list of strings)
df_processed = pd.read_csv(CONFIG['PROCESSED_IDS'], names=['id'])

# List all AdsPower profiles
list_url = '{}:{}/api/v1/user/list?page_size={}'.format(CONFIG['ADSPOWER_URL'],
                                                        CONFIG['ADSPOWER_PORT'],
                                                        CONFIG['PAGE_SIZE'],)
resp_list = requests.get(list_url).json()

# Initiate Polysynth object and update it each time
poly_account = Polysynth(address=CONFIG['SAMPLE_ADDRESS'], private_key=CONFIG['SAMPLE_PK'],
                         provider=CONFIG['HTTP_PROVIDER'], web3=w3,
                         default_slippage=0.1)

# ----------------------------------------------------------------
# PROCESS EACH PROFILE IN THE LOOP
# ----------------------------------------------------------------

# Start processing each profile
for profile in resp_list['data']['list']:

    # Check if the profile has been processed before
    if profile['user_id'] in df_processed.values:
        print('{} already processed ({})'.format(profile['user_id'], profile['name']))
        # Go to next profile in the list
        continue
    print('{} is being processed ({})'.format(profile['user_id'], profile['name']))

    # Get the seed of the current profile and restore the account (public, private key)
    with open(CONFIG['FOLDER_KEYS'] + '{}.txt'.format(profile['user_id']), newline='') as f:
        r = csv.reader(f)
        seed = next(r)[0]
    account = w3.eth.account.from_mnemonic(seed)
    address = Web3.toChecksumAddress(account.address)  # public key (address)
    private_key = Web3.toHex(account.privateKey)

    # Send funds from the previous wallet if required
    if send_funds:
        # Send USDC funds from previous wallet to the current one
        usdc_balance = usdc_contract_instance.functions.balanceOf(previous_address).call()  # Convert to decimal human readable value
        if usdc_balance / 1000000 < tr_size * 1.1:
            raise Exception('{} has not enough USDC'.format(profile['user_id']))

        # Get nonce
        nonce = w3.eth.getTransactionCount(previous_address)

        # Create a transaction
        tx = usdc_contract_instance.functions.transfer(address, usdc_balance).buildTransaction({
            'chainId': 137,  # Polygon Mainnet
            'nonce': nonce,
            'gas': 100000,
            'maxFeePerGas': w3.toWei(35, 'gwei'),
            'maxPriorityFeePerGas': w3.toWei(35, 'gwei')
        })

        # Sign and send the transaction
        signed_tx = w3.eth.account.signTransaction(tx, previous_privatekey)
        tx_hash = w3.eth.sendRawTransaction(signed_tx.rawTransaction)

        # Check the transaction status
        tx_receipt = w3.eth.wait_for_transaction_receipt(tx_hash, tx_timeout)
        if tx_receipt['status'] == 1:
            print('Transaction is successful')
        else:
            raise Exception('Bad transaction')

        # Send all MATIC funds
        matic_balance = Web3.fromWei(w3.eth.get_balance(previous_address), 'ether')
        if matic_balance < 0.5:
            raise Exception('{} has not enough MATIC'.format(profile['user_id']))

        # Get nonce
        time.sleep(10)
        nonce = w3.eth.getTransactionCount(previous_address)

        tx = {
            'chainId': 137,  # Polygon Mainnet
            'nonce': nonce,
            'to': address,
            'value': w3.toWei(matic_balance, 'ether') - 50000 * w3.toWei(35, 'gwei'),
            'gas': 50000,
            'maxFeePerGas': w3.toWei(35, 'gwei'),
            'maxPriorityFeePerGas': w3.toWei(35, 'gwei')
        }

        # Sign and send the transaction
        signed_tx = w3.eth.account.signTransaction(tx, previous_privatekey)
        tx_hash = w3.eth.sendRawTransaction(signed_tx.rawTransaction)

        # Check the transaction status
        tx_receipt = w3.eth.wait_for_transaction_receipt(tx_hash, tx_timeout)
        if tx_receipt['status'] == 1:
            print('Transaction is successful')
        else:
            raise Exception('Bad transaction')

    # ----------------------------------------------------------------
    # DEAL WITH POLYSYNTH DEX
    # ----------------------------------------------------------------

    # Update Polysynth object (workaround)
    poly_account.address = address
    poly_account.private_key = private_key
    poly_account.update_nonce()

    # Run open-close position loop
    while tr_counter < tr_mxcounter:
        # Try-catch for the whole iteration
        try:
            # If position left opened - close all
            print('Check positions')
            positions = poly_account.positions()
            if positions['data'] != '':
                # Consider we have 3 attempts to close all positions, otherwise - throw an exception
                for attempt in range(3):
                    try:
                        # If we have no position - break
                        positions = poly_account.positions()
                        if positions['data'] == '':
                            break
                        status_close = poly_account.close_position(CONFIG['MARKET'], tr_slippage)
                        if status_close['error']['code'] != '' or status_close['status_code'] != 200:
                            raise Exception('Position not closed. Exception occurred.')
                    except Exception as e:
                        # Next attempt
                        time.sleep(5)
                        print(e.args)
                        print('Retry')
                        continue
                    else:
                        break
                else:
                    raise Exception('Position not closed. Exception occurred.')
            print('Positions checked')

            # Try to open a new position
            # Consider we have 3 attempts to open a new position, otherwise - throw an exception
            for attempt in range(3):
                try:
                    # If we have an opened position - break
                    positions = poly_account.positions()
                    if positions['data'] != '':
                        break
                    status_open = poly_account.open_position(CONFIG['MARKET'], tr_side, tr_size, tr_leverage, tr_slippage)
                    if status_open['error']['code'] != '' or status_open['status_code'] != 200:
                        raise Exception('Position not opened. Exception occurred.')
                except Exception as e:
                    # Next attempt
                    time.sleep(5)
                    print(e.args)
                    print('Retry')
                    continue
                else:
                    break
            else:
                raise Exception('Position not opened. Exception occurred.')
            print('Position opened')

            # Try to close (the same approach as in the beginning of the loop)
            # Consider we have 3 attempts to close all positions, otherwise - throw an exception
            for attempt in range(3):
                try:
                    # If we have no position - break
                    positions = poly_account.positions()
                    if positions['data'] == '':
                        break
                    status_close = poly_account.close_position(CONFIG['MARKET'], tr_slippage)
                    if status_close['error']['code'] != '' or status_close['status_code'] != 200:
                        raise Exception('Position not closed. Exception occurred.')
                except Exception as e:
                    # Next attempt
                    time.sleep(5)
                    print(e.args)
                    print('Retry')
                    continue
                else:
                    break
            else:
                raise Exception('Position not closed. Exception occurred.')
            print('Position closed')

            tr_counter += 1
            print('Iteration ' + str(tr_counter) + ' finished')
        # Try-catch for the whole iteration
        except:
            print('Retry iteration ' + str(tr_counter))
            continue

    # ----------------------------------------------------------------
    # FINISH
    # ----------------------------------------------------------------

    # Additional check of balance
    time.sleep(10)
    matic_balance = Web3.fromWei(w3.eth.get_balance(address), 'ether')
    if matic_balance < 0.5:
        raise Exception('{} has not enough MATIC'.format(profile['user_id']))

    usdc_balance = usdc_contract_instance.functions.balanceOf(address).call()  # Convert to decimal human readable value
    if usdc_balance / 1000000 < tr_size * 1.1:
        for attempt in range(3):
            try:
                # If we have no position - break
                positions = poly_account.positions()
                if positions['data'] == '':
                    break
                status_close = poly_account.close_position(CONFIG['MARKET'], tr_slippage)
                if status_close['error']['code'] != '' or status_close['status_code'] != 200:
                    raise Exception('Position not closed (iteration finished). Exception occurred.')
            except Exception as e:
                # Next attempt
                time.sleep(5)
                print(e.args)
                print('Retry')
                continue
            else:
                break
        else:
            raise Exception('Position not closed (iteration finished). Exception occurred.')
        print('Position closed (iteration finished)')

    # Save processed ID to the file
    with open(CONFIG['PROCESSED_IDS'], 'a', newline="") as file:
        writer = csv.writer(file)
        writer.writerow([profile['user_id']])

    # Set flag to send funds in the beginning of next iteration, clean Polysynth instance
    send_funds = True
    previous_address = address
    previous_privatekey = private_key

    tr_counter = 0
    time.sleep(10)
