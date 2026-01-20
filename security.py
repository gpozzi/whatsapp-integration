import ast
import hmac
import hashlib
import secrets

class SecurityError(Exception):
    """Excepción lanzada cuando se detecta código inseguro."""
    pass

def validate_whatsapp_signature(request, app_secret: str) -> bool:
    """Valida la firma HMAC-SHA256 de WhatsApp.

    Args:
        request: El objeto request de Flask.
        app_secret (str): El secreto de la aplicación (App Secret).

    Returns:
        bool: True si la firma es válida, False en caso contrario.
    """
    signature = request.headers.get("X-Hub-Signature-256")
    if not signature or not signature.startswith("sha256="):
        return False

    try:
        # Extraer el hash recibido
        sig_hash = signature.split("=")[1]

        # Calcular el HMAC esperado
        # request.get_data() devuelve los bytes raw del body
        expected_hash = hmac.new(
            app_secret.encode('utf-8'),
            request.get_data(),
            hashlib.sha256
        ).hexdigest()

        # Comparación segura
        return secrets.compare_digest(sig_hash, expected_hash)
    except Exception:
        return False

def validate_python_code(code: str) -> None:
    """Valida que el código Python no contenga importaciones peligrosas.

    Analiza el Abstract Syntax Tree (AST) del código para detectar
    intentos de importar librerías del sistema o acceder a atributos internos.

    Args:
        code (str): El código Python a validar.

    Raises:
        SecurityError: Si se detecta una violación de seguridad.
    """
    try:
        # Intentamos parsear el código. Si falla, asumimos que no es ejecutable
        # o que el REPL manejará el error de sintaxis.
        tree = ast.parse(code)
    except SyntaxError:
        return

    # Lista negra de módulos peligrosos
    unsafe_modules = {
        'os', 'sys', 'subprocess', 'platform', 'shutil',
        'importlib', 'builtins', 'socket', 'urllib', 'http',
        'pickle', 'base64', 'requests'
    }

    for node in ast.walk(tree):
        # 1. Verificar Importaciones directas (import os)
        if isinstance(node, ast.Import):
            for alias in node.names:
                root_module = alias.name.split('.')[0]
                if root_module in unsafe_modules:
                    raise SecurityError(f"Importación prohibida: '{alias.name}'")

        # 2. Verificar Importaciones desde (from os import path)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                root_module = node.module.split('.')[0]
                if root_module in unsafe_modules:
                    raise SecurityError(f"Importación prohibida desde: '{node.module}'")

        # 3. Verificar acceso a atributos peligrosos (__builtins__, __import__)
        elif isinstance(node, ast.Attribute):
            if node.attr in ['__builtins__', '__import__', '__subclasses__']:
                raise SecurityError(f"Acceso a atributo prohibido: '{node.attr}'")

        # 4. Verificar acceso a nombres prohibidos (__builtins__)
        elif isinstance(node, ast.Name):
            if node.id in ['__builtins__', '__import__']:
                raise SecurityError(f"Acceso a nombre prohibido: '{node.id}'")

        # 5. Verificar llamadas a funciones peligrosas si están en el código (eval, exec)
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                if node.func.id in ['eval', 'exec', 'open', '__import__']:
                    raise SecurityError(f"Función prohibida: '{node.func.id}'")
