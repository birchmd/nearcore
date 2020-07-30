# Similar to proxy.py, however designed to work with a single node which is part
# of a distributed network, as opposed to a local cluster. The `Interceptor`
# class creates a local node on `inner_port` and a separate python server on
# `outer_port`. Whenever a new connection is opened on `outer_port` the messages
# are forwarded down to the local node (possibly -- messages may be dropped or
# modified depending on the behaviour of `handle_message`), and the responses
# from the node are sent back (again, subject to `handle_message`).
#
# Note: This library requires Python 3.7+ (e.g. Python 3.6 does not work).
#
# Example usage:
# ```
# from interceptor import Interceptor
#
# class MyInterceptor(Interceptor):
#     async def message_handler(self, message):
#         print(f'Custom handling of {message.enum}')
#         return True
#
# x = MyInterceptor()
# x.start_node('/home/ubuntu/near', '/home/ubuntu/near_node.log')
# x.start_server()
# # wait until it is time to shutdown the node...
# x.close()
# ```

import asyncio
import multiprocessing
from rc import bash
import struct
from subprocess import Popen, STDOUT
import time

from messages import schema
from messages.network import PeerMessage
from serializer import BinarySerializer

FORCE_KILL_TIMEOUT = 5

class Interceptor:
    def __init__(self, outer_port=24567, inner_port=24667):
        self.node_proc = None
        self.node_log_handle = None
        self.bridge_tasks = []
        self.server_process = None
        self.outer_port = outer_port
        self.inner_port = inner_port


    def close(self):
        if self.node_proc is not None:
            start_time = time.time()
            while self.node_proc.poll() is None:
                if time.time() - start_time > FORCE_KILL_TIMEOUT:
                    Interceptor.force_kill(self.node_proc.pid)
                    break
                else:
                    self.node_proc.kill()
                    time.sleep(1)
        
        if self.node_log_handle is not None:
            self.node_log_handle.close()
        
        for bridge in self.bridge_tasks:
            bridge.cancel()
        
        # give a moment for the bridge tasks to end
        time.sleep(0.5)

        if self.server_process is not None:
            while self.server_process.exitcode is None:
                if time.time() - start_time > FORCE_KILL_TIMEOUT:
                    Interceptor.force_kill(self.server_process.pid)
                    break
                else:
                    self.server_process.kill()
                    time.sleep(1)
            self.server_process.close()


    @staticmethod
    def force_kill(pid):
        bash(f'kill -9 {pid}')
        time.sleep(1)


    def start_node(self, executable_path, log_path):
        if self.node_log_handle is not None or self.node_proc is not None:
            print('Attempted to start node process, but it is already running.')
            return
        
        log_handle = open(log_path, 'w')
        args = [executable_path, 'run', f'--network-addr=127.0.0.1:{self.inner_port}']
        proc = Popen(args, stdout=log_handle, stderr=STDOUT)
        
        self.node_proc = proc
        self.node_log_handle = log_handle
    
    def start_server(self):
        self.server_process = multiprocessing.Process(target=self.__start_server_blocking)
        self.server_process.start()

    # Function to decide if we pass on the message to the node. `True` means
    # pass on the message unmodified, `False` means do not pass on the message,
    # and returning a new message (possibly derived from the given message) will
    # pass that one to the node indead. Override this method in sub-classes to
    # have custom message handling.
    async def message_handler(self, message):
        return True

    def __start_server_blocking(self):
        asyncio.run(self.__start_server())

    async def __start_server(self):
        server = await asyncio.start_server(self.__handle_connection, port=self.outer_port)
        
        async with server:
            await server.serve_forever()

    async def __raw_message_handler(self, raw_message):
        try:
            if all(map(lambda b: b == 0, raw_message[:5])):
                # indicates 'Handshake' message
                message = BinarySerializer(schema).deserialize(raw_message, PeerMessage)
                assert message.enum == 'Handshake'
                if message.Handshake.listen_port == self.inner_port:
                    message.Handshake.listen_port = self.outer_port
                return BinarySerializer(schema).serialize(message)
            else:
                return True

            # message = BinarySerializer(schema).deserialize(raw_message, PeerMessage)
            # # ensure we do not tell peers about the inner port, only outer one
            # if message.enum == 'Handshake':
            #     print(raw_message[0:5])
            #     if message.Handshake.listen_port == self.inner_port:
            #         message.Handshake.listen_port = self.outer_port
            
            # decision = await self.message_handler(message)

            # if decision is True and message.enum == 'Handshake':
            #     decision = message
            
            # if not isinstance(decision, bool):
            #     decision = BinarySerializer(schema).serialize(decision)
            
            # return decision
        except Exception as err:
            print(f'WARN: Failed to deserialize binary message: {err}')
            return True

    @staticmethod
    async def __bridge(reader, writer, message_handler):
        while True:
            try:
                header = await reader.read(4)
                assert len(header) == 4
                raw_message = await reader.read(struct.unpack('I', header)[0])
                decision = await message_handler(raw_message)

                if isinstance(decision, bytes):
                    raw_message = decision
                    decision = True

                if decision:
                    writer.write(struct.pack('I', len(raw_message)))
                    writer.write(raw_message)
                    await writer.drain()

            except (asyncio.CancelledError, ConnectionResetError, AssertionError):
                reader.close()
                writer.close()
                await reader.wait_closed()
                await writer.wait_closed()
                break

    async def __handle_connection(self, outer_reader, outer_writer):
        inner_reader, inner_writer = await asyncio.open_connection(host='127.0.0.1', port=self.inner_port)

        out_to_in_task = asyncio.create_task(Interceptor.__bridge(outer_reader, inner_writer, self.__raw_message_handler))
        in_to_out_task = asyncio.create_task(Interceptor.__bridge(inner_reader, outer_writer, self.__raw_message_handler))
        self.bridge_tasks.append(out_to_in_task)
        self.bridge_tasks.append(in_to_out_task)

