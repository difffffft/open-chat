from flask import Blueprint as Controller, request
from model import ContextModel
from common import Result
from constants import base_db


context_controller = Controller("context", __name__, url_prefix='/context')


@context_controller.route("/list/<string:chat_id>", methods=["GET"])
def list_(chat_id):
    db_data = base_db.session.query(ContextModel).filter(
        ContextModel.chat_id == chat_id).order_by(ContextModel.t.asc()).all()
    data = []
    for item in db_data:
        data.append({
            "id": item.id,
            "chat_id": item.chat_id,
            "content": item.content,
            "role": item.role,
            "status": item.status,
            "tool_name": item.tool_name,
            "create_time": str(item.create_time),
        })
    return Result.ok(data)


@context_controller.route("/", methods=["POST"])
def save_():
    vo = request.json
    model = ContextModel(
        chat_id=vo['chat_id'], content=vo['content'], role=vo['role'], status=vo['status'])
    base_db.session.add(model)
    base_db.session.commit()
    return Result.ok(model.id)
