import contextlib
from io import StringIO
import re
import sys
from flask import Blueprint as Controller, Response, request, g, stream_with_context
from constants import base_client, BASE_MODEL, base_db, CHAT_SYSTEM_PROMPT, RESUME_SYSTEM_PROMPT, CHAT_TYPE
from model import ChatModel, ContextModel, TypeModel
from common import Result

chat_controller = Controller("chat", __name__, url_prefix='/chat')


@chat_controller.route("/", methods=["POST"])
def save_():
    title = request.json["title"]
    type_code = request.json["type_code"]

    model = ChatModel(title=title, user_id=g.uid, type_code=type_code)
    base_db.session.add(model)
    base_db.session.commit()
    return Result.ok(model.id)


@chat_controller.route("/", methods=["DELETE"])
def delete_():
    ids = request.json
    chats_to_delete = base_db.session.query(
        ChatModel).filter(ChatModel.id.in_(ids)).all()
    for chat in chats_to_delete:
        base_db.session.delete(chat)
    base_db.session.commit()
    return Result.ok()


@chat_controller.route("/all", methods=["DELETE"])
def delete_all_():
    ids = [chat.id for chat in base_db.session.query(
        ChatModel).filter(ChatModel.user_id == g.uid).all()]
    chats_to_delete = base_db.session.query(
        ChatModel).filter(ChatModel.id.in_(ids)).all()
    for chat in chats_to_delete:
        base_db.session.delete(chat)
    base_db.session.commit()
    return Result.ok()


@chat_controller.route("/", methods=["PUT"])
def update_():
    vo = request.json
    model = base_db.session.query(ChatModel).filter(
        ChatModel.id == vo['id']).one()
    for key, value in vo.items():
        setattr(model, key, value)
    base_db.session.commit()
    return Result.ok()


@chat_controller.route("/<string:id>", methods=["GET"])
def info_(id):
    db_data = base_db.session.query(ChatModel).filter(ChatModel.id == id).one()
    return Result.ok({
        "id": db_data.id,
        "title": db_data.title,
        "user_id": db_data.user_id,
        "type_code": db_data.type_code,
        "create_time": str(db_data.create_time),
    })


@chat_controller.route("/list", methods=["GET"])
def chat_list_():
    db_data = base_db.session.query(ChatModel).filter(
        ChatModel.user_id == g.uid).order_by(ChatModel.t.desc()).all()
    data = []
    for item in db_data:
        data.append({
            "id": item.id,
            "title": item.title,
            "user_id": item.user_id,
            "type_code": item.type_code,
            "create_time": str(item.create_time),
        })
    return Result.ok(data)


def get_context(chat_id, chat_type):
    """
    聊天时:获取上下文
    """
    messages = []
    db_chat = base_db.session.query(ChatModel).filter(
        ChatModel.id == chat_id).one()
    db_type = base_db.session.query(TypeModel).filter(
        TypeModel.code == db_chat.type_code).one()
    context_list = base_db.session.query(ContextModel).filter(
        ContextModel.chat_id == chat_id, ContextModel.status == 1).order_by(ContextModel.t.asc()).all()

    if chat_type == CHAT_TYPE.NORMAL:
        messages.append({
            "role": "system",
            "content": db_type.system_prompt,
        })
    elif chat_type == CHAT_TYPE.RESUME:
        messages.append({
            "role": "system",
            "content": RESUME_SYSTEM_PROMPT,
        })
    for item in context_list:
        if item.role == "user" and db_type.question_prompt != None:
            content = db_type.question_prompt.format(item.content, item.content, item.content)
            messages.append({
                "role": item.role,
                "content": content,
            })
            print("============>", content)
        else:
            messages.append({
                "role": item.role,
                "content": item.content,
            })
    return messages


def save_question(chat_id, question):
    """
    保存问题
    """
    if question != "":
        user_context = ContextModel(
            chat_id=chat_id, content=question, role="user", status=1, tool_name="", tool_parameters=None)
        base_db.session.add(user_context)
        base_db.session.commit()


def save_anwser(chat_id, anwser):
    """
    保存回答
    """
    if anwser != "":
        assistant_context = ContextModel(
            chat_id=chat_id, content=anwser, role="assistant", status=1, tool_name="", tool_parameters=None)
        base_db.session.add(assistant_context)
        base_db.session.commit()


@chat_controller.route("/resume", methods=["POST"])
def resume_():
    """
    总结对话
    """
    chat_id = request.json["chat_id"]
    messages = get_context(chat_id, CHAT_TYPE.RESUME)
    response = base_client.chat.completions.create(
        model=BASE_MODEL,
        messages=messages
    )
    model = base_db.session.query(ChatModel).filter(
        ChatModel.id == chat_id).one()
    model.title = response.choices[0].message.content
    base_db.session.commit()
    return Result.ok()


def code_run(code):
    """
    运行代码
    """
    @contextlib.contextmanager
    def stdoutIO(stdout=None):
        old = sys.stdout
        if stdout is None:
            stdout = StringIO()
        sys.stdout = stdout
        yield stdout
        sys.stdout = old

    with stdoutIO() as s:
        try:
            import matplotlib
            matplotlib.use('agg')
            exec(code)
        except Exception as e:
            return "代码运行失败:" + str(e)
    return "代码运行结果如下:" + s.getvalue()


@chat_controller.route("/code/auto/run/<string:chat_id>", methods=["POST"])
def code_auto_run_(chat_id):
    """
    Python自动运行代码
    """
    messages = get_context(chat_id, CHAT_TYPE.NORMAL)
    if len(messages) <= 0:
        return Result.ok()
    message = messages[-1]
    if message['role'] == "user":
        return Result.ok()

    pattern = r'```python(.*?)```'
    matched_code = re.findall(pattern, message['content'], re.DOTALL)
    for code in matched_code:
        res = code_run(code)
        assistant_context = ContextModel(
            chat_id=chat_id, content=res, role="assistant", status=1, tool_name="", tool_parameters=None)
        base_db.session.add(assistant_context)
        base_db.session.commit()
    
    return Result.ok()


@chat_controller.route("/code/run", methods=["POST"])
def code_run_():
    """
    运行代码
    """
    language = request.json["language"]
    code = request.json["code"]

    @contextlib.contextmanager
    def stdoutIO(stdout=None):
        old = sys.stdout
        if stdout is None:
            stdout = StringIO()
        sys.stdout = stdout
        yield stdout
        sys.stdout = old

    if not language == "python":
        pass
    else:
        with stdoutIO() as s:
            try:
                import matplotlib
                matplotlib.use('agg')
                exec(code)
            except Exception as e:
                return Result.error(str(e))
        return Result.ok(s.getvalue())
    return Result.ok()


@chat_controller.route("/stream", methods=["POST"])
def stream_():
    """
    聊天
    """
    chat_id = request.json["chat_id"]
    question = request.json["question"]

    # 保存用户提问
    save_question(chat_id, question)

    # 获取上下文
    messages = get_context(chat_id, CHAT_TYPE.NORMAL)

    # 开始询问
    stream_response = base_client.chat.completions.create(
        model=BASE_MODEL,
        messages=messages,
        stream=True
    )

    def generate():
        anwser = ""
        for trunk in stream_response:
            content = trunk.choices[0].delta.content
            if trunk.choices[0].finish_reason != 'stop':
                anwser += content
                yield content
            else:
                # 保存回答
                save_anwser(chat_id, anwser)
                yield ""

    return Response(stream_with_context(generate()))


@chat_controller.route("/re/stream", methods=["POST"])
def re_stream_():
    """
    再试一次
    """
    chat_id = request.json["chat_id"]

    # 删除最后
    context_list = base_db.session.query(ContextModel).filter(
        ContextModel.chat_id == chat_id, ContextModel.status == 1).order_by(ContextModel.t.asc()).all()

    if len(context_list) > 0:
        last_context = context_list[-1]
        if last_context.role == "assistant":
            base_db.session.delete(last_context)
            base_db.session.commit()

    # 获取上下文
    messages = get_context(chat_id, CHAT_TYPE.NORMAL)

    # 开始询问
    stream_response = base_client.chat.completions.create(
        model=BASE_MODEL,
        messages=messages,
        stream=True
    )

    def generate():
        anwser = ""
        for trunk in stream_response:
            content = trunk.choices[0].delta.content
            if trunk.choices[0].finish_reason != 'stop':
                anwser += content
                yield content
            else:
                # 保存回答
                save_anwser(chat_id, anwser)
                yield ""

    return Response(stream_with_context(generate()))