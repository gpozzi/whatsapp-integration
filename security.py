import ast
import hmac
import hashlib
import secrets

class SecurityError(Exception):
    """Excepción lanzada cuando se detecta código inseguro."""
    pass

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

def validate_signature(payload: bytes, signature: str, secret: str) -> bool:
    """Valida la firma HMAC de una solicitud.

    Args:
        payload (bytes): El cuerpo crudo de la solicitud.
        signature (str): La firma proporcionada en el header (ej: 'sha256=...').
        secret (str): El secreto compartido (APP_SECRET).

    Returns:
        bool: True si la firma es válida, False en caso contrario.
    """
    if not secret:
        # Si no hay secreto configurado, no podemos validar.
        # Por defecto fallamos seguro o logueamos.
        # Aquí retornamos False para obligar a configurar el secreto si se llama a esta función.
        return False

    if not signature:
        return False

    # Extraer el hash de la firma (quitar 'sha256=')
    if signature.startswith('sha256='):
        signature_hash = signature[7:]
    else:
        signature_hash = signature

    try:
        # Calcular HMAC-SHA256
        expected_hash = hmac.new(
            secret.encode('utf-8'),
            payload,
            hashlib.sha256
        ).hexdigest()

        # Comparar de forma segura contra ataques de tiempo
        return secrets.compare_digest(expected_hash, signature_hash)
    except Exception:
        return False
