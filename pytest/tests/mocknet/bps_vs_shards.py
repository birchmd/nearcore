import json, os, shutil, statistics, sys, time
from rc import pmap
from collections import OrderedDict

sys.path.append('lib')
import mocknet
import data
import logs_parsing

def measure_bps(nodes, num_shards, output_file):
    pmap(mocknet.start_node, nodes)
    time.sleep(60)
    initial_metrics = mocknet.get_metrics(nodes[0])
    time.sleep(120)
    final_metrics = mocknet.get_metrics(nodes[0])
    measurement = mocknet.chain_measure_bps_and_tps(archival_node=nodes[-1], start_time=None, end_time=None, duration=120)
    measurement['num_shards'] = num_shards
    kb_per_second = (final_metrics.received_bytes - initial_metrics.received_bytes) / (1000.0 * 120.0)
    measurement['kb_per_second'] = kb_per_second
    pmap(mocknet.reset_data, nodes)
    (times_by_chunk, median_recon, total_recon) = measure_chunk_times(nodes)
    times = sorted(times_by_chunk.values())
    measurement['chunk_time'] = statistics.median(times)
    measurement['median_recon'] = median_recon
    measurement['total_recon'] = total_recon
    data.dict_to_csv([measurement], output_file, mode='a')
    print(measurement)


def determine_type(line):
    if 'sending chunk' in line:
        return 'S'
    elif 'received chunk' in line:
        return 'R'
    elif 'ShardsManager::process_partial_encoded_chunk/reconstruct' in line:
        return 'D'
    else:
        return None


def transform(typ, tokens):
    if typ == 'S':
        i = data.find_index(tokens, lambda t: t == 'sending')
        source = tokens[i - 1].split('"')[1]
        chunk_hash = tokens[i + 2]
        dest = tokens[i + 4]
        return {'source' : source, 'chunk' : chunk_hash, 'dest' : dest}
    elif typ == 'R':
        i = data.find_index(tokens, lambda t: t == 'received')
        dest = tokens[i - 1].split('"')[1]
        chunk_hash = tokens[i + 2]
        return {'chunk' : chunk_hash, 'dest' : dest}
    elif typ == 'D':
        return int(tokens[-1])
    else:
        raise Exception(f'Unknown type {typ}')

def measure_chunk_times(nodes):
    mocknet.get_logs(nodes)
    result = data.flatten(pmap(lambda node: logs_parsing.parse_log_file_stateless(f'./logs/{node.machine.name}.log', determine_type, transform), nodes))
    result.sort(key=lambda r: r['timestamp'])
    sends = [(r['timestamp'], r['data']) for r in result if r['type'] == 'S']
    receives = [(r['timestamp'], r['data']) for r in result if r['type'] == 'R']
    receives_by_chunk = data.group_by(receives, lambda x: x[1]['chunk'])
    sends_by_chunk = data.group_by(sends, lambda x: x[1]['chunk'])
    times_by_chunk = {}
    for chunk_hash in sends_by_chunk:
        sends_for_chunk = sends_by_chunk[chunk_hash]
        if chunk_hash in receives_by_chunk:
            receives_for_chunk = receives_by_chunk[chunk_hash]
            receives_by_dest = data.group_by(receives_for_chunk, lambda x: x[1]['dest'])
            times_for_chunk = []
            for (send_time, send_data) in sends_for_chunk:
                dest = send_data['dest']
                if dest in receives_by_dest:
                    receive_time = min(receives_by_dest[dest], key=lambda x: x[0])[0]
                    times_for_chunk.append(receive_time - send_time)
            times_by_chunk[chunk_hash] = statistics.mean(times_for_chunk)
    durations = [r['data'] for r in result if r['type'] == 'D']
    return (times_by_chunk, statistics.median(durations), sum(durations))

def update_genesis_timestamp(genesis_file, new_timestamp):
    lines = []
    with open(genesis_file) as input:
        for line in input.readlines():
            if 'genesis_time' in line:
                lines.append(f'  "genesis_time": "{new_timestamp}",\n')
            else:
                lines.append(line)
    with open(genesis_file, 'w') as f:
        for line in lines:
            f.write(line)

def update_num_steats(num_shards):
    genesis_file = f'genesis_{num_shards}.json'
    total_seats = 50
    with open(genesis_file) as f:
        genesis = json.load(f, object_pairs_hook=OrderedDict)
    genesis['num_block_producer_seats'] = total_seats
    seats_per_shard = total_seats // num_shards
    num_block_producer_seats_per_shard = [seats_per_shard] * num_shards
    remainder_seats = total_seats - sum(num_block_producer_seats_per_shard)
    i = 0
    while remainder_seats > 0:
        i = i % num_shards
        num_block_producer_seats_per_shard[i] += 1
        remainder_seats -= 1
        i += 1
    assert sum(num_block_producer_seats_per_shard) == total_seats
    genesis['num_block_producer_seats_per_shard'] = num_block_producer_seats_per_shard
    with open(genesis_file, 'w') as f:
        json.dump(genesis, f, indent=2)


def update_tracked_shards(config_file, tracked_shards):
    with open(config_file) as f:
        config = json.load(f, object_pairs_hook=OrderedDict)
    config['tracked_shards'] = tracked_shards
    with open(config_file, 'w') as f:
        json.dump(config, f, indent=2)

def set_node_tracked_shards(node, base_config_file, shards_mapping):
    validator = mocknet.get_validator_account(node)
    tracked_shards = shards_mapping[validator.pk]
    config_file = f'{node.machine.name}.config.json'
    shutil.copy(base_config_file, config_file)
    update_tracked_shards(config_file, tracked_shards)
    node.machine.upload(config_file, '/home/ubuntu/.near/config.json', switch_user='ubuntu')
    os.remove(config_file)

def set_all_nodes_tracked_shards(nodes, base_config_file, shards_mapping):
    pmap(lambda node: set_node_tracked_shards(node, base_config_file, shards_mapping), nodes)

def create_shards_mapping(archival_node):
    shards_mapping = {}
    validators = archival_node.get_validators()['result']
    for v in validators['current_validators']:
        shards_mapping[v['public_key']] = v['shards']
    return shards_mapping

if __name__ == '__main__':
    nodes = mocknet.get_nodes(prefix='sharded-')
    output_file = 'shards_vs_bps.csv'
    num_shards_to_test = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 20, 30 ,40 ,50] # , 60, 70, 80, 90, 100]
    for num_shards in num_shards_to_test:
        config_file = f'config_{num_shards}.json'
        genesis_file = f'genesis_{num_shards}.json'
        pmap(lambda node: node.machine.upload(config_file, '/home/ubuntu/.near/config.json', switch_user='ubuntu'), nodes)
        pmap(lambda node: node.machine.upload(genesis_file, '/home/ubuntu/.near/genesis.json', switch_user='ubuntu'), nodes)
        measure_bps(nodes, num_shards, output_file)
