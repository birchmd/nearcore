use crate::types::PeerMessage;
use actix::{sync::{SyncArbiter, SyncContext}, Actor, Addr, Message, MessageResult, Handler};
use borsh::{BorshDeserialize, BorshSerialize};

pub struct Ser(pub PeerMessage);
pub struct De(pub Vec<u8>);

impl Message for Ser {
    type Result = Result<Vec<u8>, std::io::Error>;
}

impl Message for De {
    type Result = (Result<PeerMessage, std::io::Error>, Vec<u8>);
}

pub struct BorshActor {}

impl BorshActor {
    pub fn start() -> Addr<Self> {
        SyncArbiter::start(4, || BorshActor {})
    }
}

impl Actor for BorshActor {
    type Context = SyncContext<Self>;
}

impl Handler<Ser> for BorshActor {
    type Result = Result<Vec<u8>, std::io::Error>;

    fn handle(&mut self, msg: Ser, _ctx: &mut Self::Context) -> Self::Result {
        msg.0.try_to_vec()
    }
}

impl Handler<De> for BorshActor {
    type Result = MessageResult<De>;

    fn handle(&mut self, msg: De, _ctx: &mut Self::Context) -> Self::Result {
        MessageResult((PeerMessage::try_from_slice(&msg.0), msg.0))
    }
}