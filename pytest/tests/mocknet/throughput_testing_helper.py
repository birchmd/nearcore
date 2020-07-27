# This file is uploaded to each mocknet node and run there.
# It is responsible for making the node send transactions to itself.

import base58
import json
from rc import pmap
import requests
import sys
import time

sys.path.append('lib')
from cluster import Key
from mocknet import NUM_NODES
from account import Account

LOCAL_ADDR = '127.0.0.1'
RPC_PORT = '3030'
NUM_ACCOUNTS = 100
BASE_TPS = 100  # baseline tps
SPIKE_TPS = 2000  # tps at peak
SPIKE_DURATION = 5  # number of seconds to send with peak load
TIME_BETWEEN_SPIKES = 20  # number of seconds between spikes
NUM_SPIKES = 3  # number of spikes to send over the duration of the test


def load_testing_account_id(i):
    return f'load_testing_{i}'


def get_status():
    r = requests.get(f'http://{LOCAL_ADDR}:{RPC_PORT}/status', timeout=10)
    r.raise_for_status()
    return json.loads(r.content)


def get_latest_block_hash():
    last_block_hash = get_status()['sync_info']['latest_block_hash']
    return base58.b58decode(last_block_hash.encode('utf8'))


def json_rpc(method, params):
    j = {'method': method, 'params': params, 'id': 'dontcare', 'jsonrpc': '2.0'}
    r = requests.post(f'http://{LOCAL_ADDR}:{RPC_PORT}', json=j, timeout=10)
    return json.loads(r.content)


def get_nonce_for_pk(account_id, pk, finality='optimistic'):
    access_keys = json_rpc(
        'query', {
            "request_type": "view_access_key_list",
            "account_id": account_id,
            "finality": finality
        })
    for k in access_keys['result']['keys']:
        if k['public_key'] == pk:
            return k['access_key']['nonce']


def send_transfer(account, i, i0):
    next_id = i + 1
    if next_id >= i0 + NUM_ACCOUNTS:
        next_id = i0
    dest_account_id = load_testing_account_id(next_id)
    account.send_transfer_tx(dest_account_id)


def send_baseline(accounts, start_time):
    i0 = accounts[0][1]
    wait_time = NUM_NODES / BASE_TPS
    while time.time() - start_time < TIME_BETWEEN_SPIKES:
        for (account, i) in accounts:
            send_transfer(account, i, i0)
            time.sleep(wait_time)


def send_spike(accounts, start_time):
    i0 = accounts[0][1]
    wait_time = (NUM_NODES * NUM_ACCOUNTS) / SPIKE_TPS
    while time.time() - start_time < SPIKE_DURATION:
        pmap(lambda x: send_transfer(x[0], x[1], i0), accounts)
        time.sleep(wait_time)


if __name__ == '__main__':
    node_index = int(sys.argv[1])
    pk = sys.argv[2]
    sk = sys.argv[3]

    test_account_keys = [
        (Key(load_testing_account_id(i), pk, sk), i)
        for i in range(node_index * NUM_ACCOUNTS, (node_index + 1) *
                       NUM_ACCOUNTS)
    ]

    base_block_hash = get_latest_block_hash()
    rpc_info = (LOCAL_ADDR, RPC_PORT)

    test_accounts = [(Account(key, get_nonce_for_pk(key.account_id, key.pk),
                              base_block_hash, rpc_info), i)
                     for (key, i) in test_account_keys]

    for _ in range(NUM_SPIKES):
        send_baseline(test_accounts, time.time())
        send_spike(test_accounts, time.time())
    send_baseline(test_accounts, time.time())

    # record events for accurate input tps measurements
    all_tx_events = []
    for (account, _) in test_accounts:
        all_tx_events += account.tx_timestamps
    all_tx_events.sort()
    with open('/home/ubuntu/tx_events', 'w') as output:
        for t in all_tx_events:
            output.write(f'{t}\n')
