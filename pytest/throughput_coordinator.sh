MAX_SHARDS=8
MAX_RUNS=10

OPS_DIR="/datadrive/birchmd/upstream/near-ops"
PYTEST_DIR="/datadrive/birchmd/nearcore/pytest"

shards_range=$(python -c "print(' '.join(map(lambda x: str(x + 1), range(0, $MAX_SHARDS))))")
runs_range=$(python -c "print(' '.join(map(lambda x: str(x + 1), range(0, $MAX_RUNS))))")

for num_shards in $shards_range
do
    for run_index in $runs_range
    do
        cd $OPS_DIR
        python mocknet.py sharded-reset 4bb3894701ce0c629b21f0578f83b476d80aa4ab --num-shards=$num_shards
        cd $PYTEST_DIR
        ./venv/bin/python tests/mocknet/throughput_test.py $num_shards $run_index
    done
done
