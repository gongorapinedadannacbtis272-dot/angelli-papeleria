import os
import re
from datetime import datetime, timezone
from functools import wraps

from flask import (
    Flask, render_template, request, redirect, url_for, session, flash
)
from werkzeug.security import generate_password_hash, check_password_hash
from pymongo import MongoClient
from pymongo.errors import PyMongoError, DuplicateKeyError
from bson import ObjectId
from bson.errors import InvalidId

app = Flask(__name__)
app.secret_key = os.environ.get(
    "SECRET_KEY", "clave-de-demostracion-cambiar-antes-de-publicar"
)

# Validación básica de correo electrónico para el registro de clientes.
CORREO_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# Si no se configura MongoDB, las cuentas creadas se guardan en memoria
# mientras la aplicación esté ejecutándose.
usuarios_demo = {}


@app.context_processor
def datos_globales():
    """Hace disponible el contador del carrito en todas las plantillas."""
    carrito = session.get("carrito", {})
    cantidad_total = 0
    if isinstance(carrito, dict):
        for item in carrito.values():
            if isinstance(item, dict):
                try:
                    cantidad_total += max(0, int(item.get("cantidad", 0)))
                except (TypeError, ValueError):
                    pass
    return {"cantidad_carrito": cantidad_total}


mongo_uri = os.environ.get("MONGO_URI")
if mongo_uri:
    cliente = MongoClient(mongo_uri, serverSelectionTimeoutMS=5000)
    # Usa la misma base de datos indicada en el proyecto original.
    db = cliente["papeleria_angelli"]
    try:
        db["usuarios"].create_index("correo", unique=True)
    except PyMongoError:
        # La conexión también puede revisarse al realizar una petición.
        pass
else:
    cliente = None
    db = None


productos_demo = [
    {"_id": "demo1", "nombre": "Cuaderno profesional", "categoria": "Cuadernos", "precio": 38.00, "estado": "Disponible", "emoji": "📒", "existencias": 20},
    {"_id": "demo2", "nombre": "Plumas de colores", "categoria": "Escritura", "precio": 25.00, "estado": "Disponible", "emoji": "🖊️", "existencias": 20},
    {"_id": "demo3", "nombre": "Resaltadores pastel", "categoria": "Escritura", "precio": 42.00, "estado": "Disponible", "emoji": "🖍️", "existencias": 20},
    {"_id": "demo4", "nombre": "Notas adhesivas", "categoria": "Organización", "precio": 19.00, "estado": "Agotado", "emoji": "🗒️", "existencias": 0},
    {"_id": "demo5", "nombre": "Kit de geometría", "categoria": "Escolar", "precio": 55.00, "estado": "Disponible", "emoji": "📐", "existencias": 20},
    {"_id": "demo6", "nombre": "Marcadores", "categoria": "Arte", "precio": 48.00, "estado": "Disponible", "emoji": "🎨", "existencias": 20},
]


# Completa el catálogo de MongoDB con los productos de demostración que falten.
# No borra ni reemplaza los productos que ya existen.
if db is not None:
    try:
        nombres_existentes = {
            str(producto.get("nombre", "")).strip().casefold()
            for producto in db["productos"].find({}, {"nombre": 1})
        }

        productos_faltantes = [
            {clave: valor for clave, valor in producto.items() if clave != "_id"}
            for producto in productos_demo
            if str(producto.get("nombre", "")).strip().casefold()
            not in nombres_existentes
        ]

        if productos_faltantes:
            db["productos"].insert_many(productos_faltantes)
            app.logger.info("Se agregaron %s productos iniciales a MongoDB.", len(productos_faltantes))
    except PyMongoError:
        # El error se registra y podrá diagnosticarse en los logs de Render.
        app.logger.exception("No se pudieron completar los productos iniciales de MongoDB.")


def requiere_admin(func):
    """Deja las rutas de administración solamente para el rol admin."""
    @wraps(func)
    def envoltura(*args, **kwargs):
        if not session.get("usuario"):
            flash("Inicia sesión para continuar.", "info")
            return redirect(url_for("login"))
        if session.get("rol") != "admin":
            flash("Tu cuenta de cliente no tiene acceso a administración.", "warning")
            return redirect(url_for("inicio"))
        return func(*args, **kwargs)
    return envoltura


def obtener_productos():
    if db is None:
        return productos_demo
    return list(db["productos"].find().sort("nombre", 1))


def buscar_producto(producto_id):
    if db is None:
        return next(
            (p for p in productos_demo if str(p.get("_id")) == str(producto_id)),
            None,
        )
    try:
        return db["productos"].find_one({"_id": ObjectId(producto_id)})
    except (InvalidId, TypeError):
        return None


def cantidad_segura(valor, predeterminado=1):
    try:
        cantidad = int(valor)
    except (TypeError, ValueError):
        cantidad = predeterminado
    return max(1, min(cantidad, 99))


@app.route("/")
def inicio():
    productos = obtener_productos()
    categorias = sorted(set(p.get("categoria", "Escolar") for p in productos))
    termino = request.args.get("q", "").strip().lower()
    if termino:
        productos = [
            p for p in productos
            if termino in str(p.get("nombre", "")).lower()
            or termino in str(p.get("categoria", "")).lower()
        ]
    return render_template(
        "index.html", productos=productos, categorias=categorias, termino=termino
    )


# ------------------------------
# REGISTRO DE CUENTAS DE CLIENTE
# ------------------------------
@app.route("/registro", methods=["GET", "POST"])
def registro():
    if session.get("usuario"):
        return redirect(url_for("inicio"))

    if request.method == "POST":
        nombre = request.form.get("nombre", "").strip()
        correo = request.form.get("correo", "").strip().lower()
        contrasena = request.form.get("contrasena", "")
        confirmar = request.form.get("confirmar", "")

        if len(nombre) < 2 or len(nombre) > 60:
            flash("El nombre debe tener entre 2 y 60 caracteres.", "danger")
        elif len(correo) > 120 or not CORREO_RE.match(correo):
            flash("Escribe un correo electrónico válido.", "danger")
        elif len(contrasena) < 8:
            flash("La contraseña debe tener al menos 8 caracteres.", "danger")
        elif contrasena != confirmar:
            flash("Las contraseñas no coinciden.", "danger")
        else:
            cuenta = {
                "nombre": nombre,
                "correo": correo,
                "contrasena": generate_password_hash(contrasena),
                "rol": "cliente",
            }

            if db is None:
                if correo in usuarios_demo:
                    flash("Ese correo ya tiene una cuenta. Inicia sesión.", "warning")
                    return render_template("registro.html")
                usuarios_demo[correo] = cuenta
            else:
                try:
                    db["usuarios"].insert_one({
                        **cuenta,
                        "fechaRegistro": datetime.now(timezone.utc),
                    })
                except DuplicateKeyError:
                    flash("Ese correo ya está registrado. Inicia sesión.", "warning")
                    return render_template("registro.html")

            carrito_actual = session.get("carrito", {})
            session.clear()
            session["usuario"] = nombre
            session["correo"] = correo
            session["rol"] = "cliente"
            session["carrito"] = carrito_actual if isinstance(carrito_actual, dict) else {}
            flash("¡Tu cuenta se creó correctamente! Ya puedes comprar.", "success")
            return redirect(url_for("inicio"))

    return render_template("registro.html")


# ------------------------------
# INICIO DE SESIÓN ADMIN/CLIENTE
# ------------------------------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        usuario = request.form.get("usuario", "").strip()
        contrasena = request.form.get("contrasena", "")

        # Cuenta administradora de demostración o configurada por variables de entorno.
        admin_user = os.environ.get("ADMIN_USER", "angelli")
        admin_password_hash = os.environ.get("ADMIN_PASSWORD_HASH")
        if admin_password_hash:
            es_admin = (
                usuario == admin_user
                and check_password_hash(admin_password_hash, contrasena)
            )
        else:
            es_admin = False

        if es_admin:
            session.clear()
            session["usuario"] = admin_user
            session["rol"] = "admin"
            session["carrito"] = {}
            flash("¡Bienvenida/o al panel de administración!", "success")
            return redirect(url_for("admin"))

        # Los clientes entran utilizando el correo con el que se registraron.
        correo = usuario.lower()
        if db is None:
            cuenta = usuarios_demo.get(correo)
        else:
            cuenta = db["usuarios"].find_one({"correo": correo})

        if cuenta and check_password_hash(cuenta.get("contrasena", ""), contrasena):
            carrito_actual = session.get("carrito", {})
            session.clear()
            session["usuario"] = cuenta.get("nombre", correo)
            session["correo"] = cuenta.get("correo", correo)
            session["rol"] = "cliente"
            session["carrito"] = carrito_actual if isinstance(carrito_actual, dict) else {}
            flash("¡Iniciaste sesión correctamente!", "success")
            return redirect(url_for("inicio"))

        flash("Usuario/correo o contraseña incorrectos.", "danger")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("Sesión cerrada correctamente.", "info")
    return redirect(url_for("inicio"))


# ------------------------------
# CARRITO DE COMPRAS
# ------------------------------
@app.route("/carrito")
def ver_carrito():
    carrito = session.get("carrito", {})
    items = []
    total = 0.0

    if isinstance(carrito, dict):
        for producto_id, datos in carrito.items():
            producto = buscar_producto(producto_id)
            if producto is None or not isinstance(datos, dict):
                continue
            cantidad = cantidad_segura(datos.get("cantidad", 1))
            try:
                precio = max(0.0, float(producto.get("precio", 0)))
            except (TypeError, ValueError):
                precio = 0.0
            subtotal = precio * cantidad
            items.append({
                "id": str(producto_id),
                "producto": producto,
                "cantidad": cantidad,
                "subtotal": subtotal,
            })
            total += subtotal

    return render_template("carrito.html", items=items, total=total)


@app.route("/carrito/agregar/<producto_id>", methods=["POST"])
def carrito_agregar(producto_id):
    producto = buscar_producto(producto_id)
    if producto is None:
        flash("No se encontró ese producto. Actualiza la página e inténtalo de nuevo.", "danger")
        return redirect(url_for("inicio"))
    if producto.get("estado", "Disponible") == "Agotado":
        flash("Ese producto está agotado.", "warning")
        return redirect(url_for("inicio") + "#catalogo")

    carrito = session.get("carrito", {})
    if not isinstance(carrito, dict):
        carrito = {}
    datos = carrito.get(producto_id, {"cantidad": 0})
    actual = datos.get("cantidad", 0) if isinstance(datos, dict) else 0
    try:
        actual = int(actual)
    except (TypeError, ValueError):
        actual = 0
    carrito[producto_id] = {"cantidad": min(max(actual, 0) + 1, 99)}
    session["carrito"] = carrito
    session.modified = True
    flash(f"{producto.get('nombre', 'Producto')} se agregó al carrito.", "success")
    return redirect(request.referrer or url_for("inicio"))


@app.route("/carrito/cantidad/<producto_id>", methods=["POST"])
def carrito_cantidad(producto_id):
    carrito = session.get("carrito", {})
    if not isinstance(carrito, dict) or producto_id not in carrito:
        return redirect(url_for("ver_carrito"))

    try:
        cantidad = int(request.form.get("cantidad", "1"))
    except (TypeError, ValueError):
        cantidad = 1

    if cantidad <= 0:
        carrito.pop(producto_id, None)
    else:
        datos = carrito.get(producto_id)
        if isinstance(datos, dict):
            datos["cantidad"] = min(cantidad, 99)
            carrito[producto_id] = datos
    session["carrito"] = carrito
    session.modified = True
    return redirect(url_for("ver_carrito"))


@app.route("/carrito/eliminar/<producto_id>", methods=["POST"])
def carrito_eliminar(producto_id):
    carrito = session.get("carrito", {})
    if isinstance(carrito, dict):
        carrito.pop(producto_id, None)
    session["carrito"] = carrito
    session.modified = True
    flash("Producto eliminado del carrito.", "info")
    return redirect(url_for("ver_carrito"))


@app.route("/carrito/vaciar", methods=["POST"])
def carrito_vaciar():
    session["carrito"] = {}
    session.modified = True
    flash("Se vació el carrito.", "info")
    return redirect(url_for("ver_carrito"))


@app.route("/carrito/finalizar", methods=["POST"])
def carrito_finalizar():
    carrito = session.get("carrito", {})
    total = 0.0
    if isinstance(carrito, dict):
        for producto_id, datos in carrito.items():
            producto = buscar_producto(producto_id)
            if producto is None or not isinstance(datos, dict):
                continue
            cantidad = cantidad_segura(datos.get("cantidad", 1))
            try:
                precio = max(0.0, float(producto.get("precio", 0)))
            except (TypeError, ValueError):
                precio = 0.0
            total += precio * cantidad

    if total <= 0:
        flash("Tu carrito está vacío.", "warning")
        return redirect(url_for("ver_carrito"))

    session["carrito"] = {}
    session.modified = True
    return render_template("compra_confirmada.html", total=total)


# ------------------------------
# ADMINISTRACIÓN DE PRODUCTOS
# ------------------------------
@app.route("/admin")
@requiere_admin
def admin():
    productos = obtener_productos()
    return render_template("admin.html", productos=productos, mongo_activo=db is not None)


@app.route("/productos/agregar", methods=["POST"])
@requiere_admin
def agregar_producto():
    nombre = request.form.get("nombre", "").strip()
    categoria = request.form.get("categoria", "").strip()
    estado = request.form.get("estado", "Disponible")
    try:
        precio = float(request.form.get("precio", "0"))
    except (TypeError, ValueError):
        precio = -1

    if not nombre or not categoria or precio < 0 or estado not in ("Disponible", "Agotado"):
        flash("Revisa los datos del producto.", "danger")
        return redirect(url_for("admin"))

    producto = {
        "nombre": nombre[:80],
        "categoria": categoria[:30],
        "precio": round(precio, 2),
        "estado": estado,
        "emoji": "📦",
        "existencias": 0 if estado == "Agotado" else 10,
    }
    if db is not None:
        db["productos"].insert_one(producto)
        flash("Producto guardado en MongoDB.", "success")
    else:
        flash("Modo demostración: conecta MongoDB con MONGO_URI para guardar productos permanentemente.", "warning")
    return redirect(url_for("admin"))


@app.route("/productos/eliminar/<producto_id>", methods=["POST"])
@requiere_admin
def eliminar_producto(producto_id):
    if db is not None:
        try:
            db["productos"].delete_one({"_id": ObjectId(producto_id)})
            flash("Producto eliminado.", "success")
        except InvalidId:
            flash("Identificador no válido.", "danger")
    else:
        flash("La eliminación permanente requiere configurar MongoDB.", "warning")
    return redirect(url_for("admin"))


@app.errorhandler(PyMongoError)
def error_mongo(error):
    app.logger.exception("Error al trabajar con MongoDB: %s", error)
    flash("No se pudo conectar con MongoDB. Revisa MONGO_URI y sus permisos.", "danger")
    return redirect(url_for("admin" if session.get("rol") == "admin" else "inicio"))


if __name__ == "__main__":
    app.run(debug=True)
