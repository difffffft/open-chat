from flask import g
from sqlalchemy import Column, BigInteger, Integer, String, Text

from .base_model import BaseModel


class ChatModel(BaseModel):
    __tablename__ = "t_chat"

    title = Column(String(255), nullable=False, comment="标题")
    user_id = Column(String(255), nullable=False, comment="用户ID")
    type_code = Column(String(255), nullable=False, comment="专家类型")
    meta = Column(Text, comment="元信息")