# Mocknet Usage Instructions

## Pre-requisites

### Google Cloud SDK

The `gcloud` CLI must be installed and configured on the machine that is operating mocknet.
This is required so that the script can look up the instance IP addresses from their names.
You can check that `gcloud` is installed by running

```bash
gcloud --version
```

If you see output like

```
Google Cloud SDK 321.0.0
alpha 2020.12.11
beta 2020.12.11
bq 2.0.64
core 2020.12.11
gsutil 4.57
```

then you are all set. If not then follow the Google Cloud SDK installation instructions:
https://cloud.google.com/sdk/docs/install

Once `gcloud` is installed, check you are authenticated for the `near-core` project:

```bash
gcloud config list
```

If you see output like 

```
[core]
account = michael@near.org
disable_usage_reporting = True
project = near-core
```

then you are all set. If not then run

```bash
gcloud init
```

and follow the instructions to log in.

### SSH access key

The mocknet scripts assume that `~/.ssh/near_ops` exists and is the SSH key used by near-ops.
If you do not have this key it is available to download from our AWS (or you can ask someone for it).
Ensure that you have the key in the right place:

```
$ ls -lh ~/.ssh/near_ops

-r-------- 1 birchmd birchmd 1.8K Jun 18 13:24 /home/birchmd/.ssh/near_ops
```

### `nearcore` repository

The scripts for using mocknet live in `nearcore/pytest`. Ensure you have `nearcore` cloned from git.
All future commands will assume you are running from `nearcore/pytest`.

### Python virtual environment

To ensure there is no incompatibility between globally installed python packages and the ones required by mocknet,
create a python virtual environment and install the depependencies there.

```bash
python3 -m pip install pip --upgrade
python3 -m pip install virtualenv --upgrade
python3 -m virtualenv venv -p $(which python3)
./venv/bin/pip install -r requirements.txt
```

You should now be able to start python and import the mocknet scripts:

```
$ ./venv/bin/python

Python 3.7.5 (default, Nov  7 2019, 10:50:52)
[GCC 8.3.0] on linux
Type "help", "copyright", "credits" or "license" for more information.
>>> import sys
>>> sys.path.append('lib')
>>> import mocknet
>>>
```

## Basic Usage

As in the pre-requisites section, begin with your terminal in the `nearcore/pytest` directory, start python from the virtual
environment and import the mocknet package.

```
$ ./venv/bin/python

Python 3.7.5 (default, Nov  7 2019, 10:50:52)
[GCC 8.3.0] on linux
Type "help", "copyright", "credits" or "license" for more information.
>>> import sys
>>> sys.path.append('lib')
>>> import mocknet
>>>
```

### Accessing the node objects

There are two sets of 54 nodes which make up "mocknet". The nightly Nayduck tests use only the first 54 nodes (named `mocknet-nodeX`, where `X` ranges from 0 to 53).
The latter 54 were originally provisioned to separately test the network with sharding (these are named `sharded-mocknet-nodeX`, where `X` ranges from 0 to 53),
however, we have been testing a larger network now which uses all 108 nodes as part of the same network.

To access the original nodes:

```
>>> nodes = mocknet.get_nodes()
```

To access the "sharded" nodes:

```
>>> nodes = mocknet.get_nodes(prefix='sharded-')
```

To access all nodes together:

```
nodes = mocknet.get_nodes() + mocknet.get_nodes(prefix='sharded-')
```

Most mocknet functions take a `nodes` argument, which is the set of nodes to operate on. The commands given above are how you should create `nodes` to pass to this functions.

### Starting, stopping and resetting nodes

To start all the nodes run:

```python
from rc import pmap
pmap(mocknet.start_node, nodes)
```

To stop all nodes run:

```python
pmap(mocknet.stop_node, nodes)
```

To stop all nodes _and clear their data directories_, run:

```python
pmap(mocknet.reset_data, nodes)
```

The last command is useful when you want to restart the network from a fresh genesis. Note that this command does not change `config.json` or `genesis.json`, nor does it delete the logs.
It only clears the data directory for each node.

### Obtaining the logs from the nodes

To download the logs from all nodes run:

```python
mocknet.get_logs(nodes)
```

Note that this function assumes the directory `nearcore/pytest/logs/` exists. I generally reset all the nodes before downloading their logs.
I don't know how things would work out if the near binary were writing to the file while the mocknet script was trying to download it.

### Deploying a specific binary to the nodes

When the nodes are not running you can upload a new binary to the machines:

```
pmap(lambda node: node.machine.upload('<LOCAL_PATH_TO_BINARY>', '/home/ubuntu/near', switch_user='ubuntu'), nodes)
```

Note that you can have some machines running different binaries than others by specifying a subset of the nodes, e.g. `nodes[:100]`.

### Updating config and genesis files

The genesis and config files can be updated in a similar way to the binary:

```python
pmap(lambda node: node.machine.upload(config_file, '/home/ubuntu/.near/config.json', switch_user='ubuntu'), nodes)
pmap(lambda node: node.machine.upload(genesis_file, '/home/ubuntu/.near/genesis.json', switch_user='ubuntu'), nodes)
```

where `config_file`, and `genesis_file` represent the local paths to the desired config and genesis json files, respectively.
Note that you can send different files to different nodes by specifying a sub-set of the nodes. This is important because
I have been running the tests where the validating nodes have `"tracked_shards": []`
(which is the first 50 nodes if only 54 are used in the cluster or first 100 nodes if 108 nodes are in the cluster), while the
RPC nodes track all the shards explicitly. Example config and genesis files for the 8-shard network can be found on my GitHub:

* https://github.com/birchmd/nearcore/blob/shard-scaling/pytest/config_8.json
* https://github.com/birchmd/nearcore/blob/shard-scaling/pytest/genesis_8.json

This files are configured to use all 108 nodes in the cluster. The config also has `tracked_shards` set, so you will need to clear
that array before uploading to validator nodes.

### Adding transaction load to the network

Transactions are submitted to the network from every node using python scripts local to each node.
To run transactions first ensure the local python environments are set up:

```python
mocknet.setup_python_environments(nodes, 'tests/mocknet/transfer_only_load_testing_helper.py')
```

Note the second argument is the script to upload to the nodes which will then be responsible for sending the transactions.
The script in that example is found on my GitHub: https://github.com/birchmd/nearcore/blob/shard-scaling/pytest/tests/mocknet/transfer_only_load_testing_helper.py
Then ensure the cluster is up and running (i.e. all nodes are up and block production has started).
Then start all the transaction helpers:

```python
mocknet.start_load_test_helpers(nodes, 'transfer_only_load_testing_helper.py')
```

Note that the transaction rate can be adjusted by changing the `TRANSFER_SLEEP_TIME` constant in `transfer_only_load_testing_helper.py`.
I have been using a value of `0.05` in recent tests.

### Watching the network to see if validators are lost

On my GitHub I have a useful function which watches the network and raises an exception when validators get kicked out:

https://github.com/birchmd/nearcore/blob/shard-scaling/pytest/tests/mocknet/bps_vs_shards.py#L31

## Warning about Nayduck

Since the Nayduck tests use some of the same machines as the ad-hoc tests we have been running, you need to make sure
that Nayduck mocknet tests do not start running while you are running a test (otherwise both will be messed up). To
ensure this I have a special branch which can be used to stop the Nayduck tests from running for 6 hours. To stop them
for longer you can submit a run multiple times. From `nearcore` (not `nearcore/pytest` like everything else in this doc!):

```
git checkout hold-mocknet
python3 nightly/nayduck.py --test_file nightly/mocknet.txt
python3 nightly/nayduck.py --test_file nightly/mocknet.txt
```

This will prevent Nayduck mocknet tests from running for 12 hours for example.
