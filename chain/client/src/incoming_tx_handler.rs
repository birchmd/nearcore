use crate::{Client, ClientActor};
use actix::{
    sync::{SyncArbiter, SyncContext},
    Actor, Addr, Handler, Message,
};
use log::error;
use near_chain::RuntimeAdapter;
use near_network::{NetworkAdapter, NetworkClientResponses};
use near_primitives::block::Tip;
use near_primitives::transaction::SignedTransaction;
use near_primitives::types::{AccountId, BlockHeightDelta, ShardId, StateRoot};
use std::sync::Arc;

pub struct IncomingTx {
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

impl Message for IncomingTx {
    type Result = NetworkClientResponses;
}

pub struct TxForMemPool(pub SignedTransaction, pub ShardId, pub Option<AccountId>, pub bool);

impl Message for TxForMemPool {
    type Result = ();
}

pub struct IncomingTxHandler {
    network_adapter: Arc<dyn NetworkAdapter>,
    runtime_adapter: Arc<dyn RuntimeAdapter>,
    client_actor: Addr<ClientActor>,
}

impl IncomingTxHandler {
    pub fn new(
        runtime_adapter: Arc<dyn RuntimeAdapter>,
        network_adapter: Arc<dyn NetworkAdapter>,
        client_actor: Addr<ClientActor>,
    ) -> Self {
        Self { network_adapter, runtime_adapter, client_actor }
    }

    pub fn start(
        n_threads: usize,
        runtime_adapter: Arc<dyn RuntimeAdapter>,
        network_adapter: Arc<dyn NetworkAdapter>,
        client_actor: Addr<ClientActor>,
    ) -> Addr<Self> {
        SyncArbiter::start(n_threads, move || {
            Self::new(runtime_adapter.clone(), network_adapter.clone(), client_actor.clone())
        })
    }
}

impl Actor for IncomingTxHandler {
    type Context = SyncContext<Self>;
}

impl Handler<IncomingTx> for IncomingTxHandler {
    type Result = NetworkClientResponses;

    fn handle(&mut self, msg: IncomingTx, _ctx: &mut Self::Context) -> Self::Result {
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
                    self.client_actor.do_send(TxForMemPool(
                        msg.tx,
                        msg.shard_id,
                        msg.validator_signer,
                        msg.is_forwarded,
                    ));
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
