use crate::Client;
use actix::{Actor, Addr, Arbiter, Context, Handler, Message};
use log::error;
use near_chain::{Chain, ChainGenesis, DoomslugThresholdMode, RuntimeAdapter};
use near_network::{types::UnvalidatedTx, NetworkAdapter, NetworkClientResponses};
use near_pool::SharedTxPool;
use near_primitives::block::Tip;
use near_primitives::transaction::SignedTransaction;
use near_primitives::types::{BlockHeightDelta, ShardId, StateRoot};
use std::collections::HashMap;
use std::sync::Arc;

pub struct IncomingTx {
    pub tx: SignedTransaction,
    pub is_forwarded: bool,
    pub check_only: bool,
    pub gas_price: u128,
    pub shard_id: ShardId,
    pub head: Tip,
    pub maybe_state_root: Option<StateRoot>,
    pub epoch_length: BlockHeightDelta,
    pub validator_signer: Option<String>,
    pub cares_about_shard: bool,
}

impl IncomingTx {
    pub fn new(
        tx: SignedTransaction,
        is_forwarded: bool,
        check_only: bool,
        gas_price: u128,
        shard_id: ShardId,
        head: Tip,
        maybe_state_root: Option<StateRoot>,
        epoch_length: BlockHeightDelta,
        validator_signer: Option<String>,
        cares_about_shard: bool,
    ) -> Self {
        Self {
            tx,
            is_forwarded,
            check_only,
            gas_price,
            shard_id,
            head,
            maybe_state_root,
            epoch_length,
            validator_signer,
            cares_about_shard,
        }
    }
}

pub struct IncomingTxHandler {
    network_adapter: Arc<dyn NetworkAdapter>,
    runtime_adapter: Arc<dyn RuntimeAdapter>,
    tx_pools: HashMap<ShardId, SharedTxPool>,
    chain: Chain,
    epoch_length: BlockHeightDelta,
    validator_signer: Option<String>,
}

impl IncomingTxHandler {
    pub fn new(
        runtime_adapter: Arc<dyn RuntimeAdapter>,
        network_adapter: Arc<dyn NetworkAdapter>,
        tx_pools: HashMap<ShardId, SharedTxPool>,
        chain_genesis: ChainGenesis,
        epoch_length: BlockHeightDelta,
        validator_signer: Option<String>,
    ) -> Self {
        let chain =
            Chain::new(runtime_adapter.clone(), &chain_genesis, DoomslugThresholdMode::TwoThirds)
                .unwrap();
        Self { network_adapter, runtime_adapter, tx_pools, chain, epoch_length, validator_signer }
    }

    pub fn start(
        runtime_adapter: Arc<dyn RuntimeAdapter>,
        network_adapter: Arc<dyn NetworkAdapter>,
        tx_pools: HashMap<ShardId, SharedTxPool>,
        chain_genesis: ChainGenesis,
        epoch_length: BlockHeightDelta,
        validator_signer: Option<String>,
    ) -> (Addr<Self>, Arbiter) {
        let arbiter = Arbiter::new();
        let addr = Self::start_in_arbiter(&arbiter, move |_ctx| {
            Self::new(
                runtime_adapter,
                network_adapter,
                tx_pools,
                chain_genesis,
                epoch_length,
                validator_signer,
            )
        });
        (addr, arbiter)
    }
}

impl Actor for IncomingTxHandler {
    type Context = Context<Self>;
}

impl Handler<UnvalidatedTx> for IncomingTxHandler {
    type Result = NetworkClientResponses;

    fn handle(&mut self, msg: UnvalidatedTx, _ctx: &mut Self::Context) -> Self::Result {
        let msg = match Client::prep_incoming_tx(
            msg.tx,
            msg.is_forwarded,
            msg.check_only,
            self.validator_signer.as_ref(),
            &mut self.chain,
            &self.runtime_adapter,
            self.epoch_length,
        ) {
            Ok(Ok(incoming_tx)) => incoming_tx,
            Ok(Err(response)) => {
                return response;
            }
            Err(err) => {
                error!(target: "client", "Error during transaction validation: {}", err);
                return NetworkClientResponses::NoResponse;
            }
        };
        let response = Client::validate_and_forward_tx(
            &msg.tx,
            msg.is_forwarded,
            msg.check_only,
            &self.runtime_adapter,
            &self.network_adapter,
            msg.gas_price,
            msg.shard_id,
            &msg.head,
            msg.maybe_state_root,
            msg.epoch_length,
            msg.validator_signer.as_ref(),
            msg.cares_about_shard,
        );

        match response {
            Err(err) => {
                error!(target: "client", "Error during transaction validation: {}", err);
                NetworkClientResponses::NoResponse
            }
            Ok(response) => {
                if !msg.check_only && msg.maybe_state_root.is_some() {
                    if let Some(lock) = self.tx_pools.get(&msg.shard_id) {
                        let mut pool = lock.write();
                        pool.insert_transaction(msg.tx);
                    }
                }
                response
            }
        }
    }
}

pub struct SetIncomingTxHandler(pub Addr<IncomingTxHandler>);
impl Message for SetIncomingTxHandler {
    type Result = ();
}
