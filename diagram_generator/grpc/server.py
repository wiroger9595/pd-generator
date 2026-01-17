"""
gRPC 服务器启动文件
使用新的服务层
"""
import time
import grpc
from concurrent import futures
from dotenv import load_dotenv
import os

import proto.TreeDiagramGenerateGrpc_pb2 as pb2
import proto.TreeDiagramGenerateGrpc_pb2_grpc as pb2_grpc
from diagram_generator.grpc.service_servicer import TreeDiagramServiceServicer
from grpc_reflection.v1alpha import reflection

load_dotenv()
SERVER_PORT = os.getenv('SERVER_PORT', '9091')


def serve():
    """
    启动 gRPC 服务器
    """
    MAX_MESSAGE_LENGTH = 32 * 1024 * 1024
    server = grpc.server(
        futures.ThreadPoolExecutor(max_workers=10),
        options=[
            ('grpc.max_send_message_length', MAX_MESSAGE_LENGTH),
            ('grpc.max_receive_message_length', MAX_MESSAGE_LENGTH),
        ]
    )

    print("--- 准备注册 gRPC 服务 ---")

    # 将服务实现类别加入到服务器中
    pb2_grpc.add_TreeDiagramGenerateGrpcServiceServicer_to_server(
        TreeDiagramServiceServicer(), server
    )

    print("--- 服务注册完成 ---")

    SERVICE_NAMES = (
        pb2.DESCRIPTOR.services_by_name[
            "TreeDiagramGenerateGrpcService"
        ].full_name,
        reflection.SERVICE_NAME,
    )

    reflection.enable_server_reflection(SERVICE_NAMES, server)

    server.add_insecure_port(f'[::]:{SERVER_PORT}')
    print(f"Python gRPC server listening on port {SERVER_PORT}...")
    server.start()

    try:
        while True:
            time.sleep(86400)
    except KeyboardInterrupt:
        print("服务器关闭中...")
        server.stop(0)


if __name__ == '__main__':
    serve()
