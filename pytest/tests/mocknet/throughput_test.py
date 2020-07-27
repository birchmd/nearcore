import sys, time
from rc import pmap

from throughput_testing_helper import SPIKE_DURATION, TIME_BETWEEN_SPIKES, NUM_SPIKES

sys.path.append('lib')
import mocknet

num_shrds = sys.argv[1]
run_index = sys.argv[2]

total_test_time = 12 * (SPIKE_DURATION + TIME_BETWEEN_SPIKES)
nodes = mocknet.get_nodes(prefix='sharded-')

pmap(mocknet.start_node, nodes)
# remove old ouput
pmap(
    lambda node: node.machine.run('bash', input='rm -rf /home/ubuntu/tx_events'
                                 ), nodes)
print('INFO: Waiting for nodes to come online.')
time.sleep(60)


def setup_python_env(node):
    m = node.machine
    print(f'INFO: Setting up python environment on {m.name}')
    m.run('bash', input=mocknet.PYTHON_SETUP_SCRIPT)
    m.upload('lib', mocknet.PYTHON_DIR, switch_user='ubuntu')
    m.upload('requirements.txt', mocknet.PYTHON_DIR, switch_user='ubuntu')
    m.upload('tests/mocknet/throughput_testing_helper.py',
             mocknet.PYTHON_DIR,
             switch_user='ubuntu')
    m.run('bash', input=mocknet.INSTALL_PYTHON_REQUIREMENTS)
    print(f'INFO: {m.name} python setup complete')


def start_throughput_test_helper_script(index, pk, sk):
    return f'''
        cd {mocknet.PYTHON_DIR}
        nohup ./venv/bin/python throughput_testing_helper.py {index} "{pk}" "{sk}" > throughput_test.out 2> throughput_test.err < /dev/null &
    '''


def start_throughput_test_helper(node, pk, sk):
    m = node.machine
    print(f'INFO: Starting throughput_testing_helper on {m.name}')
    index = int(m.name.split('node')[-1])
    m.run('bash', input=start_throughput_test_helper_script(index, pk, sk))


def get_output(node):
    try:
        m = node.machine
        target_file = f'./logs/{m.name}_txs'
        m.download('/home/ubuntu/tx_events', target_file)
        with open(target_file) as f:
            return list(map(lambda line: float(line.strip()), f.readlines()))
    except:
        return []


def accumulate_events(tx_events, bins):
    counts = [0 for _ in bins]
    n = len(bins) - 1
    i = 0
    total = 0
    for t in tx_events:
        if t > bins[i]:
            counts[i] = total
            i += 1
            if i > n:
                i = n
        total += 1
    # fill in remainder with total (no new events after previous loop)
    for j in range(i, n + 1):
        counts[j] = total
    return counts


def compute_rates(cumulative, bins):
    return [(cumulative[i] - cumulative[i - 1]) / (bins[i] - bins[i - 1])
            for i in range(1, len(bins))]


pmap(setup_python_env, nodes)
account_keys = mocknet.get_validator_account(nodes[0])
pk = account_keys.pk
sk = account_keys.sk
pmap(lambda node: start_throughput_test_helper(node, pk, sk), nodes)

throughput_measurements = []
rpc_node = nodes[-1]
start_time = time.time()

print('INFO: Waiting for test to complete')
while time.time() - start_time < total_test_time:
    m = mocknet.get_metrics(rpc_node)
    throughput_measurements.append((m.timestamp, m.total_transactions))
    time.sleep(2)

print('INFO: Gathering results')
input_tx_times = sorted(sum(pmap(get_output, nodes), []))

bins = [m[0] for m in throughput_measurements]
cumulative_input_txs = accumulate_events(input_tx_times, bins)
cumulative_output_txs = [m[1] for m in throughput_measurements]

input_tps = compute_rates(cumulative_input_txs, bins)
output_tps = compute_rates(cumulative_output_txs, bins)
time_steps = [bins[i] - bins[0] for i in range(1, len(bins))]

print('INFO: Writing output')
with open(f'throughput_results_{num_shrds}shard_{run_index}.csv',
          'w') as output:
    for (t, (i_tps, o_tps)) in zip(time_steps, zip(input_tps, output_tps)):
        output.write(f'{t},{i_tps},{o_tps}\n')
