import base58
from cluster import GCloudNode, Key
from metrics import Metrics
from transaction import sign_payment_tx_and_get_hash, sign_staking_tx_and_get_hash
import json
import os
import statistics
import time
from rc import run, pmap

NUM_SECONDS_PER_YEAR = 3600 * 24 * 365
NUM_NODES = 54
NODE_BASE_NAME = 'mocknet-node'
NODE_USERNAME = 'ubuntu'
NODE_SSH_KEY_PATH = '~/.ssh/near_ops'
KEY_TARGET_ENV_VAR = 'NEAR_PYTEST_KEY_TARGET'
DEFAULT_KEY_TARGET = '/tmp/mocknet'

TMUX_STOP_SCRIPT = '''
while tmux has-session -t near; do
tmux kill-session -t near || true
done
'''

TMUX_START_SCRIPT = '''
sudo rm -rf /tmp/near.log
tmux new -s near -d bash
tmux send-keys -t near 'RUST_BACKTRACE=full /home/ubuntu/near run 2>&1 | tee /home/ubuntu/near.log' C-m
'''

PYTHON_DIR = '/home/ubuntu/.near/pytest/'

PYTHON_SETUP_SCRIPT = f'''
rm -rf {PYTHON_DIR}
mkdir -p {PYTHON_DIR}
if [ -z $(which python3.7) ]
then
    sudo apt install python3.7-dev python3.7-venv -y
fi
python3.7 -m pip install pip --upgrade
python3.7 -m pip install virtualenv --upgrade
cd {PYTHON_DIR}
python3 -m virtualenv venv -p $(which python3.7)
'''

INSTALL_PYTHON_REQUIREMENTS = f'''
cd {PYTHON_DIR}
./venv/bin/pip install -r requirements.txt
'''


# set prefix = 'sharded-' to access sharded mocknet nodes
def get_node(i, prefix=''):
    n = GCloudNode(f'{prefix}{NODE_BASE_NAME}{i}')
    n.machine.username = NODE_USERNAME
    n.machine.ssh_key_path = NODE_SSH_KEY_PATH
    return n


def get_nodes(prefix=''):
    return pmap(lambda i: get_node(i, prefix=prefix), range(NUM_NODES))


def create_target_dir(machine):
    base_target_dir = os.environ.get(KEY_TARGET_ENV_VAR, DEFAULT_KEY_TARGET)
    target_dir = f'{base_target_dir}/{machine.name}'
    run(f'mkdir -p {target_dir}')
    return target_dir


def get_validator_account(node):
    m = node.machine
    target_dir = create_target_dir(m)
    m.download(f'/home/ubuntu/.near/validator_key.json', target_dir)
    return Key.from_json_file(f'{target_dir}/validator_key.json')


def list_validators(node):
    validators = node.get_validators()['result']
    validator_accounts = set(
        map(lambda v: v['account_id'], validators['current_validators']))
    return validator_accounts


def setup_python_environment(node, additional_files):
    m = node.machine
    print(f'INFO: Setting up python environment on {m.name}')
    m.run('bash', input=PYTHON_SETUP_SCRIPT)
    m.upload('lib', PYTHON_DIR, switch_user='ubuntu')
    m.upload('requirements.txt', PYTHON_DIR, switch_user='ubuntu')
    for f in additional_files:
        m.upload(f, PYTHON_DIR, switch_user='ubuntu')
    m.run('bash', input=INSTALL_PYTHON_REQUIREMENTS)
    print(f'INFO: {m.name} python setup complete')


def setup_python_environments(nodes, additional_files):
    pmap(lambda n: setup_python_environment(n, additional_files), nodes)


def start_load_test_helper_script(script_name, index, pk, sk):
    return f'''
        cd {PYTHON_DIR}
        nohup ./venv/bin/python {script_name} {index} "{pk}" "{sk}" > load_test.out 2> load_test.err < /dev/null &
    '''


def start_load_test_helper(node, script_name, pk, sk):
    m = node.machine
    print(f'INFO: Starting {script_name} on {m.name}')
    index = int(m.name.split('node')[-1])
    m.run('bash', input=start_load_test_helper_script(script_name, index, pk, sk))


def start_load_test_helpers(nodes, script_name):
    account = get_validator_account(get_node(0))
    pmap(lambda node: start_load_test_helper(node, script_name, account.pk, account.sk),
         nodes)


def get_log(node):
    m = node.machine
    target_file = f'./logs/{m.name}.log'
    m.download(f'/home/ubuntu/near.log', target_file)

def get_logs(nodes):
    pmap(get_log, nodes)

def get_epoch_length_in_blocks(node):
    m = node.machine
    target_dir = create_target_dir(m)
    m.download(f'/home/ubuntu/.near/genesis.json', target_dir)
    with open(f'{target_dir}/genesis.json') as f:
        config = json.load(f)
        epoch_length_in_blocks = config['epoch_length']
        return epoch_length_in_blocks


def get_metrics(node):
    (addr, port) = node.rpc_addr()
    metrics_url = f'http://{addr}:{port}/metrics'
    return Metrics.from_url(metrics_url)


# Sends the transaction to the network via `node` and checks for success.
# Some retrying is done when the node returns a Timeout error.
def send_transaction(node, tx, tx_hash, account_id, timeout=120):
    response = node.send_tx_and_wait(tx, timeout)
    loop_start = time.time()
    missing_count = 0
    while 'error' in response.keys():
        error_data = response['error']['data']
        if error_data == 'Timeout':
            print(
                f'WARN: transaction {tx_hash} returned Timout, checking status again.'
            )
            time.sleep(5)
            response = node.get_tx(tx_hash, account_id)
        elif "doesn't exist" in error_data:
            missing_count += 1
            print(
                f'WARN: transaction {tx_hash} falied to be recieved by the node, checking again.'
            )
            if missing_count < 20:
                time.sleep(5)
                response = node.get_tx(tx_hash, account_id)
            else:
                print(f'WARN: re-sending transaction {tx_hash}.')
                response = node.send_tx_and_wait(tx, timeout)
                missing_count = 0
        else:
            raise RuntimeError(
                f'Error in processing transaction {tx_hash}: {response}')
        if time.time() - loop_start > timeout:
            raise TimeoutError(
                f'Transaction {tx_hash} did not complete successfully within the timeout'
            )

    if 'SuccessValue' not in response['result']['status']:
        raise RuntimeError(
            f'ERROR: Failed transaction {tx_hash}. Response: {response}')


def transfer_between_nodes(nodes):
    print('INFO: Testing transfer between mocknet validators')
    node = nodes[0]
    alice = get_validator_account(nodes[1])
    bob = get_validator_account(nodes[0])
    transfer_amount = 100
    get_balance = lambda account: int(
        node.get_account(account.account_id)['result']['amount'])

    alice_initial_balance = get_balance(alice)
    alice_nonce = node.get_nonce_for_pk(alice.account_id, alice.pk)
    bob_initial_balance = get_balance(bob)
    print(f'INFO: Alice initial balance: {alice_initial_balance}')
    print(f'INFO: Bob initial balance: {bob_initial_balance}')

    last_block_hash = node.get_status()['sync_info']['latest_block_hash']
    last_block_hash_decoded = base58.b58decode(last_block_hash.encode('utf8'))

    tx, tx_hash = sign_payment_tx_and_get_hash(alice, bob.account_id,
                                               transfer_amount, alice_nonce + 1,
                                               last_block_hash_decoded)
    send_transaction(node, tx, tx_hash, alice.account_id)

    alice_final_balance = get_balance(alice)
    bob_final_balance = get_balance(bob)
    print(f'INFO: Alice final balance: {alice_final_balance}')
    print(f'INFO: Bob final balance: {bob_final_balance}')

    # Check mod 1000 to ignore the cost of the transaction itself
    assert (alice_initial_balance -
            alice_final_balance) % 1000 == transfer_amount
    assert bob_final_balance - bob_initial_balance == transfer_amount


def stake_node(node):
    account = get_validator_account(node)
    print(f'INFO: Staking {account.account_id}.')
    nonce = node.get_nonce_for_pk(account.account_id, account.pk)

    validators = node.get_validators()['result']
    if account.account_id in validators['current_validators']:
        return
    stake_amount = max(
        map(lambda v: int(v['stake']), validators['current_validators']))

    latest_block_hash = node.get_status()['sync_info']['latest_block_hash']
    last_block_hash_decoded = base58.b58decode(latest_block_hash.encode('utf8'))

    staking_tx, staking_tx_hash = sign_staking_tx_and_get_hash(
        account, account, stake_amount, nonce + 1, last_block_hash_decoded)
    send_transaction(node, staking_tx, staking_tx_hash, account.account_id)


def accounts_from_nodes(nodes):
    return pmap(get_validator_account, nodes)


def kill_proccess_script(pid):
    return f'''
        sudo kill {pid}
        while kill -0 {pid}; do
            sleep 1
        done
    '''


def get_near_pid(machine):
    p = machine.run(
        "ps aux | grep 'near.* run' | grep -v grep | awk '{print $2}'")
    return p.stdout.strip()


def stop_node(node):
    m = node.machine
    print(f'INFO: Stopping node {m.name}')
    pid = get_near_pid(m)
    if pid != '':
        m.run('bash', input=kill_proccess_script(pid))
        m.run('sudo -u ubuntu -i', input=TMUX_STOP_SCRIPT)


def start_node(node):
    m = node.machine
    print(f'INFO: Starting node {m.name}')
    pid = get_near_pid(m)
    if pid == '':
        start_process = m.run('sudo -u ubuntu -i', input=TMUX_START_SCRIPT)
        assert start_process.returncode == 0, m.name + '\n' + start_process.stderr
