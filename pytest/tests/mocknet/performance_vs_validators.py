# The purpose of this test is to measure how the number of validators impacts
# performance. For various numbers of validators, we put the network under a
# load of 500 transfer transactions per second and measure how many it is able
# to process.

from collections import OrderedDict
import json, sys, time
from rc import pmap

from performance_testing_helper import TEST_TIMEOUT

sys.path.append('lib')
import mocknet
from metrics import Metrics


def update_genesis(nodes, validators_to_remove):
    target_file = '/tmp/near/genesis.json'
    dest_file = '/home/ubuntu/.near/genesis.json'
    nodes[0].machine.download(dest_file, target_file)
    genesis = json.load(open(target_file), object_pairs_hook=OrderedDict)
    remaining_validators = [
        v for v in genesis['validators']
        if v['account_id'] not in validators_to_remove
    ]
    genesis['validators'] = remaining_validators
    new_records = []
    for r in genesis['records']:
        if 'Account' in r:
            if r['Account']['account_id'] in validators_to_remove:
                locked = int(r['Account']['account']['locked'])
                amount = int(r['Account']['account']['amount'])
                r['Account']['account']['locked'] = '0'
                r['Account']['account']['amount'] = str(locked + amount)
        new_records.append(r)
    genesis['records'] = new_records
    json.dump(genesis, open(target_file, 'w'), indent=2)
    for node in nodes:
        node.machine.upload(target_file, dest_file, switch_user='ubuntu')


def measure_tps(nodes):
    mocknet.setup_python_environments(
        nodes, 'tests/mocknet/performance_testing_helper.py')
    mocknet.start_load_test_helpers(nodes, 'performance_testing_helper.py')
    initial_metrics = mocknet.get_metrics(nodes[-1])
    time.sleep(TEST_TIMEOUT)
    final_metrics = mocknet.get_metrics(nodes[-1])

    delta = Metrics.diff(final_metrics, initial_metrics)
    bps = final_metrics.blocks_per_second
    tps = delta.total_transactions / delta.timestamp

    return (bps, tps)


if __name__ == '__main__':
    nodes = mocknet.get_nodes(prefix='sharded-')

    output_file = 'performance_vs_validators.csv'

    for num_validators_to_remove in range(0, 50):
        pmap(mocknet.reset_data, nodes)
        validators_to_remove = set(
            map(lambda n: f'node{n}', range(num_validators_to_remove)))
        update_genesis(nodes, validators_to_remove)
        pmap(mocknet.start_node, nodes)
        time.sleep(60)

        num_validators = len(mocknet.list_validators(nodes[0]))
        print(f'INFO: num_validators = {num_validators}')
        (bps, tps) = measure_tps(nodes)
        print(f'INFO: ({num_validators},{bps},{tps})')
        with open(output_file, 'a') as f:
            f.write(f'{num_validators},{bps},{tps}\n')
