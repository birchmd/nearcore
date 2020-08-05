import sys, time
from rc import pmap

from load_testing_helper import (NUM_ACCOUNTS, get_test_accounts_from_args,
                                 get_latest_block_hash, throttle_txns,
                                 send_transfer)

sys.path.append('lib')
from mocknet import NUM_NODES

TEST_TIMEOUT = 180
MAX_TPS = 500  # maximum transactions per second sent (across the whole network)
MAX_TPS_PER_NODE = MAX_TPS / NUM_NODES


def send_transfers(i0):
    pmap(
        lambda account_and_index: send_transfer(account_and_index[
            0], account_and_index[1], i0), test_accounts)


if __name__ == '__main__':
    test_accounts = get_test_accounts_from_args()

    i0 = test_accounts[0][1]

    start_time = time.time()

    total_tx_sent = 0
    elapsed_time = 0
    while time.time() - start_time < TEST_TIMEOUT:
        (total_tx_sent,
         elapsed_time) = throttle_txns(send_transfers, total_tx_sent,
                                       elapsed_time, MAX_TPS_PER_NODE, i0)
