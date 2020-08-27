import statistics, sys, time
from rc import pmap

from transfers_only_helper import TEST_TIMEOUT

sys.path.append('lib')
import data, logs_parsing, mocknet


def determine_type(log_line):
    if 'EVENT' in log_line:
        if 'Produced chunk' in log_line:
            return 'PCE'
        elif 'reconstruct chunk' in log_line:
            return 'RCE'
        else:
            return None
    elif 'duration' in log_line:
        return 'D'
    else:
        return None


def transform(line_type, tokens, node):
    if line_type == 'PCE' or line_type == 'RCE':
        # Produced chunk event or Reconstructed chunk event
        i = data.find_index(tokens, lambda t: 'height=' in t)
        height = int(tokens[i].split('=')[1])
        i = data.find_index(tokens, lambda t: 'chunk_hash=' in t)
        chunk_hash = tokens[i].split('=')[1]
        return {'node': node, 'height': height, 'hash': chunk_hash}
    elif line_type == 'D':
        # recorded duration
        duration = int(tokens[-1])
        i = data.find_index(tokens, lambda t: 'duration' in t)
        name = tokens[i - 1]
        return {'node': node, 'name': name, 'duration': duration}
    else:
        raise Exception('Unknown type')


def parse_node_log(node):
    node_name = node.machine.name
    log_file = f'logs/{node_name}.log'
    transform_fn = lambda line_type, tokens: transform(line_type, tokens,
                                                       node_name)
    return logs_parsing.parse_log_file_stateless(log_file, determine_type,
                                                 transform_fn)


def get_delays(chunk_events_by_hash):
    result = []
    for chunk_hash in chunk_events_by_hash:
        chunk_events = chunk_events_by_hash[chunk_hash]
        chunk_events_by_type = data.group_by(chunk_events, lambda e: e['type'])
        if 'PCE' not in chunk_events_by_type or 'RCE' not in chunk_events_by_type:
            # The chunk may have been produced before the test started, even if
            # it was reconstructed afterwards, similarly it may have been
            # received after the test ended. In these cases we skip it
            continue
        t_p = chunk_events_by_type['PCE'][0]['timestamp']
        chunk_reconstructions_by_node = data.group_by(
            chunk_events_by_type['RCE'], lambda e: e['data']['node'])
        first_reconstruction_per_node = [
            min(
                map(lambda e: e['timestamp'],
                    chunk_reconstructions_by_node[node]))
            for node in chunk_reconstructions_by_node
        ]
        deltas = sorted([t - t_p for t in first_reconstruction_per_node])
        result.append({
            'hash': chunk_hash,
            'time': t_p,
            'delay': statistics.median(deltas)
        })
    return result


def measure_times(nodes):
    pmap(mocknet.start_node, nodes)
    time.sleep(30)
    mocknet.setup_python_environments(nodes,
                                      'tests/mocknet/transfers_only_helper.py')
    mocknet.start_load_test_helpers(nodes, 'transfers_only_helper.py')
    time.sleep(TEST_TIMEOUT + 10)
    input_tx_events = mocknet.get_tx_events(nodes)
    # drop first and last 5% of events to avoid edges of test
    n = int(0.05 * len(input_tx_events))
    input_tx_events = input_tx_events[n:-n]
    test_start_time = input_tx_events[0]
    test_end_time = input_tx_events[-1]
    input_tps = data.compute_rate(input_tx_events)
    bps_tps_measurement = mocknet.chain_measure_bps_and_tps(
        nodes[-1], test_start_time, test_end_time)
    bps_tps_measurement['in_tps'] = input_tps
    pmap(mocknet.reset_data, nodes)
    mocknet.get_logs(nodes)
    parsed_records = sorted(data.flatten(pmap(parse_node_log, nodes)),
                            key=lambda r: r['timestamp'])

    durations = [
        r for r in parsed_records if r['timestamp'] >= test_start_time and
        r['timestamp'] <= test_end_time and r['type'] == 'D'
    ]
    chunk_events = [
        r for r in parsed_records if r['timestamp'] >= test_start_time and
        r['timestamp'] <= test_end_time and 'E' in r['type']
    ]

    durations_by_name = data.group_by(durations, lambda r: r['data']['name'])
    duration_results = []
    for name in durations_by_name:
        durations = [r['data']['duration'] for r in durations_by_name[name]]
        mean = statistics.mean(durations) / 1e6
        sd = statistics.stdev(durations) / 1e6
        total = sum(durations)
        duration_results.append({
            'name': name,
            'mean': mean,
            'sd': sd,
            'input': input_tps,
            'total': total
        })
    duration_results.sort(key=lambda r: r['mean'], reverse=True)
    for result in duration_results:
        name = result['name']
        mean = "{:.4f}".format(result['mean'])
        sd = "{:.4f}".format(result['sd'])
        print(f'{name} : {mean} +/- {sd} seconds')

    chunk_events_by_hash = data.group_by(chunk_events,
                                         lambda e: e['data']['hash'])
    delays = [x['delay'] for x in get_delays(chunk_events_by_hash)]
    mean_delay = "{:.4f}".format(statistics.mean(delays))
    sd_delay = "{:.4f}".format(statistics.stdev(delays))
    total_delay = sum(delays)
    print(f'Chunk network delay : {mean_delay} +/- {sd_delay} seconds')
    print(bps_tps_measurement)
    duration_results.append({
        'name': "chunk_network_delay",
        'mean': mean_delay,
        'sd': sd_delay,
        'input': input_tps,
        'total': total_delay
    })
    data.dict_to_csv(duration_results, 'timings.csv', 'a')
    data.dict_to_csv([bps_tps_measurement], 'bps_tps.csv', 'a')


def set_max_tps(max_tps):
    lines = []
    with open('tests/mocknet/transfers_only_helper.py') as f:
        for line in f.readlines():
            if 'MAX_TPS =' in line:
                lines.append(f'MAX_TPS = {max_tps}\n')
            else:
                lines.append(line)
    with open('tests/mocknet/transfers_only_helper.py', 'w') as f:
        for line in lines:
            f.write(line)


if __name__ == '__main__':
    nodes = mocknet.get_nodes(prefix='sharded-')
    max_tps_to_test = [500, 1000, 1500, 2000, 5000, 10000]
    for max_tps in max_tps_to_test:
        set_max_tps(max_tps)
        measure_times(nodes)
