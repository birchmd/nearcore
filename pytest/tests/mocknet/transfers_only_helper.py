import sys, time
from rc import pmap, run

from load_testing_helper import (get_test_accounts_from_args, throttle_txns,
                                 send_transfer, write_tx_events)

sys.path.append('lib')
from mocknet import NUM_NODES, TX_OUT_FILE

TEST_TIMEOUT = 180
MAX_TPS = 10000
MAX_TPS_PER_NODE = MAX_TPS / NUM_NODES


def send_transfers(i0):
    pmap(
        lambda account_and_index: send_transfer(account_and_index[
            0], account_and_index[1], i0), test_accounts)


if __name__ == '__main__':
    test_accounts = get_test_accounts_from_args()
    run(f'rm -rf {TX_OUT_FILE}')

    i0 = test_accounts[0][1]

    start_time = time.time()

    total_tx_sent = 0
    elapsed_time = 0
    while time.time() - start_time < TEST_TIMEOUT:
        (total_tx_sent,
         elapsed_time) = throttle_txns(send_transfers, total_tx_sent,
                                       elapsed_time, MAX_TPS_PER_NODE, i0)

    write_tx_events(test_accounts)
