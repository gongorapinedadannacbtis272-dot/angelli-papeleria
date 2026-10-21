# Angelli · Papelería y creatividad

Proyecto editable de Flask con catálogo, carrito de compras, registro de clientes, inicio de sesión y administración de productos.

## Cómo abrirlo y ejecutarlo en Windows

1. Extrae el archivo ZIP.
2. Abre la carpeta `angelli_papeleria` en Visual Studio Code.
3. Abre Terminal → Nueva terminal y ejecuta:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe app.py
```

4. Abre http://127.0.0.1:5000 en tu navegador.

## Cuentas

- Administrador de demostración: usuario `angelli`, contraseña `Angelli2026!`.
- Clientes: pueden crear su propia cuenta en el enlace “Crear una cuenta” y entrar con su correo y contraseña.
- Las cuentas de clientes se guardan de manera permanente si se configura `MONGO_URI`. Sin MongoDB, las cuentas creadas solo existen mientras la aplicación siga ejecutándose.
- Las cuentas de cliente no pueden acceder al panel administrativo.

## Carrito

El carrito permite agregar productos, ver el total, cambiar cantidades, eliminar artículos, vaciarlo y finalizar una compra de demostración. No procesa pagos reales ni crea un pedido real.

## MongoDB Atlas (opcional)

Configura la variable de entorno `MONGO_URI` con la cadena de conexión de tu base de datos. La aplicación usa la base `papeleria_angelli`, con colecciones `productos` y `usuarios`. Si MongoDB no está configurado, se muestran productos de ejemplo.

Antes de publicar el sitio, configura variables de entorno seguras para `SECRET_KEY`, `ADMIN_USER` y `ADMIN_PASSWORD_HASH`. No publiques credenciales reales en el código.
