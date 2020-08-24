# The purpose of this test is to measure how the number of validators impacts
# performance. For various numbers of validators, we put the network under a
# load of 500 transfer transactions per second and measure how many it is able
# to process.

from collections import OrderedDict
import json, statistics, sys, time
from rc import pmap

from performance_testing_helper import TEST_TIMEOUT

sys.path.append('lib')
import mocknet
from metrics import Metrics


def update_genesis(nodes, gas_limit):
    target_file = '/tmp/near/genesis.json'
    dest_file = '/home/ubuntu/.near/genesis.json'
    nodes[0].machine.download(dest_file, target_file)
    genesis = json.load(open(target_file), object_pairs_hook=OrderedDict)
    genesis['gas_limit'] = gas_limit
    json.dump(genesis, open(target_file, 'w'), indent=2)
    pmap(lambda node: node.machine.upload(target_file, dest_file, switch_user='ubuntu'), nodes)


def measure_tps(nodes):
    mocknet.setup_python_environments(
        nodes, 'tests/mocknet/performance_testing_helper.py')
    mocknet.start_load_test_helpers(nodes, 'performance_testing_helper.py')
    metrics = []
    start_time = time.time()
    while time.time() - start_time < TEST_TIMEOUT:
        metrics.append(mocknet.get_metrics(nodes[-1]))
        time.sleep(2)
    
    initial_metrics = metrics[0]
    final_metrics = metrics[-1]
    delta = Metrics.diff(final_metrics, initial_metrics)
    bps = statistics.mean(map(lambda m: m.blocks_per_second, metrics))
    tps = delta.total_transactions / delta.timestamp

    return (bps, tps)


if __name__ == '__main__':
    nodes = mocknet.get_nodes(prefix='sharded-')

    output_file = 'performance_vs_gas_limit.csv'
    zeros = '0' * 14
    gas_limits = [int(str(i) + zeros) for i in range(1, 11)]

    for gas_limit in gas_limits:
        pmap(mocknet.reset_data, nodes)
        update_genesis(nodes, gas_limit)
        pmap(mocknet.start_node, nodes)
        time.sleep(60)

        print(f'INFO: gas_limit = {gas_limit}')
        (bps, tps) = measure_tps(nodes)
        print(f'INFO: ({gas_limit},{bps},{tps})')
        with open(output_file, 'a') as f:
            f.write(f'{gas_limit},{bps},{tps}\n')
