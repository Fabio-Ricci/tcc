import argparse
import asyncio
import binascii
import csv
import string
import struct
import datetime
import timeit
from typing import List, Tuple
from dataclasses import dataclass

from aioquic.asyncio import QuicConnectionProtocol
from aioquic.asyncio.client import connect as conn
from aioquic.quic.configuration import QuicConfiguration
from src.dash import Dash

from src.structures.data_types import VideoPacket, QUICPacket
from src.utils import message_to_video_packet, get_client_file_name, get_user_id, create_user_dir, host_parser
from src.constants.video_constants import HIGH_PRIORITY, FRAME_TIME_MS, LOW_PRIORITY, VIDEO_FPS, CLIENT_BITRATES, \
    N_SEGMENTS, MAX_TILE, INITIAL_BUFFER_SIZE


@dataclass
class Tile:
    file_name: str
    file_data: VideoPacket


@dataclass
class Segment:
    index: int
    tiles: List[Tile]


SEGMENT_DURATION = 1  # in seconds
buffer: List[Segment] = []
buffer_limit = 10  # in number of segments
buffer_offset = 0  # in number of segments


async def send_data(writer, stream_id, end_stream, packet=None, push_status=None):
    data = QUICPacket(stream_id, end_stream, packet, push_status).serialize()

    writer.write(struct.pack('<L', len(data)))
    writer.write(data)


async def connect(ca_cert: str, connection_host: str, connection_port: int):
    print("Connecting to Host", connection_host, connection_port)
    configuration = QuicConfiguration(is_client=True)
    configuration.load_verify_locations(ca_cert)
    async with conn(connection_host, connection_port, configuration=configuration) as client:
        connection_protocol = QuicConnectionProtocol
        high_priority_reader, high_priority_writer = await connection_protocol.create_stream(client)
        low_priority_reader, low_priority_writer = await connection_protocol.create_stream(client)
    return high_priority_reader, high_priority_writer, low_priority_reader, low_priority_writer


async def client(ca_cert: str, connection_host: str, connection_port: int, dash_algorithm: Dash):
    hp_reader, hp_writer, lp_reader, lp_writer = await connect(
        ca_cert=ca_cert, connection_host=connection_host, connection_port=connection_port)  # initialize connection

    # thread para receber
    client_id = get_user_id()
    print("Starting Client: ", client_id)
    create_user_dir(client_id)

    asyncio.ensure_future(
        receive(reader=hp_reader, client_id=client_id, dash=dash_algorithm))
    asyncio.ensure_future(
        receive(reader=lp_reader, client_id=client_id, dash=dash_algorithm))

    hp_writer.write(client_id.encode())

    # send data
    message = VideoPacket(1, 1,
                          HIGH_PRIORITY, 10)
    await send_data(hp_writer, stream_id=client_id, end_stream=False, packet=message)

    message = VideoPacket(1, 3,
                          HIGH_PRIORITY, 10)
    await send_data(hp_writer, stream_id=client_id, end_stream=False, packet=message)
    message = VideoPacket(1, 5,
                          HIGH_PRIORITY, 10)
    await send_data(hp_writer, stream_id=client_id, end_stream=False, packet=message)
    message = VideoPacket(1, 2,
                          HIGH_PRIORITY, 10)
    await send_data(hp_writer, stream_id=client_id, end_stream=False, packet=message)
    message = VideoPacket(1, 4,
                          HIGH_PRIORITY, 10)
    await send_data(hp_writer, stream_id=client_id, end_stream=False, packet=message)

    await asyncio.sleep(10)

    await send_data(hp_writer, stream_id=client_id, end_stream=True)
    await send_data(lp_writer, stream_id=client_id, end_stream=True)


async def receive(reader: asyncio.StreamReader, client_id: str, dash: Dash):
    try:
        while True:
            size, = struct.unpack('<L', await reader.read(4))

            dash.append_download_size(size)

            file_name_data = await reader.readexactly(size)
            file_data = message_to_video_packet(eval(file_name_data.decode()))

            file_name = get_client_file_name(segment=file_data.segment, tile=file_data.tile, bitrate=file_data.bitrate,
                                             client_id=client_id)

            print(
                f'Receiving segment {file_data.segment} tile {file_data.tile}')

            # add to buffer
            if len(buffer) + buffer_offset < file_data.segment:  # add new segment
                tiles = MAX_TILE*[None]
                tile = Tile(file_name=file_name, file_data=file_data)
                tile_index = file_data.tile-1
                tiles[tile_index] = tile
                segment = Segment(index=file_data.segment, tiles=tiles)
                buffer.append(segment)
            else:  # append tile to existing segment
                segment_index = file_data.segment-1-buffer_offset
                tile_index = file_data.tile - 1
                buffer[segment_index].tiles[tile_index] = Tile(
                    file_name=file_name, file_data=file_data)
    except Exception as err:
        print(err)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="HTTP/3 client for video streaming")
    parser.add_argument(
        "url",
        type=str,
        help="the URL to query (must be HTTPS)"
    )
    parser.add_argument(
        "-c",
        "--ca-certs",
        type=str,
        help="load CA certificates from the specified file"
    )
    parser.add_argument(
        "-i",
        "--user-input",
        required=True,
        type=str,
        help="CSV file with user input simulation",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        help="increase output verbosity",
        action="store_true"
    )
    parser.add_argument(
        "-da",
        "--dash-algorithm",
        required=False,
        default="basic",
        type=str,
        help="dash algorithm (options: basic, basic2) - (defaults to basic)",
    )

    args = parser.parse_args()

    Client_Log = args.verbose

    User_Input_File = args.user_input

    host, port = host_parser(args.url)

    if port is None:
        port = 4433

    user_dash = Dash(CLIENT_BITRATES, args.dash_algorithm)

    asyncio.get_event_loop().run_until_complete(client(ca_cert=args.ca_certs,
                                                       connection_host=host, connection_port=port, dash_algorithm=user_dash))
