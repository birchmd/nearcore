import asyncio
import random
import sys
import time

from load_testing_helper import get_latest_block_hash, get_test_accounts_from_args, send_transfer

sys.path.append('lib')
from cluster import Key
from interceptor import Interceptor

TEST_DURATION = 180 # seconds
DROP_FRACTION = 0.00 # drop 1% of all messages
TARGET_TPS = 100
NEAR_EXECUTABLE = '/home/ubuntu/near'
NEAR_LOG = '/home/ubuntu/near.log'

class MessageDropper(Interceptor):
    async def message_handler(self, message):
        r = random.random()
        if r > DROP_FRACTION:
            return True
        else:
            print(f'INFO: Dropped {message.enum}')
            return False


if __name__ == '__main__':
    x = MessageDropper()
    x.start_node(NEAR_EXECUTABLE, NEAR_LOG)
    x.start_server()

    # Give some time for the node to boot up
    time.sleep(30)

    test_accounts = get_test_accounts_from_args()

    base_block_hash = None
    while base_block_hash is None:
        try:
            base_block_hash = get_latest_block_hash()
        except:
            # It could take some time for the status endpoint to
            # be ready, so we wait a bit and retry.
            time.sleep(0.2)
            continue

    account_key = Key.from_json_file('/home/ubuntu/.near/validator_key.json')
    start_time = time.time()
    i = 0
    # Send 2 transfer transactions per second;
    # this happens on every node, so total tps ~100.
    while time.time() - start_time < TEST_DURATION:
        try:
            i = (i + 1) % len(test_accounts)
            send_transfer(test_accounts[i][0], i + 1, base_block_hash)
        except:
            print("WARN: Error while sending transfer")
        finally:
            time.sleep(0.5)

    x.close()
