use actix::{Actor, Context, Handler};
use log::{info, warn, error};
use std::time::Instant;

pub mod types {
    use near_primitives::errors::InvalidTxError;
    use near_primitives::utils::DisplayOption;
    use std::net::SocketAddr;
    use std::time::Instant;
    use crate::PeerInfo;

    pub enum FnType {
        StreamHandler,
        Encode,
        Decode,
    }

    impl FnType {
        pub fn to_str(&self) -> &str {
            match self {
                Self::StreamHandler => "STREAM_HANDLER",
                Self::Decode => "DECODE",
                Self::Encode => "ENCODE",
            }
        }
    }

    pub enum Message {
        ErrorConvertToBytes(std::io::Error),
        GetChainFailed(actix::MailboxError),
        HandshakeToUnknownPeer,
        InvalidTx(DisplayOption<PeerInfo>, InvalidTxError),
        FnCall {
            fn_type: FnType,
            start: Instant,
            end: Instant,
            call_id: u64,
            remote_addr: SocketAddr,
        },
    }

    impl actix::Message for Message {
        type Result = ();
    }
}

#[derive(Default)]
pub struct Logger {}

impl Actor for Logger {
    type Context = Context<Self>;

    fn started(&mut self, ctx: &mut Self::Context) {
        ctx.set_mailbox_capacity(500_000);
    }
}

impl Handler<types::Message> for Logger {
    type Result = ();

    fn handle(&mut self, msg: types::Message, _ctx: &mut Self::Context) -> Self::Result {
        match msg {
            types::Message::FnCall {fn_type, start, end, call_id, remote_addr} => {
                let now = Instant::now();
                let call_duration = end.duration_since(start);
                let duration_since_start = now.duration_since(start);
                info!(
                    "{} id={} remote_addr={} started_ms_ago={} duration_ms={}",
                    fn_type.to_str(),
                    call_id,
                    remote_addr,
                    duration_since_start.as_millis(),
                    call_duration.as_millis()
                );
            }
            types::Message::InvalidTx(peer_info, err) => {
                warn!(target: "network", "Received invalid tx from peer {}: {}", peer_info, err);
            }
            types::Message::HandshakeToUnknownPeer => {
                error!(target: "network", "Sending handshake to an unknown peer");
            }
            types::Message::ErrorConvertToBytes(err) => {
                error!(target: "network", "Error converting message to bytes: {}", err);
            }
            types::Message::GetChainFailed(err) => {
                error!(target: "network", "Failed sending GetChain to client: {}", err);
            }
        }
    }
}