"""Bilibili danmaku protobuf messages.

The checked-in module uses protobuf's runtime descriptor API
"""

from google.protobuf import descriptor_pb2
from google.protobuf import descriptor_pool
from google.protobuf import message as protobuf_message
from google.protobuf import reflection
from google.protobuf import symbol_database

_file = descriptor_pb2.FileDescriptorProto()
_file.name = "dm.proto"
_file.package = "bilibili.community.service.dm.v1"
_file.syntax = "proto3"

_elem = _file.message_type.add()
_elem.name = "DanmakuElem"
for name, number, field_type in (
    ("id", 1, descriptor_pb2.FieldDescriptorProto.TYPE_INT64),
    ("progress", 2, descriptor_pb2.FieldDescriptorProto.TYPE_INT32),
    ("mode", 3, descriptor_pb2.FieldDescriptorProto.TYPE_INT32),
    ("fontsize", 4, descriptor_pb2.FieldDescriptorProto.TYPE_INT32),
    ("color", 5, descriptor_pb2.FieldDescriptorProto.TYPE_UINT32),
    ("midHash", 6, descriptor_pb2.FieldDescriptorProto.TYPE_STRING),
    ("content", 7, descriptor_pb2.FieldDescriptorProto.TYPE_STRING),
    ("ctime", 8, descriptor_pb2.FieldDescriptorProto.TYPE_INT64),
):
    field = _elem.field.add()
    field.name = name
    field.number = number
    field.label = descriptor_pb2.FieldDescriptorProto.LABEL_OPTIONAL
    field.type = field_type

_reply = _file.message_type.add()
_reply.name = "DmSegMobileReply"
_field = _reply.field.add()
_field.name = "elems"
_field.number = 1
_field.label = descriptor_pb2.FieldDescriptorProto.LABEL_REPEATED
_field.type = descriptor_pb2.FieldDescriptorProto.TYPE_MESSAGE
_field.type_name = ".bilibili.community.service.dm.v1.DanmakuElem"

DESCRIPTOR = descriptor_pool.Default().AddSerializedFile(
    _file.SerializeToString()
)
_symbol_database = symbol_database.Default()

DanmakuElem = reflection.GeneratedProtocolMessageType(
    "DanmakuElem",
    (protobuf_message.Message,),
    {
        "DESCRIPTOR": DESCRIPTOR.message_types_by_name["DanmakuElem"],
        "__module__": __name__,
    },
)
_symbol_database.RegisterMessage(DanmakuElem)

DmSegMobileReply = reflection.GeneratedProtocolMessageType(
    "DmSegMobileReply",
    (protobuf_message.Message,),
    {
        "DESCRIPTOR": DESCRIPTOR.message_types_by_name["DmSegMobileReply"],
        "__module__": __name__,
    },
)
_symbol_database.RegisterMessage(DmSegMobileReply)
DecodeError = protobuf_message.DecodeError
