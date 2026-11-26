import json

from flask import (
    Blueprint, current_app, g, jsonify, redirect, render_template, request, url_for
)
from werkzeug.exceptions import abort

from flaskr.auth import login_required
from flaskr.db import get_db
from flaskr.rag.retriever import answer



bp = Blueprint('chat', __name__)

MAX_LEN = 2000
DEFAULT_TITLE = "Nuevo chat"


def user_chats():
    return get_db().execute(
        "SELECT id, title, created FROM chat WHERE user_id = ? "
        "ORDER BY created DESC, id DESC", (g.user["id"],)).fetchall()


def get_chat(chat_id):
    # Filtra por dueño: un chat ajeno responde 404 (evita IDOR)
    chat = get_db().execute(
        "SELECT id, title FROM chat WHERE id = ? AND user_id = ?",
        (chat_id, g.user["id"])).fetchone()
    if chat is None:
        abort(404)
    return chat


@bp.route('/')
def index():
    return render_template('chat/index.html')


@bp.route('/chat')
@login_required
def chat():
    chats = user_chats()
    if chats:
        return redirect(url_for("chat.view", chat_id=chats[0]["id"]))
    return render_template("chat/view.html", chats=chats, chat=None, messages=[])


@bp.route('/chat/new', methods=('POST',))
@login_required
def new():
    db = get_db()
    cur = db.execute(
        "INSERT INTO chat (user_id, title) VALUES (?, ?)",
        (g.user["id"], DEFAULT_TITLE))
    db.commit()
    return redirect(url_for("chat.view", chat_id=cur.lastrowid))


@bp.route('/chat/<int:chat_id>')
@login_required
def view(chat_id):
    chat = get_chat(chat_id)
    rows = get_db().execute(
        "SELECT rol, content, sources FROM message "
        "WHERE chat_id = ? ORDER BY id", (chat_id,)).fetchall()
    messages = [
        {"role": r["rol"], "content": r["content"],
         "sources": json.loads(r["sources"]) if r["sources"] else []}
        for r in rows
    ]
    return render_template("chat/view.html", chats=user_chats(),
                           chat=chat, messages=messages)


@bp.route('/chat/<int:chat_id>/send', methods=('POST',))
@login_required
def send(chat_id):
    chat = get_chat(chat_id)
    question = (request.get_json(silent=True) or {}).get("message", "")
    question = question.strip() if isinstance(question, str) else ""
    if not question or len(question) > MAX_LEN:
        return jsonify(error="Mensaje vacío o demasiado largo"), 400

    db = get_db()
    history = [(r["rol"], r["content"]) for r in db.execute(
        "SELECT rol, content FROM message WHERE chat_id = ? ORDER BY id",
        (chat_id,))]

    try:
        text, sources = answer(question, history)
    except Exception:
        current_app.logger.exception("Fallo en el RAG")
        return jsonify(error="No se pudo generar la respuesta"), 502

    db.execute("INSERT INTO message (chat_id, rol, content) VALUES (?,?,?)",
               (chat_id, "user", question))
    db.execute("INSERT INTO message (chat_id, rol, content, sources) "
               "VALUES (?,?,?,?)",
               (chat_id, "assistant", text, json.dumps(sources)))
    if chat["title"] == DEFAULT_TITLE:
        db.execute("UPDATE chat SET title = ? WHERE id = ?",
                   (question[:40], chat_id))
    db.commit()
    return jsonify(reply=text, sources=sources)


## PARTE DEL TUTORIAL DE FLASK

# @bp.get("/<int:chat_id>")
# @login_required
# def view(chat_id):
#     chat = get_chat(chat_id)
#     messages = get_db().execute(
#         "SELECT rol, content FROM message WHERE chat_id = ? ORDER BY created, id",
#         (chat_id,)).fetchall()
#     return render_template("chat/view.html", chats=user_chats(), chat=chat, messages=messages)
 

# @bp.post("/new")
# @login_required
# def new():
#     db = get_db()
#     cur = db.execute("INSERT INTO chat (user_id, title) VALUES (?, ?)",
#                      (g.user["id"], "Nuevo chat"))
#     db.commit()
#     return redirect(url_for("chat.view", chat_id=cur.lastrowid))

# @bp.route('/create', methods=('GET', 'POST'))
# @login_required
# def create():
#     if request.method == 'POST':
#         title = request.form['title']
#         body = request.form['body']
#         error = None

#         if not title:
#             error = 'Title is required.'

#         if error is not None:
#             flash(error)
#         else:
#             db = get_db()
#             db.execute(
#                 'INSERT INTO post (title, body, author_id)'
#                 ' VALUES (?, ?, ?)',
#                 (title, body, g.user['id'])
#             )
#             db.commit()
#             return redirect(url_for('blog.index'))

#     return render_template('blog/create.html')

# def get_post(id, check_author=True):
#     post = get_db().execute(
#         'SELECT p.id, title, body, created, author_id, username'
#         ' FROM post p JOIN user u ON p.author_id = u.id'
#         ' WHERE p.id = ?',
#         (id,)
#     ).fetchone()

#     if post is None:
#         abort(404, f"Post id {id} doesn't exist.")

#     if check_author and post['author_id'] != g.user['id']:
#         abort(403)

#     return post

# @bp.route('/<int:id>/update', methods=('GET', 'POST'))
# @login_required
# def update(id):
#     post = get_post(id)

#     if request.method == 'POST':
#         title = request.form['title']
#         body = request.form['body']
#         error = None

#         if not title:
#             error = 'Title is required.'

#         if error is not None:
#             flash("este es el error", error)
#         else:
#             db = get_db()
#             db.execute(
#                 'UPDATE post SET title = ?, body = ?'
#                 ' WHERE id = ?',
#                 (title, body, id)
#             )
#             db.commit()
#             return redirect(url_for('blog.index'))

#     return render_template('blog/update.html', post=post)

# @bp.route('/<int:id>/delete', methods=('POST',))
# @login_required
# def delete(id):
#     get_post(id)
#     db = get_db()
#     db.execute('DELETE FROM post WHERE id = ?', (id,))
#     db.commit()
#     return redirect(url_for('blog.index'))